import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from typer.testing import CliRunner
from src.main import app
from src.pipeline import NovelPipeline
from src.publishing.episode_metadata import (EpisodeMetadata, EpisodeMetadataService,
    LLMEpisodeMetadataGenerator, MetadataComposer, ChapterText, load_story_config)
from src.publishing.metadata import build_upload_spec


class EpisodeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.story_file = self.root / 'story.json'
        self.story = {'story_title': 'Truyện thử', 'base_tags': ['truyện audio', 'Bảo hiểm'],
                      'hashtags': ['TruyenAudio'], 'privacy': 'private', 'description_footer': 'Theo dõi kênh.'}
        self.story_file.write_text(json.dumps(self.story))
        self.text = self.root / 'chapter_1_vi.txt'
        self.text.write_text('Chương 1: Bảo hiểm\n\nAn tranh luận với luật sư để nhận lại tiền bảo hiểm.')
        self.audio = self.root / 'chapter_1.mp3'
        self.audio.write_bytes(b'audio-placeholder')
        self.video = self.root / 'videos/chapter_1.mp4'
        self.dynamic = EpisodeMetadata('Giành lại tiền bảo hiểm', 'An bảo vệ quyền lợi của mình.',
                                       ('bảo hiểm', 'luật sư'), 'GIÀNH LẠI QUYỀN LỢI')
        self.generator = Mock()
        self.generator.cache_identity = 'fake:1'
        self.generator.generate.return_value = self.dynamic

    def test_composition_preserves_fixed_controls_and_deduplicates_tags(self):
        result = MetadataComposer().compose(self.story, self.dynamic,
            (ChapterText('chapter.txt', 'Chương 1', 'text'),))
        self.assertIn('Truyện thử', result['title'])
        self.assertIn('Giành lại tiền bảo hiểm', result['title'])
        self.assertEqual(result['tags'], ['truyện audio', 'Bảo hiểm', 'luật sư'])
        self.assertIn('Theo dõi kênh.', result['description'])
        self.assertEqual(result['privacy'], 'private')
        self.assertNotIn('thumbnail_text', result)

    def test_cache_invalidation_and_generated_upload_discovery(self):
        service = EpisodeMetadataService(self.generator)
        dynamic, path = service.prepare(self.video, [self.text], self.story)
        self.assertTrue(path.is_file())
        spec = build_upload_spec(self.video, channel_id='channel')
        self.assertIn('An bảo vệ', spec.description)
        self.assertIn('#TruyenAudio', spec.description)
        service.prepare(self.video, [self.text], self.story)
        self.generator.generate.assert_called_once()
        self.text.write_text(self.text.read_text() + '\nDiễn biến mới.')
        service.prepare(self.video, [self.text], self.story)
        self.assertEqual(self.generator.generate.call_count, 2)
        service.prepare(self.video, [self.text], dict(self.story, description_footer='Mới'))
        self.assertEqual(self.generator.generate.call_count, 3)

    def test_user_edit_preserved_and_explicit_file_overrides_generated(self):
        service = EpisodeMetadataService(self.generator)
        _, path = service.prepare(self.video, [self.text], self.story)
        metadata = json.loads(path.read_text())
        metadata['title'] = 'Đã biên tập'
        path.write_text(json.dumps(metadata))
        service.prepare(self.video, [self.text], self.story)
        self.assertEqual(build_upload_spec(self.video, channel_id='channel').title, 'Đã biên tập')
        explicit = self.root / 'explicit.json'
        explicit.write_text('{"title":"Explicit"}')
        self.assertEqual(build_upload_spec(self.video, channel_id='channel', metadata_file=explicit).title, 'Explicit')
        self.generator.generate.assert_called_once()

    def test_invalid_dynamic_response_does_not_publish_artifacts(self):
        self.generator.generate.return_value = EpisodeMetadata('', 'Summary', (), 'Text')
        with self.assertRaises(ValueError):
            EpisodeMetadataService(self.generator).prepare(self.video, [self.text], self.story)
        self.assertFalse(self.video.with_suffix('.youtube.json').exists())

    def test_llm_is_separate_and_always_closed(self):
        generator = LLMEpisodeMetadataGenerator(provider_name='deepseek')
        provider = Mock()
        provider.generate.return_value = json.dumps({'title': self.dynamic.title, 'summary': self.dynamic.summary,
            'tags': list(self.dynamic.tags), 'thumbnail_text': self.dynamic.thumbnail_text})
        chapters = (ChapterText('ch1.txt', 'Chương 1', 'Translated content'),)
        with patch('src.publishing.episode_metadata.get_translation_provider', return_value=provider):
            self.assertEqual(generator.generate(self.story, chapters), self.dynamic)
        payload = json.loads(provider.generate.call_args.kwargs['user_prompt'])
        self.assertEqual(payload['chapters'][0]['text'], 'Translated content')
        provider.close.assert_called_once()
        provider.generate.return_value = 'not json'
        with patch('src.publishing.episode_metadata.get_translation_provider', return_value=provider):
            with self.assertRaises(ValueError):
                generator.generate(self.story, chapters)
        self.assertEqual(provider.close.call_count, 2)

    def test_large_input_rejected_before_call(self):
        generator = LLMEpisodeMetadataGenerator(max_input_chars=3)
        with patch('src.publishing.episode_metadata.get_translation_provider') as factory:
            with self.assertRaises(ValueError):
                generator.generate(self.story, (ChapterText('a', 'title', 'too long'),))
            factory.assert_not_called()

    def test_natural_order_keeps_translation_audio_mapping(self):
        audio2 = self.root / 'chapter_2.mp3'
        text2 = self.root / 'chapter_2_vi.txt'
        audio2.write_bytes(b'audio2')
        text2.write_text('Chương 2\n\nNội dung thứ hai.')
        renderer = Mock()
        renderer.render.side_effect = lambda spec, **kw: spec.output
        outputs = NovelPipeline().render_videos([audio2, self.audio], self.root / 'bg.jpg',
            output_dir=self.root / 'videos', translated_files=[text2, self.text], story_config=self.story_file,
            metadata_generator=self.generator, chapters_per_video=2, renderer=renderer)
        chapters = self.generator.generate.call_args.args[1]
        self.assertEqual([c.filename for c in chapters], [self.text.name, text2.name])
        spec = renderer.render.call_args.args[0]
        self.assertEqual(spec.thumbnail_text, self.dynamic.thumbnail_text)
        self.assertEqual(len(outputs), 1)
        self.assertIn('Truyện thử', spec.title)

    def test_story_validation_and_missing_translation(self):
        self.story_file.write_text('{"story_title":"Title","privacy":"invalid"}')
        with self.assertRaises(ValueError):
            load_story_config(self.story_file)
        self.story_file.write_text(json.dumps(self.story))
        with self.assertRaises(ValueError):
            NovelPipeline().render_videos([self.audio], self.root / 'bg.jpg', story_config=self.story_file,
                                          renderer=Mock(), metadata_generator=self.generator)

    def test_process_cli_wires_translations_and_generated_metadata(self):
        background = self.root / 'bg.jpg'
        Image.new('RGB', (320, 180)).save(background)
        with patch('src.main.NovelTranslator'), patch('src.main.get_tts_provider'), \
             patch('src.main.NovelPipeline') as pipeline:
            pipeline.return_value.process_file.return_value = (self.text, self.audio)
            result = CliRunner().invoke(app, ['process', str(self.text), '--background', str(background),
                '--story-config', str(self.story_file), '--translation-provider', 'deepseek'])
            self.assertEqual(result.exit_code, 0, result.output)
            kwargs = pipeline.return_value.render_videos.call_args.kwargs
            self.assertEqual(kwargs['translated_files'], [self.text])
            self.assertEqual(kwargs['story_config'], self.story_file)
            self.assertEqual(kwargs['metadata_provider'], 'deepseek')

    def test_full_flow_fetch_translate_audio_metadata_render_upload(self):
        import shutil
        import subprocess
        from src.sources.base import Chapter
        from src.translator import NovelTranslator
        from src.glossary import Glossary
        from src.publishing.base import UploadProgress
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('Requires FFmpeg')
        source = Mock()
        source.fetch_chapter.side_effect = [
            Chapter('test', '1', '1', 'Chapter 1', 'An opens a book.', 'https://example.test/1', 'en', 'https://example.test/2'),
            Chapter('test', '1', '2', 'Chapter 2', 'An visits the lawyer.', 'https://example.test/2', 'en')]
        translation_provider = Mock()
        translation_provider.conversation_limit = 1
        translation_provider.generate.side_effect = ['Chương 1\n\nAn mở sách.', 'Chương 2\n\nAn gặp luật sư.']
        translator = NovelTranslator(provider=translation_provider, glossary=Glossary())
        class Speech:
            def generate_batch(self, tasks, **kwargs):
                for _, path in tasks:
                    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.5', str(path)], check=True)
        background = self.root / 'background.jpg'
        Image.new('RGB', (640, 360), 'navy').save(background)
        publisher = Mock()
        publisher.channel_id.return_value = 'channel'
        publisher.start.return_value = 'fake-session'
        publisher.query.return_value = UploadProgress(0)
        publisher.send.side_effect = lambda session, data, offset, size: UploadProgress(size, 'abcdefghijk', 'private')
        with patch('src.config.INPUT_DIR', self.root / 'input'), patch('src.config.OUTPUT_DIR', self.root / 'output'), \
             patch('src.config.VIDEO_WIDTH', 320), patch('src.config.VIDEO_HEIGHT', 180), \
             patch('src.config.VIDEO_FPS', 10), patch('src.config.YOUTUBE_STATE_DIR', self.root / 'upload-state'):
            pipeline = NovelPipeline(translator=translator, tts_provider=Speech())
            results = pipeline.process_url('https://example.test/1', max_chapters=2, source=source)
            videos = pipeline.render_videos([audio for _, audio in results], background,
                story_config=self.story_file, translated_files=[text for text, _ in results],
                metadata_generator=self.generator, chapters_per_video=2)
            published = pipeline.upload_videos(videos, channel_id='channel', publisher=publisher)
        self.assertEqual(len(videos), 1)
        self.assertTrue(videos[0].is_file())
        self.assertTrue(videos[0].with_suffix('.jpg').is_file())
        self.assertTrue(videos[0].with_suffix('.episode.json').is_file())
        self.assertTrue(videos[0].with_suffix('.youtube.json').is_file())
        self.assertEqual(published[0].video_id, 'abcdefghijk')
        self.assertEqual(len(self.generator.generate.call_args.args[1]), 2)
        spec = publisher.start.call_args.args[0]
        self.assertIn('An bảo vệ', spec.description)
        self.assertIn('#TruyenAudio', spec.description)
        self.assertEqual(spec.privacy, 'private')
