import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from typer.testing import CliRunner
from src.main import app
from src.pipeline import NovelPipeline
from src.publishing.metadata import build_upload_spec, load_metadata
from src.publishing.youtube import YouTubePublisher


class YouTubeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'chapter_1.mp4'
        self.video.write_bytes(b'video-placeholder')
        self.video.with_suffix('.json').write_text(json.dumps({'title': 'Rendered', 'duration_seconds': 120}))
        self.config = self.root / 'metadata.json'

    def write(self, value):
        self.config.write_text(json.dumps(value, ensure_ascii=False))
        return self.config

    def build(self, **kwargs):
        return build_upload_spec(self.video, channel_id='channel', metadata_file=self.config, **kwargs)

    def test_long_titles_from_every_source_are_shortened_before_upload(self):
        long_title = 'Một tiêu đề tiếng Việt rất dài ' * 8
        self.write({'title': long_title})
        self.assertLessEqual(len(self.build().title), 100)
        self.assertLessEqual(len(self.build(title=long_title).title), 100)
        self.write({})
        self.video.with_suffix('.json').write_text(json.dumps({'title': long_title}))
        self.assertLessEqual(len(self.build().title), 100)
        self.video.with_suffix('.youtube.json').write_text(json.dumps({'title': long_title}))
        spec = build_upload_spec(self.video, channel_id='channel')
        self.assertLessEqual(len(spec.title), 100)
        self.assertNotIn('…', spec.title)
        self.assertNotIn('...', spec.title)
        from src.publishing.jobs import PublishingRunner
        PublishingRunner._validate(spec, check_media=False)

    def test_title_boundary_unicode_and_invalid_values(self):
        import unicodedata
        from src.publishing.title import normalize_title
        self.assertEqual(normalize_title('Một… câu... chuyện'), 'Một câu chuyện')
        self.assertEqual(normalize_title('Tiêu đề...'), 'Tiêu đề')
        exact = 'Á' * 100
        self.assertEqual(normalize_title(exact), exact)
        self.assertEqual(normalize_title(unicodedata.normalize('NFD', exact)), exact)
        self.assertEqual(len(normalize_title('A' * 101)), 100)
        self.assertEqual(normalize_title('  Tiêu đề\n nhiều   khoảng trắng '), 'Tiêu đề nhiều khoảng trắng')
        for value in ('', ' ', '<bad>', '...', '…', None, 42):
            with self.assertRaises(ValueError):
                normalize_title(value)

    def test_precedence_and_false_values(self):
        self.write({'defaults': {'title': 'Default', 'privacy': 'unlisted', 'made_for_kids': True,
                                'tags': ['default']},
                    'videos': {'chapter_1.mp4': {'title': 'Specific', 'tags': ['specific']}}})
        spec = self.build()
        self.assertEqual((spec.title, spec.privacy, spec.tags, spec.made_for_kids),
                         ('Specific', 'unlisted', ('specific',), True))
        spec = self.build(title='CLI', privacy='private', tags=[], made_for_kids=False)
        self.assertEqual((spec.title, spec.privacy, spec.tags, spec.made_for_kids), ('CLI', 'private', (), False))

    def test_flat_json_unicode_hashtags_and_description(self):
        self.write({'description': 'Mô tả\nDòng hai', 'hashtags': ['TruyệnAudio', '#Audiobook', 'truyệnaudio']})
        spec = self.build()
        self.assertEqual(spec.title, 'Rendered')
        self.assertEqual(spec.description, 'Mô tả\nDòng hai\n\n#TruyệnAudio #Audiobook')

    def test_relative_thumbnail_and_disable(self):
        thumbnail = self.root / 'cover.png'
        Image.new('RGB', (320, 180)).save(thumbnail)
        self.write({'thumbnail': 'cover.png'})
        self.assertEqual(self.build().thumbnail, thumbnail.resolve())
        self.assertIsNone(self.build(use_thumbnail=False).thumbnail)
        self.write({'thumbnail': None})
        self.assertIsNone(self.build().thumbnail)

    def test_unknown_keys_types_and_schema_rejected(self):
        for data in ({'titel': 'typo'}, {'tags': 'not-array'}, {'made_for_kids': 'false'},
                     {'privacy': 'world'}, {'default_language': 'Vietnamese'}, {'defaults': [], 'videos': {}},
                     {'defaults': {}, 'videos': {'../wrong.mp4': {}}},
                     {'schema_version': 2, 'defaults': {}}, {'description': 5}):
            self.write(data)
            with self.assertRaises(ValueError, msg=str(data)):
                self.build()
        self.config.write_text('{"title":"one","title":"two"}')
        with self.assertRaisesRegex(ValueError, 'trùng'):
            self.build()

    def test_valid_chapters_and_invalid_timestamps(self):
        chapters = [{'start_seconds': 0, 'title': 'Mở đầu'},
                    {'start_seconds': 30, 'title': 'Diễn biến'}, {'start_seconds': 70, 'title': 'Kết thúc'}]
        self.write({'chapters': chapters})
        self.assertIn('00:00 Mở đầu\n00:30 Diễn biến\n01:10 Kết thúc', self.build().description)
        for invalid in (chapters[:2], [dict(c, start_seconds=s) for c, s in zip(chapters, [1, 30, 70])],
                        [dict(c, start_seconds=s) for c, s in zip(chapters, [0, 9, 70])],
                        [dict(c, start_seconds=s) for c, s in zip(chapters, [0, 30, 115])]):
            self.write({'chapters': invalid})
            with self.assertRaises(ValueError):
                self.build()

    def test_cli_json_values_are_not_overridden_by_defaults(self):
        self.write({'title': 'From JSON', 'description': 'Description', 'tags': ['json-tag'],
                    'privacy': 'unlisted', 'made_for_kids': True})
        result = CliRunner().invoke(app, ['youtube-upload', str(self.video),
            '--metadata-file', str(self.config), '--dry-run'])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data['title'], 'From JSON')
        self.assertEqual(data['tags'], ['json-tag'])
        self.assertEqual(data['privacy'], 'unlisted')
        self.assertTrue(data['made_for_kids'])
        result = CliRunner().invoke(app, ['youtube-upload', str(self.video),
            '--metadata-file', str(self.config), '--not-made-for-kids', '--privacy', 'private', '--dry-run'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(json.loads(result.output)['made_for_kids'])
        self.assertEqual(json.loads(result.output)['privacy'], 'private')

    def test_invalid_metadata_fails_before_oauth_or_upload(self):
        self.write({'title': '<invalid>'})
        with patch('src.publishing.youtube.YouTubePublisher') as publisher:
            with self.assertRaises(ValueError):
                NovelPipeline().upload_videos([self.video], channel_id='channel', metadata_file=self.config)
            publisher.assert_not_called()

    def test_transport_receives_language_and_synthetic_fields(self):
        self.write({'default_language': 'vi', 'default_audio_language': 'vi',
                    'contains_synthetic_media': True, 'notify_subscribers': False})
        http = Mock()
        http.request.return_value.status_code = 200
        http.request.return_value.headers = {'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'}
        publisher = YouTubePublisher(token_path=self.root / 'unused', session=http)
        publisher.start(self.build(), 100)
        args = http.request.call_args.kwargs
        self.assertEqual(args['json']['snippet']['defaultLanguage'], 'vi')
        self.assertEqual(args['json']['snippet']['defaultAudioLanguage'], 'vi')
        self.assertTrue(args['json']['status']['containsSyntheticMedia'])
        self.assertEqual(args['params']['notifySubscribers'], 'false')

    def test_json_hashtags_cannot_silently_overflow_description(self):
        self.write({'description': 'a' * 4990, 'hashtags': ['Audiobook', 'TruyenAudio']})
        result = CliRunner().invoke(app, ['youtube-upload', str(self.video),
            '--metadata-file', str(self.config), '--dry-run'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('5000', result.output)


    def test_process_forwards_external_metadata_for_local_and_web_input(self):
        self.write({'description': 'From JSON'})
        background = self.root / 'background.jpg'
        Image.new('RGB', (320, 180)).save(background)
        token = self.root / 'token.json'
        token.write_text('{}')
        source = self.root / 'chapter.txt'
        source.write_text('Hello')
        for input_path in (str(source), 'https://ixdzs8.com/read/644938/p1.html'):
            with patch('src.main.NovelTranslator'), patch('src.main.get_tts_provider'), \
                 patch('src.config.YOUTUBE_TOKEN_FILE', token), patch('src.config.YOUTUBE_CHANNEL_ID', 'channel'), \
                 patch('src.main.NovelPipeline') as pipeline:
                pipeline.return_value.process_file.return_value = (source, self.video)
                pipeline.return_value.process_url.return_value = [(source, self.video)]
                pipeline.return_value.render_videos.return_value = [self.video]
                result = CliRunner().invoke(app, ['process', input_path, '--background', str(background),
                    '--upload-youtube', '--youtube-metadata-file', str(self.config)])
                self.assertEqual(result.exit_code, 0, result.output)
                pipeline.return_value.upload_videos.assert_called_once_with(
                    [self.video], privacy=None, metadata_file=self.config)
