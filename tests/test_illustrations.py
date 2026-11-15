import base64
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from PIL import Image
from typer.testing import CliRunner

from src.main import app
from src.pipeline import NovelPipeline
from src.video.base import IllustrationScene, VideoSpec
from src.video.ffmpeg import FFmpegVideoRenderer
from src.video.illustrations import (GeminiImageBridge, IllustrationService, image_bytes,
                                     split_passages, validate_prompts)


def png(color='red'):
    buffer = io.BytesIO()
    Image.new('RGB', (320, 180), color).save(buffer, format='PNG')
    return buffer.getvalue()


class FakeBridge:
    model = 'gemini-auto'
    base_url = 'http://bridge/openai/v1'

    def __init__(self):
        self.plans, self.images = [], []
        self.fail_on = None

    def plan(self, passages, style, title):
        self.plans.append(passages)
        return ['Illustrate ' + part for part in passages]

    def generate(self, prompt, width, height):
        self.images.append(prompt)
        if self.fail_on == len(self.images):
            raise RuntimeError('quota reached')
        return png()


class IllustrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'chapter_vi.txt'
        self.source.write_text('Chương một. Người khách mở cửa. Anh bước vào phòng. Cô gái quay lại.', encoding='utf-8')
        self.bridge = FakeBridge()
        self.service = IllustrationService(self.bridge, images_per_chapter=3)

    def prepare(self, **kwargs):
        return self.service.prepare([self.source], [30.0], self.root / 'images', **kwargs)

    def test_passages_preserve_order_and_words(self):
        for text in ('Một câu. Hai câu! Ba câu?\n\nĐoạn tiếp.', 'một hai ba bốn năm', '中文内容'):
            for count in (1, 4, 8):
                parts = split_passages(text, count)
                self.assertEqual(' '.join(parts).split(), text.split())
                self.assertTrue(all(parts))
                self.assertLessEqual(len(parts), count)
        for count in (0, 9, True):
            with self.assertRaises(ValueError):
                split_passages('text', count)
        with self.assertRaises(ValueError):
            split_passages('  ', 2)

    def test_partial_failure_resumes_only_missing_images(self):
        self.bridge.fail_on = 2
        with self.assertRaisesRegex(RuntimeError, 'quota'):
            self.prepare()
        self.assertEqual(len(list((self.root / 'images').rglob('*.png'))), 1)
        self.bridge.fail_on = None
        scenes = self.prepare()
        self.assertEqual(len(self.bridge.plans), 1)
        self.assertEqual(len(self.bridge.images), 4)  # one saved, one failed, two remaining
        self.assertAlmostEqual(sum(s.duration_seconds for s in scenes), 30)
        self.assertEqual(len(scenes), 3)
        self.prepare()
        self.assertEqual(len(self.bridge.images), 4)

    def test_corrupt_image_and_changed_text_invalidate_cache(self):
        scenes = self.prepare()
        scenes[1].image.write_bytes(b'broken')
        self.prepare()
        self.assertEqual(len(self.bridge.images), 4)
        self.source.write_text(self.source.read_text() + ' Một sự kiện mới.')
        changed = self.prepare()
        self.assertEqual(len(self.bridge.plans), 2)
        self.assertNotEqual(scenes[0].image.parent, changed[0].image.parent)

    def test_new_audio_duration_reuses_images_and_keeps_chapter_boundary(self):
        self.prepare()
        second = self.root / 'chapter_2_vi.txt'
        second.write_text('Ngày mai. Một chuyến đi mới.')
        scenes = self.service.prepare([self.source, second], [10., 20.], self.root / 'both')
        first_count = len(split_passages(self.source.read_text(), 3))
        self.assertAlmostEqual(sum(s.duration_seconds for s in scenes[:first_count]), 10.)
        self.assertAlmostEqual(sum(s.duration_seconds for s in scenes[first_count:]), 20.)
        before = len(self.bridge.images)
        changed = self.service.prepare([self.source, second], [20., 30.], self.root / 'both')
        self.assertEqual(len(self.bridge.images), before)
        self.assertAlmostEqual(sum(s.duration_seconds for s in changed), 50.)

    def test_invalid_plan_or_input_never_generates_images(self):
        with patch.object(self.bridge, 'plan', return_value=['only one']):
            with self.assertRaises(ValueError):
                self.prepare()
        self.assertEqual(self.bridge.images, [])
        for durations in ([], [0.], [float('nan')]):
            with self.assertRaises(ValueError):
                self.service.prepare([self.source], durations, self.root / 'invalid')
        for data in (b'<html>not an image</html>', b''):
            with self.assertRaises(ValueError):
                image_bytes(data)
        for prompts in ([1], [''], ['x' * 6001]):
            with self.assertRaises(ValueError):
                validate_prompts(prompts, 1)

    def test_no_resume_regenerates_and_corrupt_manifest_fails_closed(self):
        self.prepare()
        self.prepare(resume=False)
        self.assertEqual(len(self.bridge.images), 6)
        manifest = next((self.root / 'images').rglob('manifest.json'))
        manifest.write_text('{broken')
        with self.assertRaisesRegex(ValueError, 'Checkpoint'):
            self.prepare()

    def test_bridge_uses_portable_base64_and_separate_chat_endpoint(self):
        requests = []
        def respond(request):
            requests.append(request)
            if request.url.path.endswith('/chat/completions'):
                payload = json.loads(request.content)
                self.assertEqual(payload['reasoning_effort'], 'low')
                self.assertEqual(payload['response_format'], {'type': 'json_object'})
                return httpx.Response(200, json={'choices': [{'message': {'content': '```json\n{"prompts":["scene"]}\n```'}}]})
            payload = json.loads(request.content)
            self.assertEqual(payload['n'], 1)
            self.assertEqual(payload['response_format'], 'b64_json')
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(png()).decode()}]})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            bridge = GeminiImageBridge('http://bridge/openai/v1', 'gemini-auto', client=client)
            self.assertEqual(bridge.plan(['source'], 'style', 'story'), ['scene'])
            self.assertEqual(image_bytes(bridge.generate('prompt', 1920, 1080)), png())
        self.assertEqual([r.url.path for r in requests], ['/openai/v1/chat/completions', '/openai/v1/images/generations'])

    def test_bridge_does_not_retry_quota_or_fetch_remote_image_urls(self):
        for response in (httpx.Response(429), httpx.Response(200, json={'data': [{'url': 'https://signed.example/image'}]})):
            calls = []
            def respond(request):
                calls.append(request)
                return response
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                bridge = GeminiImageBridge('http://bridge/openai/v1', 'gemini-auto', client=client)
                with self.assertRaises((RuntimeError, ValueError)):
                    bridge.generate('prompt', 1920, 1080)
            self.assertEqual(len(calls), 1)

    def test_bridge_reports_model_error_and_correct_stage_without_secrets(self):
        detail = 'unsupported Gemini model "bad-model"; available models: gemini-pro. Bearer secret-token'
        with httpx.Client(transport=httpx.MockTransport(lambda request:
                httpx.Response(400, json={'error': {'message': detail, 'type': 'invalid_request_error'}}))) as client:
            bridge = GeminiImageBridge('http://bridge/openai/v1', 'bad-model', api_key='secret-token', client=client)
            with self.assertRaises(RuntimeError) as raised:
                bridge.plan(['text'], 'style', 'title')
            message = str(raised.exception)
            self.assertIn('lập prompt', message)
            self.assertIn('available models: gemini-pro', message)
            self.assertIn('GEMINI_IMAGE_MODEL', message)
            self.assertNotIn('secret-token', message)

    def test_bridge_does_not_dump_html_or_unbounded_error_bodies(self):
        for response in (httpx.Response(400, text='<html>private cookie</html>'),
                         httpx.Response(400, json={'error': {'message': 'x' * 20000}})):
            with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
                bridge = GeminiImageBridge('http://bridge/openai/v1', 'gemini-auto', client=client)
                with self.assertRaises(RuntimeError) as raised:
                    bridge.generate('prompt', 1280, 720)
                self.assertNotIn('private cookie', str(raised.exception))
                self.assertLess(len(str(raised.exception)), 1000)

    def test_prompt_timeout_reports_stage_without_retry_or_request_details(self):
        calls = []
        def respond(request):
            calls.append(request)
            raise httpx.ReadTimeout('private request details', request=request)
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            bridge = GeminiImageBridge('http://bridge/openai/v1', 'gemini-auto', client=client)
            with self.assertRaisesRegex(RuntimeError, 'lập prompt.*hết thời gian') as raised:
                bridge.plan(['text'], 'style', 'title')
        self.assertEqual(len(calls), 1)
        self.assertNotIn('private request details', str(raised.exception))

    def test_cli_forwards_translation_without_story_metadata(self):
        audio = self.root / 'chapter.mp3'
        audio.write_bytes(b'fixture')
        bg = self.root / 'background.png'
        bg.write_bytes(png())
        with patch('src.main.NovelPipeline') as pipeline:
            result = CliRunner().invoke(app, ['render-video', str(audio), '--background', str(bg),
                '--translated-file', str(self.source), '--illustrate'])
            self.assertEqual(result.exit_code, 0, result.output)
            args = pipeline.return_value.render_videos.call_args.kwargs
            self.assertTrue(args['illustrate'])
            self.assertEqual(args['translated_files'], [self.source])
        with patch('src.main.NovelTranslator'), patch('src.main.get_tts_provider'), patch('src.main.NovelPipeline') as pipeline:
            pipeline.return_value.process_url.return_value = [(self.source, audio)]
            result = CliRunner().invoke(app, ['process', 'https://ixdzs8.com/read/1/p1.html', '--illustrate'])
            self.assertEqual(result.exit_code, 0, result.output)
            args = pipeline.return_value.render_videos.call_args.kwargs
            self.assertTrue(args['illustrate'])
            self.assertEqual(args['translated_files'], [self.source])

        with patch('src.main.NovelPipeline') as pipeline:
            result = CliRunner().invoke(app, ['render-video', str(audio),
                '--translated-file', str(self.source), '--illustrate'])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIsNone(pipeline.return_value.render_videos.call_args.args[1])
        with patch('src.main.NovelTranslator'), patch('src.main.get_tts_provider'), patch('src.main.NovelPipeline') as pipeline:
            pipeline.return_value.process_file.return_value = (self.source, audio)
            result = CliRunner().invoke(app, ['process', str(self.source), '--illustrate'])
            self.assertEqual(result.exit_code, 0, result.output)
            args = pipeline.return_value.render_videos.call_args.kwargs
            self.assertTrue(args['illustrate'])
            self.assertEqual(args['translated_files'], [self.source])

    def test_profile_requires_boolean_illustration_setting(self):
        from src.remote.profiles import load_profiles
        (self.root / 'story.json').write_text(json.dumps({'story_title': 'Tên truyện'}))
        (self.root / 'bg.png').write_bytes(png())
        profile = {'chapter_url_template': 'https://ixdzs8.com/read/1/p{chapter}.html',
                   'story_config': 'story.json', 'background': 'bg.png', 'glossary': 'glossary.csv', 'illustrate': True}
        path = self.root / 'profiles.json'
        path.write_text(json.dumps({'stories': {'demo': profile}}))
        self.assertTrue(load_profiles(path)['demo']['illustrate'])
        profile['illustrate'] = 'true'
        path.write_text(json.dumps({'stories': {'demo': profile}}))
        with self.assertRaisesRegex(ValueError, 'illustrate'):
            load_profiles(path)

    def test_manual_steps_stop_before_images_and_render_is_offline(self):
        args = ([self.source], [30.], self.root / 'stages')
        self.service.prepare(*args, stop_after='passages')
        self.assertEqual(self.bridge.plans, [])
        self.assertEqual(self.bridge.images, [])
        self.service.prepare(*args, stop_after='prompts')
        self.assertEqual(len(self.bridge.plans), 1)
        self.assertEqual(self.bridge.images, [])
        self.service.prepare(*args, stop_after='images')
        self.assertEqual(len(self.bridge.images), 3)
        with patch.object(self.bridge, 'plan', side_effect=AssertionError('offline')), \
             patch.object(self.bridge, 'generate', side_effect=AssertionError('offline')):
            scenes = self.service.prepare(*args, cached_only=True)
        self.assertEqual(len(scenes), 3)

    def test_offline_step_rejects_missing_and_corrupt_images_without_api(self):
        args = ([self.source], [30.], self.root / 'offline')
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            self.service.prepare(*args, cached_only=True)
        self.assertEqual(self.bridge.plans, [])
        scenes = self.service.prepare(*args)
        scenes[0].image.write_bytes(b'broken')
        before = len(self.bridge.images)
        with self.assertRaisesRegex(ValueError, 'Ảnh thiếu/hỏng'):
            self.service.prepare(*args, cached_only=True)
        self.assertEqual(len(self.bridge.images), before)



@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class IllustratedRendererTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audio = self.root / 'chapter.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=3', str(self.audio)], check=True)
        self.renderer = FFmpegVideoRenderer(state_dir=self.root / 'state')
        self.duration = self.renderer._duration(self.renderer._probe(self.audio))
        self.images = []
        for index, color in enumerate(('red', 'blue', 'green')):
            image = self.root / f'scene{index}.png'
            image.write_bytes(png(color))
            self.images.append(image)
        scenes = tuple(IllustrationScene(image, self.duration / 3, f'passage {index}', f'prompt {index}')
                       for index, image in enumerate(self.images))
        self.spec = VideoSpec((self.audio,), self.images[0], self.root / 'out.mp4',
                              'Truyện thử', 320, 180, 20, scenes=scenes, transition_seconds=.4)

    def pixel(self, video, time):
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(time), '-i', str(video),
            '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'])
        return Image.frombytes('RGB', (320, 180), data).getpixel((160, 90))

    def test_real_slideshow_blends_frames_keeps_audio_and_resumes(self):
        output = self.renderer.render(self.spec)
        info = self.renderer._probe(output)
        self.assertAlmostEqual(self.renderer._duration(info), self.duration, delta=.15)
        self.assertTrue(any(s['codec_type'] == 'audio' for s in info['streams']))
        red = self.pixel(output, .2)
        middle = self.pixel(output, self.duration / 3 + .2)
        blue = self.pixel(output, 1.7)
        self.assertGreater(red[0], 200)
        self.assertGreater(middle[0], 30)
        self.assertGreater(middle[2], 30)  # A blended frame, not a hard cut.
        self.assertGreater(blue[2], 200)
        metadata = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(len(metadata['scenes']), 3)
        self.assertEqual(metadata['timing'], 'proportional_text_length')
        before = output.read_bytes()
        with patch.object(self.renderer, '_run', side_effect=AssertionError('should resume')):
            self.renderer.render(self.spec)
        self.assertEqual(output.read_bytes(), before)
        with patch.object(self.renderer, '_run', side_effect=RuntimeError('render failed')):
            with self.assertRaises(RuntimeError):
                self.renderer.render(replace(self.spec, zoom_amount=.08))
        self.assertEqual(output.read_bytes(), before)

    def test_single_image_and_changed_image_render_again(self):
        single = replace(self.spec, scenes=(IllustrationScene(self.images[0], self.duration),))
        self.renderer.render(single)
        self.images[0].write_bytes(png('yellow'))
        with patch.object(self.renderer, '_run', wraps=self.renderer._run) as run:
            self.renderer.render(single)
            run.assert_called_once()
        for spec in (replace(single, transition_seconds=0), replace(single, zoom_amount=float('nan')),
                     replace(single, scenes=(IllustrationScene(self.images[0], 1.),))):
            with self.assertRaises(ValueError):
                self.renderer.render(spec)

    def test_pipeline_matches_translations_after_natural_sort_and_can_disable(self):
        texts, audios = [], []
        for chapter in (10, 2):
            text = self.root / f'chapter_{chapter}_vi.txt'
            text.write_text(f'Chương {chapter}. Một cảnh truyện.')
            audio = self.root / f'chapter_{chapter}.mp3'
            shutil.copyfile(self.audio, audio)
            texts.append(text)
            audios.append(audio)
        service, renderer = Mock(), Mock()
        service.prepare.return_value = ()
        renderer.render.side_effect = lambda spec, **kwargs: spec.output
        outputs = NovelPipeline().render_videos(audios, self.images[0], translated_files=texts,
            illustrate=True, illustration_service=service, renderer=renderer, chapters_per_video=2)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(service.prepare.call_args.args[0], [texts[1], texts[0]])
        self.assertEqual(len(service.prepare.call_args.args[1]), 2)
        with patch('src.config.VIDEO_ILLUSTRATIONS', True), patch('src.video.illustrations.GeminiImageBridge') as bridge:
            NovelPipeline().render_videos(audios, self.images[0], illustrate=False, renderer=renderer)
            bridge.assert_not_called()

    def test_pipeline_without_background_generates_and_renders(self):
        text = self.root / 'chapter_vi.txt'
        text.write_text('Chương một. Người khách mở cửa. Anh bước vào phòng. Cô gái quay lại.')
        events = []
        service = IllustrationService(FakeBridge(), images_per_chapter=2, progress=events.append)
        self.renderer.progress = events.append
        with patch('src.config.VIDEO_WIDTH', 320), patch('src.config.VIDEO_HEIGHT', 180), patch('src.config.VIDEO_FPS', 20):
            outputs = NovelPipeline(progress=events.append).render_videos([self.audio], translated_files=[text],
                illustrate=True, illustration_service=service, renderer=self.renderer, output_dir=self.root / 'videos')
        self.assertTrue(outputs[0].is_file())
        self.assertEqual(json.loads(outputs[0].with_suffix('.json').read_text())['timing'], 'proportional_text_length')
        self.assertTrue(any(e.stage == 'illustrations' and e.current == e.total for e in events))
        self.assertEqual(events[-1].stage, 'render')
