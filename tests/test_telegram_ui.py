import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from src.remote.app import BotApplication
from src.remote.controller import BotController
from src.remote.store import BotStore
from src.remote.transport import TelegramMessenger
from src.remote.ui import TelegramUI, COMMANDS


class UITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = BotStore(Path(temp.name) / 'bot.sqlite3')
        self.profiles = {'story': {'upload_youtube': True}, 'local': {'upload_youtube': False}}
        self.controller = BotController(self.store, self.profiles, [42, 43])
        self.ui = TelegramUI(self.controller)
        self.counter = 0

    def event(self, text, *, callback=False, user=42, group=False):
        self.counter += 1
        message = {'message_id': 100, 'chat': {'id': user, 'type': 'group' if group else 'private'}}
        sender = {'id': user, 'is_bot': False}
        if callback:
            return {'update_id': self.counter, 'callback_query': {'id': str(self.counter), 'from': sender,
                    'message': message, 'data': text}}
        return {'update_id': self.counter, 'message': dict(message, text=text, **{'from': sender})}

    def text(self, text):
        return self.ui.handle(self.event(text))[1]

    def click(self, data):
        return self.ui.handle(self.event(data, callback=True))[1]

    def key(self, action):
        return action + ':' + self.store.ui_state(42)['token']

    def pick(self, index=0):
        return self.click(self.key('pick') + ':' + str(index))

    def job(self, chapter=1, status='queued', user=42):
        job, _ = self.store.enqueue('story', chapter, self.profiles['story'], user, user, time.time())
        if status != 'queued':
            self.store.finish(job['id'], status)
        return job['id']

    def buttons(self, screen):
        return [b for row in screen['reply_markup']['inline_keyboard'] for b in row]

    def test_home_and_bare_commands_start_guides(self):
        screen = self.text('/start')
        self.assertIn('Bảng điều khiển', screen['text'])
        self.assertTrue(any(b['callback_data'] == 'new' for b in self.buttons(screen)))
        self.assertIn('Bước 1', self.text('/run')['text'])
        self.assertIn('Bước 1', self.text('/plan')['text'])
        self.assertIn('Nhập các ID', self.text('/cancel')['text'])
        self.assertIn('Dọn lịch sử', self.text('/clear')['text'])
        self.assertEqual(self.store.list(42), [])

    def test_run_requires_confirmation_and_repeated_click_is_safe(self):
        self.click('flow:run')
        self.pick()
        preview = self.text('21')
        self.assertIn('Chương 21', preview['text'])
        self.assertIn('Xác nhận', str(preview))
        self.assertEqual(self.store.list(42), [])
        token = self.key('confirm')
        event = self.event(token, callback=True)
        first = self.ui.handle(event)
        self.assertEqual(first, self.ui.handle(event))
        self.click(token)  # Different update ID for a double tap on the same button.
        self.assertEqual(len(self.store.list(42)), 1)
        self.assertEqual(self.store.list(42)[0]['chapter'], 21)

    def test_wizard_restart_and_invalid_input_preserve_prompt(self):
        self.text('/run')
        self.pick()
        screen = self.text('not-a-number')
        self.assertIn('Nhập số chương', screen['text'])
        self.ui = TelegramUI(self.controller)
        screen = self.text('12')
        self.assertIn('Chương 12', screen['text'])
        self.click(self.key('confirm'))
        self.assertEqual(self.store.list(42)[0]['chapter'], 12)

    def test_preview_back_then_change_chapter_invalidates_old_confirm(self):
        self.text('/run')
        self.pick()
        self.text('12')
        old = self.key('confirm')
        self.click(self.key('back'))
        self.text('13')
        self.assertIn('đã cũ', self.click(old)['text'])
        self.assertEqual(self.store.list(42), [])
        self.click(self.key('confirm'))
        self.assertEqual(self.store.list(42)[0]['chapter'], 13)

    def test_cancel_and_clear_require_confirmation(self):
        one = self.job()
        self.click(f'action:cancel:{one}')
        self.assertEqual(self.store.get(one)['status'], 'queued')
        self.click(self.key('confirm'))
        self.assertEqual(self.store.get(one)['status'], 'cancelled')
        self.click('clean:finished')
        self.assertEqual(len(self.store.list(42)), 1)
        self.click(self.key('confirm'))
        self.assertEqual(self.store.list(42), [])
        self.assertIsNotNone(self.store.get(one))

    def test_bulk_cancel_preview_and_ownership(self):
        one = self.job()
        two = self.job(2)
        other = self.job(3, user=43)
        self.text('/cancel')
        self.text(f'{one} {two} {other}')
        self.click(self.key('confirm'))
        self.assertEqual(self.store.get(one)['status'], 'cancelled')
        self.assertEqual(self.store.get(two)['status'], 'cancelled')
        self.assertEqual(self.store.get(other)['status'], 'queued')

    def test_schedule_distinguishes_start_time_from_publish(self):
        screen = self.click('new')
        self.assertIn('không phải giờ công khai', screen['text'])
        self.click('flow:schedule')
        self.pick()
        self.text('3')
        screen = self.text('2020-01-01 00:00')
        self.assertIn('giờ bắt đầu xử lý', screen['text'])
        self.text('2099-01-02 19:30')
        self.click(self.key('confirm'))
        job = self.store.list(42)[0]
        self.assertIsNone(job['publish_at'])
        self.assertGreater(job['run_at'], time.time())

    def test_daily_flow_previews_all_chapters_and_deduplicates_after_crash(self):
        self.text('/plan')
        self.pick()
        self.text('10')
        self.text('2099-01-02')
        screen = self.click(self.key('days') + ':3')
        self.assertIn('15 chương / 3 ngày', screen['text'])
        self.assertIn('Chương 24', screen['text'])
        self.assertEqual(self.store.list(42), [])
        event = self.event(self.key('confirm'), callback=True)
        # Simulate a crash after queue commit but before the UI receipt/state commit.
        with patch.object(self.store, 'ui_commit', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                self.ui.handle(event)
        self.ui = TelegramUI(self.controller)
        self.ui.handle(event)
        self.assertEqual(self.store.list_page(42)[1], 15)

    def test_retry_retime_and_contextual_actions(self):
        one = self.job(status='failed')
        screen = self.click(f'job:{one}')
        self.assertTrue(any(b.get('callback_data') == f'action:retime:{one}' for b in self.buttons(screen)))
        self.click(f'action:retime:{one}')
        self.text('2099-01-02 19:30')
        self.click(self.key('confirm'))
        job = self.store.get(one)
        self.assertEqual(job['status'], 'queued')
        self.assertEqual(json.loads(job['settings'])['youtube_publish_at'], '2099-01-02T12:30:00Z')
        screen = self.click(f'job:{one}')
        self.assertFalse(any('retry' in b.get('callback_data', '') for b in self.buttons(screen)))

    def test_jobs_filter_pagination_clear_and_other_user(self):
        for chapter in range(1, 24):
            self.job(chapter, status='failed' if chapter % 2 else 'succeeded')
        self.job(24, user=43)
        self.store.clear('1', 42)
        screen = self.text('/status')
        self.assertIn('Trang 1/3 · 22 job', screen['text'])
        self.assertTrue(any(b.get('callback_data') == 'jobs:all:2' for b in self.buttons(screen)))
        screen = self.click('jobs:all:3')
        self.assertIn('Trang 3/3', screen['text'])
        self.assertIn('11 job', self.click('jobs:failed:1')['text'])
        self.assertIn('Không có job', self.click('jobs:active:1')['text'])
        self.assertNotIn('Job #24', self.click('job:24')['text'])

    def test_stale_expired_malicious_and_unauthorized_callbacks(self):
        for event in (self.event('home', callback=True, user=99),
                      self.event('home', callback=True, group=True)):
            self.assertIsNone(self.ui.handle(event))
        self.text('/run')
        data = self.key('pick') + ':0'
        with patch('src.remote.ui.time.time', return_value=time.time() + 1900):
            self.assertIn('hết hạn', self.click(data)['text'])
        screen = self.click('action:cancel:1;rm')
        self.assertIn('Chưa thể', screen['text'])
        self.assertEqual(self.store.list(42), [])

    def test_state_isolated_and_abort_discards_draft(self):
        self.text('/run')
        self.pick()
        self.text('5')
        token = self.key('confirm')
        self.ui.handle(self.event('home', callback=True, user=43))
        self.assertIsNotNone(self.store.ui_state(42))
        self.text('/abort')
        self.assertIn('đã cũ', self.click(token)['text'])
        self.assertEqual(self.store.list(42), [])

    def test_run_now_button_confirms_and_bypasses_schedule_and_upload_pause(self):
        self.store.enqueue_daily(123, 'story', [(1, '2099-01-02T19:30:00+07:00')], {}, 42, 42)
        self.store.pause_uploads(time.time() + 86400)
        screen = self.click('job:1')
        self.assertTrue(any(b.get('callback_data') == 'action:now:1' for b in self.buttons(screen)))
        screen = self.click('action:now:1')
        self.assertIn('Upload private, không đặt lịch', screen['text'])
        self.assertIsNone(self.store.claim())
        self.click(self.key('confirm'))
        restored = BotStore(self.store.path)
        job = restored.claim()
        self.assertEqual(job['id'], 1)
        self.assertEqual(job['manual_now'], 1)
        settings = json.loads(job['settings'])
        self.assertTrue(settings['manual_upload_now'])
        self.assertNotIn('youtube_publish_at', settings)
        self.assertEqual(settings['youtube_privacy'], 'private')
        self.assertGreater(restored.upload_pause_until(), time.time())

    def test_now_failed_expired_job_and_access_guards(self):
        self.store.enqueue('story', 1, {'youtube_publish_at': '2020-01-01T00:00:00Z'}, 42, 42, time.time())
        self.store.finish(1, 'failed')
        self.assertFalse(self.store.retry(1, 43, immediate=True))
        self.assertIn('Đã ưu tiên', self.text('/now 1')['text'])
        self.assertEqual(self.store.claim()['id'], 1)
        self.assertFalse(self.store.retry(1, 42, immediate=True))
        self.store.finish(1, 'succeeded')
        self.assertFalse(self.store.retry(1, 42, immediate=True))

    def test_manual_now_priority_does_not_start_parallel_job(self):
        self.job(1)
        self.job(2)
        self.job(3, status='failed')
        self.store.retry(3, 42, immediate=True)
        self.assertEqual(self.store.claim()['id'], 3)
        # Work is still consumed by the existing single serial worker.
        self.assertEqual(self.store.get(1)['status'], 'queued')
        self.assertEqual(self.store.get(2)['status'], 'queued')

    def test_plain_commands_remain_available(self):
        screen = self.text('/run story 7')
        self.assertIn('Job #', screen['text'])
        self.assertEqual(self.store.list(42)[0]['chapter'], 7)
        self.text('/cancel 1')
        self.assertEqual(self.store.get(1)['status'], 'cancelled')

    def test_many_profiles_buttons_are_bounded_and_paged(self):
        self.controller.profiles = {f'story_{i}': {} for i in range(25)}
        screen = self.text('/run')
        self.assertEqual(sum(b['callback_data'].startswith('pick:') for b in self.buttons(screen)), 8)
        screen = self.click(self.key('storiespage') + ':1')
        self.assertIn('story_8', str(screen))
        for b in self.buttons(screen):
            self.assertLessEqual(len(b['callback_data'].encode()), 64)

    def test_app_acknowledges_and_edits_callbacks_without_duplicate_work(self):
        messenger = Mock()
        messenger.send.return_value = 200
        app = BotApplication(self.store, self.controller, messenger, Mock(), ui=self.ui)
        event = self.event('jobs:all:1', callback=True)
        messenger.poll.return_value = [event]
        app.poll_once()
        messenger.answer_callback.assert_called_once_with(event['callback_query']['id'])
        self.assertEqual(messenger.send.call_args.args[2], 100)
        self.assertIn('reply_markup', messenger.send.call_args.kwargs)

    def test_navigation_from_progress_does_not_get_overwritten_by_worker(self):
        one = self.job()
        self.store.notified(one, 100, self.store.get(one)['updated_at'])
        messenger = Mock()
        event = self.event('home', callback=True)
        messenger.poll.return_value = [event]
        app = BotApplication(self.store, self.controller, messenger, Mock(), ui=self.ui)
        app.poll_once()
        self.assertIsNone(messenger.send.call_args.args[2])
        self.assertEqual(self.store.get(one)['message_id'], 100)

    def test_local_job_hides_publish_action_and_invalid_command_is_targeted(self):
        job, _ = self.store.enqueue('local', 1, {'upload_youtube': False}, 42, 42, time.time())
        self.store.finish(job['id'], 'failed')
        screen = self.click(f'job:{job["id"]}')
        self.assertFalse(any('retime' in b.get('callback_data', '') for b in self.buttons(screen)))
        screen = self.text('/cancel 1 nope')
        self.assertIn('Cú pháp: /cancel', screen['text'])
        self.assertNotIn('/schedule-day', screen['text'])

    def test_app_outage_replays_same_confirmation(self):
        self.text('/run')
        self.pick()
        self.text('1')
        event = self.event(self.key('confirm'), callback=True)
        messenger = Mock()
        messenger.poll.return_value = [event]
        messenger.send.side_effect = RuntimeError('offline')
        app = BotApplication(self.store, self.controller, messenger, Mock(), ui=self.ui)
        app.poll_once()
        self.assertEqual(self.store.offset(), 0)
        messenger.send.side_effect = None
        app.poll_once()
        self.assertEqual(len(self.store.list(42)), 1)
        self.assertEqual(self.store.offset(), event['update_id'] + 1)


class UITransportTests(unittest.TestCase):
    def test_callback_poll_command_menu_and_long_messages(self):
        calls = []
        def handle(request):
            payload = json.loads(request.content)
            calls.append((request.url.path.rsplit('/', 1)[1], payload))
            return httpx.Response(200, json={'ok': True, 'result': {'message_id': len(calls)}})
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            messenger = TelegramMessenger('fake', client=client)
            messenger.poll(0)
            messenger.answer_callback('query')
            messenger.configure_commands(COMMANDS, [42])
            text = '📚' * 2500 + 'tail'
            markup = {'inline_keyboard': [[{'text': 'Menu', 'callback_data': 'home'}]]}
            messenger.send(42, text, reply_markup=markup)
        self.assertIn('callback_query', calls[0][1]['allowed_updates'])
        self.assertEqual(calls[1][0], 'answerCallbackQuery')
        self.assertEqual(calls[2][1]['scope'], {'type': 'chat', 'chat_id': 42})
        sends = [p for method, p in calls if method == 'sendMessage']
        self.assertEqual(''.join(p['text'] for p in sends), text)
        self.assertTrue(all(len(p['text'].encode('utf-16-le')) // 2 <= 3500 for p in sends))
        self.assertEqual(sends[-1]['reply_markup'], markup)

    def test_edit_network_failure_does_not_send_duplicate_message(self):
        methods = []
        def handle(request):
            methods.append(request.url.path.rsplit('/', 1)[1])
            return httpx.Response(429, json={'ok': False, 'error_code': 429, 'description': 'Too many requests'})
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(RuntimeError):
                TelegramMessenger('fake', client=client).send(42, 'hello', 100)
        self.assertEqual(methods, ['editMessageText'])
