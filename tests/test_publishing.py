import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image
from typer.testing import CliRunner

from src.main import app
from src.pipeline import NovelPipeline
from src.publishing.base import UploadSpec, UploadProgress, RetryableUploadError
from src.publishing.jobs import PublishingRunner
from src.publishing.metadata import build_upload_spec
from src.publishing.youtube import YouTubePublisher

ID = 'abcdefghijk'
SESSION = 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'


class FakePublisher:
    def __init__(self):
        self.starts = 0
        self.offset = 0
        self.size = 0
        self.sends = []
        self.thumbnails = 0
        self.interrupt = False
        self.lose_final = False
        self.fail_thumbnail = False

    def channel_id(self): return 'channel'
    def start(self, spec, size):
        self.starts += 1
        self.size = size
        return SESSION
    def query(self, session, size):
        return UploadProgress(self.offset, ID if self.offset == size else None, 'private')
    def send(self, session, data, offset, size):
        self.sends.append(offset)
        self.offset = offset + len(data)
        if self.interrupt:
            self.interrupt = False
            raise KeyboardInterrupt()
        if self.lose_final and self.offset == size:
            self.lose_final = False
            raise RetryableUploadError('lost response')
        return self.query(session, size)
    def set_thumbnail(self, video_id, thumbnail):
        self.thumbnails += 1
        if self.fail_thumbnail:
            raise RuntimeError('thumbnail permission denied')
    def close(self): pass


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'chapter.mp4'
        self.video.write_bytes(b'v' * (512 * 1024 + 9))
        self.thumb = self.root / 'chapter.jpg'
        Image.new('RGB', (320, 180), 'blue').save(self.thumb)
        self.spec = UploadSpec(self.video, 'Tên truyện', 'channel', thumbnail=self.thumb)
        self.publisher = FakePublisher()
        self.runner = PublishingRunner(self.publisher, self.root / 'state', chunk_size=256 * 1024)

    def test_success_and_deduplication_across_paths(self):
        result = self.runner.publish(self.spec)
        self.assertEqual(result.video_id, ID)
        self.assertEqual(self.publisher.starts, 1)
        self.assertEqual(self.publisher.sends, [0, 256 * 1024, 512 * 1024])
        self.assertEqual(self.publisher.thumbnails, 1)
        copy = self.root / 'renamed.mp4'
        copy.write_bytes(self.video.read_bytes())
        self.runner.publish(replace(self.spec, video=copy))
        self.assertEqual(self.publisher.starts, 1)
        self.assertEqual(self.publisher.thumbnails, 1)

    def test_resume_after_interrupt_uses_server_offset(self):
        self.publisher.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.runner.publish(self.spec)
        self.runner.publish(self.spec)
        self.assertEqual(self.publisher.starts, 1)
        self.assertEqual(self.publisher.sends, [0, 256 * 1024, 512 * 1024])

    def test_lost_final_response_is_recovered_without_duplicate(self):
        self.publisher.lose_final = True
        with patch('src.publishing.jobs.time.sleep'):
            self.assertEqual(self.runner.publish(self.spec).video_id, ID)
        self.assertEqual(self.publisher.starts, 1)

    def test_thumbnail_failure_preserves_id_and_only_retries_thumbnail(self):
        self.publisher.fail_thumbnail = True
        with self.assertRaises(RuntimeError):
            self.runner.publish(self.spec)
        count = len(self.publisher.sends)
        with sqlite3.connect(self.root / 'state/uploads.sqlite3') as db:
            self.assertEqual(db.execute('SELECT video_id FROM uploads').fetchone()[0], ID)
        self.publisher.fail_thumbnail = False
        self.runner.publish(self.spec)
        self.assertEqual(len(self.publisher.sends), count)
        self.assertEqual(self.publisher.starts, 1)
        self.assertEqual(self.publisher.thumbnails, 2)

    def test_expired_session_does_not_start_new_upload(self):
        self.publisher.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.runner.publish(self.spec)
        with patch.object(self.publisher, 'query', side_effect=RuntimeError('expired')):
            with self.assertRaises(RuntimeError):
                self.runner.publish(self.spec)
        self.assertEqual(self.publisher.starts, 1)

    def test_metadata_change_is_blocked_and_channel_checked(self):
        self.runner.publish(self.spec)
        with self.assertRaises(ValueError):
            self.runner.publish(replace(self.spec, title='Other title'))
        with self.assertRaises(ValueError):
            self.runner.publish(replace(self.spec, channel_id='wrong-channel'))
        self.assertEqual(self.publisher.starts, 1)

    def test_validation_before_remote_calls(self):
        for spec in (replace(self.spec, title=''), replace(self.spec, privacy='invalid'),
                     replace(self.spec, channel_id=''), replace(self.spec, title='a' * 101),
                     replace(self.spec, video=self.root / 'missing.mp4')):
            with self.assertRaises(ValueError):
                self.runner.publish(spec)
        self.assertEqual(self.publisher.starts, 0)

    def test_metadata_sidecar_and_dry_run_are_offline(self):
        self.video.with_suffix('.json').write_text(json.dumps({'title': 'Rendered title'}))
        spec = build_upload_spec(self.video, channel_id='channel')
        self.assertEqual(spec.title, 'Rendered title')
        self.assertEqual(spec.thumbnail, self.thumb)
        with patch('src.publishing.youtube.authorized_session', side_effect=AssertionError('network')):
            result = CliRunner().invoke(app, ['youtube-upload', str(self.video), '--dry-run'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('Rendered title', result.output)

    def test_pipeline_injectable_publisher(self):
        with patch('src.config.YOUTUBE_STATE_DIR', self.root / 'state'):
            result = NovelPipeline().upload_videos([self.video], channel_id='channel', publisher=self.publisher)
        self.assertEqual(result[0].video_id, ID)

    def test_pipeline_upload_requires_background_before_translation(self):
        with patch('src.main.NovelTranslator') as translator:
            result = CliRunner().invoke(app, ['process', 'input.txt', '--upload-youtube'])
        self.assertNotEqual(result.exit_code, 0)
        translator.assert_not_called()


    def test_upload_progress_reports_acknowledged_bytes(self):
        events = []
        self.runner.progress = events.append
        self.runner.publish(self.spec)
        self.assertEqual(events[0].current, 0)
        self.assertEqual(events[-1].current, self.video.stat().st_size)
        self.assertTrue(all(event.unit == 'byte' for event in events))
        self.assertEqual([event.current for event in events], sorted(event.current for event in events))


def response(status, data=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data or {}).encode()
    result.headers.update(headers or {})
    return result


class YouTubeTransportTests(unittest.TestCase):
    def setUp(self):
        self.http = Mock()
        self.publisher = YouTubePublisher(token_path=Path('unused'), session=self.http)

    def test_initialization_and_resumable_range(self):
        self.http.request.return_value = response(200, headers={'Location': SESSION})
        spec = UploadSpec(Path('v.mp4'), 'Title', 'channel')
        self.assertEqual(self.publisher.start(spec, 1000), SESSION)
        call = self.http.request.call_args
        self.assertEqual(call.kwargs['json']['status']['privacyStatus'], 'private')
        self.assertFalse(call.kwargs['allow_redirects'])
        self.http.request.return_value = response(308, headers={'Range': 'bytes=0-255'})
        self.assertEqual(self.publisher.query(SESSION, 1000).offset, 256)
        self.assertEqual(self.http.request.call_args.kwargs['headers']['Content-Range'], 'bytes */1000')
        self.http.request.return_value = response(201, {'id': ID, 'status': {'privacyStatus': 'private'}})
        self.assertEqual(self.publisher.send(SESSION, b'abc', 997, 1000).video_id, ID)
        self.assertEqual(self.http.request.call_args.kwargs['headers']['Content-Range'], 'bytes 997-999/1000')

    def test_transport_failure_never_exposes_session_url(self):
        self.http.request.side_effect = requests.ConnectionError(SESSION)
        with self.assertRaises(RetryableUploadError) as caught:
            self.publisher.query(SESSION, 1000)
        self.assertNotIn(SESSION, str(caught.exception))

    def test_unsafe_session_and_nonretryable_api_errors(self):
        with self.assertRaises(ValueError):
            self.publisher.query('https://evil.test/upload', 1000)
        self.http.request.assert_not_called()
        self.http.request.return_value = response(403, {'error': {'errors': [{'reason': 'quotaExceeded'}]}})
        with self.assertRaisesRegex(RuntimeError, 'quotaExceeded'):
            self.publisher.query(SESSION, 1000)

    def test_retryable_server_errors(self):
        self.http.request.return_value = response(503)
        with self.assertRaises(RetryableUploadError):
            self.publisher.query(SESSION, 1000)


class OAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import google.oauth2.credentials
        except ImportError:
            raise unittest.SkipTest('Install requirements-youtube.txt for OAuth tests')

    def test_token_storage_and_offline_loading(self):
        from datetime import datetime
        from google.oauth2.credentials import Credentials
        from src.publishing.auth import SCOPES, save_token, authorized_session
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token.json'
            credentials = Credentials(token='test-token', refresh_token='test-refresh',
                token_uri='https://oauth2.googleapis.com/token', client_id='test-client',
                client_secret='test-secret', scopes=SCOPES, expiry=datetime(2099, 1, 1))
            save_token(credentials, token)
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
            session = authorized_session(token)
            self.assertEqual(session.credentials.token, 'test-token')
            session.close()
            credentials = Credentials(token='test', refresh_token='refresh',
                token_uri='https://oauth2.googleapis.com/token', client_id='client',
                client_secret='secret', scopes=SCOPES[:1], expiry=datetime(2099, 1, 1))
            save_token(credentials, token)
            with self.assertRaisesRegex(ValueError, 'thiếu quyền'):
                authorized_session(token)

    def test_missing_token_is_actionable(self):
        from src.publishing.auth import authorized_session
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'youtube-auth'):
                authorized_session(Path(directory) / 'missing.json')


class ChannelUploadLimitTests(unittest.TestCase):
    def test_limit_error_is_actionable_not_session_expiry_or_retryable(self):
        from src.publishing.base import UploadLimitExceeded
        http = Mock()
        http.request.return_value = response(400, {'error': {'errors': [{'reason': 'uploadLimitExceeded'}]}})
        publisher = YouTubePublisher(token_path=Path('unused'), session=http)
        with self.assertRaises(UploadLimitExceeded) as caught:
            publisher.channel_id()
        self.assertIn('24 giờ', str(caught.exception))
        self.assertNotIn('phiên upload hết hạn', str(caught.exception))
        self.assertNotIsInstance(caught.exception, RetryableUploadError)
