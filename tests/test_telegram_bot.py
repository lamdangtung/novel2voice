import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from PIL import Image
from src.remote.app import BotApplication, instance_lock, safe_error
from src.remote.controller import BotController, format_job
from src.remote.executor import FullPipelineExecutor, ProgressTracker
from src.remote.profiles import load_profiles
from src.remote.store import BotStore
from src.remote.transport import TelegramMessenger
from src.progress import ProgressEvent


def update(text, *, uid=42, update_id=1, chat_type='private'):
    return {'update_id': update_id, 'message': {'text': text,
        'from': {'id': uid, 'is_bot': False}, 'chat': {'id': uid, 'type': chat_type}}}


class BotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = BotStore(self.root / 'bot.sqlite3')
        self.profiles = {'story': {'chapter_url_template': 'https://ixdzs8.com/read/644938/p{chapter}.html'}}
        self.controller = BotController(self.store, self.profiles, [42])
        self.messenger = Mock()
        self.messenger.send.return_value = 123
        self.executor = Mock()
        self.executor.run.return_value = {'videos': [], 'youtube': ['https://www.youtube.com/watch?v=abcdefghijk']}
        self.app = BotApplication(self.store, self.controller, self.messenger, self.executor)

    def test_authorization_and_private_chat_required(self):
        self.assertIsNone(self.controller.handle(update('/run story 1', uid=99)))
        self.assertIsNone(self.controller.handle(update('/run story 1', chat_type='group')))
        self.assertEqual(self.store.list(42), [])
        with self.assertRaises(ValueError):
            BotController(self.store, self.profiles, [])

    def test_run_duplicate_delivery_and_chapter_dedup(self):
        first = self.controller.handle(update('/run story 1'))
        self.assertEqual(first, self.controller.handle(update('/run story 1')))
        self.controller.handle(update('/run story 1', update_id=2))
        self.assertEqual(len(self.store.list(42)), 1)
        self.assertTrue(self.app.work_once())
        self.controller.handle(update('/run story 1', update_id=3))
        self.assertEqual(len(self.store.list(42)), 1)
        self.assertEqual(self.store.get(1)['status'], 'succeeded')

    def test_schedule_timezone_and_claim_only_due_job(self):
        self.controller.handle(update('/schedule story 2 2099-01-01 09:00'))
        job = self.store.get(1)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        expected = datetime(2099, 1, 1, 9, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')).timestamp()
        self.assertEqual(job['run_at'], expected)
        self.assertIsNone(self.store.claim(now=expected - 1))
        self.assertEqual(self.store.claim(now=expected)['chapter'], 2)
        self.assertIsNone(self.store.claim(now=expected))

    def test_status_pages_cover_all_visible_jobs_with_owner_isolation(self):
        for chapter in range(1, 24):
            self.store.enqueue('story', chapter, {}, 42, 42, time.time())
        self.store.finish(2, 'succeeded')
        self.store.clear('2', 42)
        self.store.enqueue('other', 1, {}, 99, 99, time.time())
        seen = []
        for page, expected in ((1, 10), (2, 10), (3, 2)):
            jobs, total = self.store.list_page(42, page)
            self.assertEqual(total, 22)
            self.assertEqual(len(jobs), expected)
            seen.extend(job['id'] for job in jobs)
            command = '/status' if page == 1 else f'/status page {page}'
            reply = self.controller.handle(update(command, update_id=page))[1]
            self.assertIn(f'Trang {page}/3 · 22 job', reply)
            if page < 3:
                self.assertIn(f'/status page {page + 1}', reply)
            if page > 1:
                self.assertIn(f'/status page {page - 1}', reply)
            self.assertLess(len(reply), 4000)
        self.assertEqual(seen, [i for i in range(23, 0, -1) if i != 2])
        self.assertIn('Job #1', self.controller.handle(update('/status 1', update_id=10))[1])
        self.assertIn('không tồn tại', self.controller.handle(update('/status page 4', update_id=11))[1])
        self.assertIn('Số trang phải', self.controller.handle(update('/status page 0', update_id=12))[1])
        self.assertIn('Lệnh không hợp lệ', self.controller.handle(update('/status page abc', update_id=13))[1])

    def test_status_empty_and_exact_page_boundary(self):
        self.assertEqual(self.controller.handle(update('/status'))[1], 'Chưa có job.')
        for chapter in range(1, 11):
            self.store.enqueue('story', chapter, {}, 42, 42, time.time())
        reply = self.controller.handle(update('/status', update_id=2))[1]
        self.assertIn('Trang 1/1 · 10 job', reply)
        self.assertNotIn('Trang sau:', reply)
        self.assertNotIn('Trang trước:', reply)
        self.assertIn('Có 1 trang', self.controller.handle(update('/status page 2', update_id=3))[1])

    def test_cancel_and_owner_isolation(self):
        self.controller.handle(update('/schedule story 2 2099-01-01 09:00'))
        self.assertFalse(self.store.cancel(1, 99))
        self.assertIsNone(self.store.get(1, 99))
        self.assertTrue(self.store.cancel(1, 42))
        self.assertIsNone(self.store.claim(now=5_000_000_000))

    def test_cancel_multiple_jobs_reports_each_and_deduplicates(self):
        for chapter in range(1, 5):
            self.store.enqueue('story', chapter, {}, 42, 42, time.time())
        self.store.claim()
        self.store.finish(2, 'succeeded')
        other, _ = self.store.enqueue('other', 1, {}, 99, 99, time.time())
        request = update(f'/cancel 1 2 3 4 4 {other["id"]} 999', update_id=10)
        reply = self.controller.handle(request)
        self.assertIn('#1: Đang chạy', reply[1])
        self.assertIn('#2: Không còn chờ chạy', reply[1])
        self.assertIn('#3: Đã hủy lịch.', reply[1])
        self.assertEqual(reply[1].count('#4:'), 1)
        self.assertIn(f'#{other["id"]}: Không tìm thấy job của bạn.', reply[1])
        self.assertIn('#999: Không tìm thấy job của bạn.', reply[1])
        self.assertEqual(self.store.get(3)['status'], 'cancelled')
        self.assertEqual(self.store.get(4)['status'], 'cancelled')
        self.assertEqual(self.store.get(other['id'])['status'], 'queued')
        self.assertEqual(self.controller.handle(request), reply)

    def test_cancel_invalid_batch_does_not_partially_cancel(self):
        self.controller.handle(update('/run story 1'))
        for index, text in enumerate(('/cancel 1 abc', '/cancel 1 -2', '/cancel 1 0'), 20):
            self.assertIn('Lệnh không hợp lệ', self.controller.handle(update(text, update_id=index))[1])
            self.assertEqual(self.store.get(1)['status'], 'queued')
        self.assertIn('Đã hủy lịch.', self.controller.handle(update('/cancel 1', update_id=30))[1])

    def test_failed_job_retry_and_restart_interruption(self):
        self.controller.handle(update('/run story 1'))
        self.executor.run.side_effect = RuntimeError('failed')
        self.app.work_once()
        self.assertEqual(self.store.get(1)['status'], 'failed')
        self.assertTrue(self.store.retry(1, 42))
        self.store.claim()
        self.store.recover()
        self.assertEqual(self.store.get(1)['status'], 'interrupted')
        self.assertTrue(self.store.retry(1, 42))

    def test_clear_guards_owner_and_retains_checkpoints(self):
        self.controller.handle(update('/run story 1'))
        self.assertIn('/cancel 1', self.controller.handle(update('/clear 1', update_id=2))[1])
        self.store.claim()
        self.assertIn('đang chạy', self.controller.handle(update('/clear 1', update_id=3))[1])
        self.store.finish(1, 'failed', error='test')
        checkpoint = self.root / 'artifacts' / '1' / 'artifacts.json'
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text('{}')
        self.store.pause_uploads(time.time() + 86400)
        pause = self.store.upload_pause_until()
        self.assertEqual(self.store.clear('failed', 99), 0)
        reply = self.controller.handle(update('/clear 1', update_id=4))
        self.assertIn('Đã dọn 1', reply[1])
        self.assertEqual(reply, self.controller.handle(update('/clear 1', update_id=4)))
        self.assertEqual(self.store.list(42), [])
        self.assertEqual(self.store.notifications(), [])
        self.assertTrue(checkpoint.exists())
        self.assertEqual(self.store.upload_pause_until(), pause)
        self.assertEqual(BotStore(self.store.path).list(42), [])
        reply = self.controller.handle(update('/run story 1', update_id=5))[1]
        self.assertIn('/retry 1', reply)
        self.assertEqual(len(self.store.list(42)), 1)
        self.assertTrue(self.store.retry(1, 42))

    def test_clear_groups_and_completed_dedup(self):
        for chapter, status in enumerate(('succeeded', 'cancelled', 'failed', 'interrupted', 'queued'), 1):
            job, _ = self.store.enqueue('story', chapter, self.profiles['story'], 42, 42, time.time())
            if status != 'queued':
                self.store.finish(job['id'], status)
        self.assertIn('Đã dọn 2', self.controller.handle(update('/clear finished'))[1])
        self.assertEqual({j['status'] for j in self.store.list(42)}, {'failed', 'interrupted', 'queued'})
        self.assertIn('Đã dọn 2', self.controller.handle(update('/clear failed', update_id=2))[1])
        self.assertEqual(len(self.store.list(42)), 1)
        self.controller.handle(update('/run story 1', update_id=3))
        self.assertEqual(self.store.get(1)['status'], 'succeeded')
        self.assertEqual(len(self.store.list(42)), 2)
        self.assertEqual(self.store.clear('finished', 42), 1)
        self.assertEqual(self.store.clear('finished', 42), 0)

    def test_no_cancel_running_job(self):
        self.controller.handle(update('/run story 1'))
        self.store.claim()
        self.assertFalse(self.store.cancel(1, 42))

    def test_telegram_outage_never_reexecutes_pipeline(self):
        self.messenger.poll.return_value = [update('/run story 1')]
        self.messenger.send.side_effect = RuntimeError('offline')
        self.app.poll_once()
        self.assertEqual(self.store.offset(), 0)
        self.app.poll_once()
        self.assertEqual(len(self.store.list(42)), 1)
        self.messenger.send.side_effect = None
        self.app.poll_once()
        self.assertEqual(self.store.offset(), 2)
        self.executor.run.assert_not_called()

    def test_completion_notification_is_persisted_and_edited(self):
        self.controller.handle(update('/run story 1'))
        self.app.work_once()
        self.app.flush_notifications()
        self.assertIn('abcdefghijk', self.messenger.send.call_args.args[1])
        self.assertEqual(self.store.get(1)['message_id'], 123)
        self.assertEqual(self.store.notifications(), [])

    def test_revoked_user_job_is_not_executed(self):
        self.controller.handle(update('/run story 1'))
        self.controller.allowed_users.clear()
        self.app.work_once()
        self.app.flush_notifications()
        self.executor.run.assert_not_called()
        self.messenger.send.assert_not_called()

    def test_progress_and_eta_calculation(self):
        self.controller.handle(update('/run story 1'))
        job = self.store.claim()
        clock = Mock(return_value=0)
        tracker = ProgressTracker(self.store, job, clock=clock)
        tracker(ProgressEvent('upload', 0, 1000, 'byte'))
        clock.return_value = 10
        tracker(ProgressEvent('upload', 500, 1000, 'byte'))
        progress = json.loads(self.store.get(1)['progress'])
        self.assertEqual(progress['fraction'], .5)
        self.assertAlmostEqual(progress['upload_eta'], 10)
        self.assertIn('Upload: 0.0/0.0 MiB', format_job(self.store.get(1)))
        self.assertIn('ước tính', format_job(self.store.get(1)))

    def test_invalid_remote_input_cannot_execute_shell(self):
        for index, command in enumerate(['/run story 1;rm', '/run missing 1', '/run story -1',
                                          '/schedule story 1 2020-01-01 00:00'], 1):
            self.controller.handle(update(command, update_id=index))
        self.assertEqual(self.store.list(42), [])

    def test_instance_lock(self):
        with instance_lock(self.root / 'lock'):
            with self.assertRaises(RuntimeError):
                with instance_lock(self.root / 'lock'):
                    pass

    def test_transport_and_redaction(self):
        payloads = []
        def handle(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={'ok': True, 'result': {'message_id': 11}})
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            transport = TelegramMessenger('fake-secret', client=client)
            self.assertEqual(transport.send(42, 'progress', 9), 11)
        self.assertEqual(payloads[0]['message_id'], 9)
        self.assertNotIn('secret', safe_error(RuntimeError('secret https://host/path?token=abc'), ['secret']))
        self.assertNotIn('token=abc', safe_error(RuntimeError('https://host/path?token=abc')))

    def test_profile_paths_and_validation(self):
        story = self.root / 'story.json'
        story.write_text('{"story_title":"Test"}')
        background = self.root / 'background.jpg'
        Image.new('RGB', (20, 20)).save(background)
        profile = self.root / 'profiles.json'
        entry = dict(self.profiles['story'], story_config='story.json', background='background.jpg', glossary='glossary.csv')
        profile.write_text(json.dumps({'stories': {'story': entry}}))
        loaded = load_profiles(profile)['story']
        self.assertEqual(loaded['story_config'], str(story.resolve()))
        entry['chapter_url_template'] = 'https://evil.test/{chapter}'
        profile.write_text(json.dumps({'stories': {'story': entry}}))
        with self.assertRaises(ValueError):
            load_profiles(profile)

    def test_executor_retry_reuses_completed_artifacts(self):
        files = {}
        for name in ('source.txt', 'translation.txt', 'audio.mp3', 'video.mp4', 'video.youtube.json', 'video.jpg'):
            path = self.root / name
            path.write_text('content')
            files[name] = path
        settings = dict(self.profiles['story'], glossary=str(self.root / 'glossary.csv'),
                        background='bg.jpg', story_config='story.json', _job_dir=str(self.root / 'artifacts'))
        with patch('src.remote.executor.NovelPipeline') as factory, \
             patch('src.remote.executor.NovelTranslator') as translator, \
             patch('src.remote.executor.get_tts_provider') as speech:
            pipeline = factory.return_value
            pipeline.fetch_only.return_value = [files['source.txt']]
            pipeline.translate_only.return_value = files['translation.txt']
            pipeline.tts_only.return_value = files['audio.mp3']
            pipeline.render_videos.return_value = [files['video.mp4']]
            pipeline.upload_videos.side_effect = [RuntimeError('upload failed'),
                                                   [SimpleNamespace(url='https://www.youtube.com/watch?v=abcdefghijk')]]
            executor = FullPipelineExecutor()
            with self.assertRaises(RuntimeError):
                executor.run(settings, 1, None)
            result = executor.run(settings, 1, None)
            self.assertTrue(result['youtube'])
            translator.assert_called_once()
            speech.assert_called_once()
            pipeline.render_videos.assert_called_once()
            self.assertEqual(pipeline.upload_videos.call_count, 2)
            files['audio.mp3'].write_text('modified')
            with self.assertRaises(ValueError):
                executor.run(settings, 1, None)

    def test_bot_startup_rejects_missing_or_invalid_auth_without_network(self):
        from src.remote.app import run_bot
        for token, users in (('', ''), ('fake-token', 'not-a-user-id'), ('fake-token', '-1')):
            with patch('src.config.TELEGRAM_BOT_TOKEN', token), \
                 patch('src.config.TELEGRAM_ALLOWED_USER_IDS', users), \
                 patch('src.remote.app.TelegramMessenger') as transport:
                with self.assertRaises(ValueError):
                    run_bot(self.root / 'missing.json', self.root / 'state')
                transport.assert_not_called()

    def test_telegram_errors_identify_token_conflict_and_network_without_leaking_token(self):
        for code, expected in ((401, 'Token'), (409, 'Xung đột')):
            def handle(request):
                return httpx.Response(code, json={'ok': False, 'error_code': code,
                    'description': 'Rejected https://api.telegram.org/botfake-secret/getUpdates'})
            with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                messenger = TelegramMessenger('fake-secret', client=client)
                with self.assertRaises(RuntimeError) as caught:
                    messenger.poll(0)
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn('fake-secret', str(caught.exception))
        def offline(request):
            raise httpx.ConnectError('DNS lookup failed https://api.telegram.org/botfake-secret/getMe')
        with httpx.Client(transport=httpx.MockTransport(offline)) as client:
            messenger = TelegramMessenger('fake-secret', client=client)
            with self.assertRaises(RuntimeError) as caught:
                messenger.identity()
            self.assertIn('ConnectError', str(caught.exception))
            self.assertNotIn('fake-secret', str(caught.exception))

    def test_run_failed_chapter_reuses_job_and_directs_user_to_retry(self):
        self.controller.handle(update('/run story 1'))
        self.store.finish(1, 'failed', error='failure')
        reply = self.controller.handle(update('/run story 1', update_id=2))[1]
        self.assertIn('/retry 1', reply)
        self.assertEqual(len(self.store.list(42)), 1)

    def test_upload_limit_pauses_other_upload_jobs_persistently(self):
        from src.publishing.base import UploadLimitExceeded
        self.controller.handle(update('/run story 1'))
        self.controller.handle(update('/run story 2', update_id=2))
        self.executor.run.side_effect = UploadLimitExceeded('uploadLimitExceeded')
        self.assertTrue(self.app.work_once())
        self.assertEqual(self.store.get(1)['status'], 'failed')
        self.assertGreater(self.store.upload_pause_until(), time.time() + 86000)
        self.assertFalse(self.app.work_once())
        self.executor.run.assert_called_once()
        reply = self.controller.handle(update('/status 1', update_id=3))[1]
        self.assertIn('tạm giữ upload', reply)
        resumed = BotStore(self.root / 'bot.sqlite3')
        self.assertIsNone(resumed.claim())
        # Jobs that explicitly disable upload can continue.
        resumed.enqueue('local', 1, {'upload_youtube': False}, 42, 42, 0)
        self.assertEqual(resumed.claim()['profile'], 'local')

    def test_legacy_upload_limit_error_restores_pause_on_startup(self):
        self.controller.handle(update('/run story 1'))
        self.store.finish(1, 'failed', error='YouTube HTTP 400 (uploadLimitExceeded).')
        restored = BotStore(self.root / 'bot.sqlite3')
        self.assertGreater(restored.upload_pause_until(), time.time() + 86000)
