import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from src.remote.controller import BotController
from src.remote.scheduling import plan_daily, validate_times
from src.remote.store import BotStore
from src.publishing.base import UploadSpec
from src.publishing.jobs import PublishingRunner
from src.publishing.metadata import build_upload_spec
from src.publishing.youtube import YouTubePublisher
from src.publishing.schedule import normalize_publish_at


def message(text, update_id=1):
    return {'update_id': update_id, 'message': {'text': text, 'from': {'id': 42},
                                              'chat': {'id': 42, 'type': 'private'}}}


class DailyPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = BotStore(self.root / 'bot.sqlite3')
        self.controller = BotController(self.store, {'story': {'upload_youtube': True}}, [42])

    def test_five_slots_vietnam_time(self):
        plan = plan_daily(10, '2099-01-01')
        self.assertEqual([chapter for chapter, _ in plan], [10, 11, 12, 13, 14])
        self.assertEqual([when[11:16] for _, when in plan], ['06:30', '11:30', '17:00', '19:30', '22:00'])
        self.assertTrue(all(when.endswith('+07:00') for _, when in plan))
        self.assertEqual(normalize_publish_at(plan[0][1]), '2098-12-31T23:30:00Z')

    def test_multiple_days_and_year_rollover(self):
        plan = plan_daily(101, '2099-12-31', days=2)
        self.assertEqual(len(plan), 10)
        self.assertEqual(plan[-1][0], 110)
        self.assertIn('2100-01-01T22:00', plan[-1][1])

    def test_reject_past_slots_bad_counts_and_bad_times(self):
        for kwargs in ({'days': 0}, {'days': 8}, {'start_chapter': 0}):
            args = {'start_chapter': 1, 'date': '2099-01-01', **kwargs}
            with self.assertRaises(ValueError):
                plan_daily(**args)
        with self.assertRaises(ValueError):
            plan_daily(1, '2099-01-01', now=datetime(2099, 1, 1, 1, tzinfo=timezone.utc))
        for times in (['06:30'] * 5, ['25:00'] * 5, ['06:30'], ['22:00', '19:30', '17:00', '11:30', '06:30']):
            with self.assertRaises(ValueError):
                validate_times(times)

    def test_command_prepares_jobs_only_within_24_hours_of_publication(self):
        reply = self.controller.handle(message('/schedule-day story 10 2099-01-01'))[1]
        self.assertIn('5 job', reply)
        for job_id in range(1, 6):
            job = self.store.get(job_id)
            self.assertEqual(job['chapter'], job_id + 9)
            self.assertEqual(json.loads(job['settings'])['youtube_privacy'], 'private')
            self.assertIn('2099-01-01T', json.loads(job['settings'])['youtube_publish_at'])
        self.assertIsNone(self.store.claim())
        first = self.store.get(1)
        self.assertIsNone(self.store.claim(now=first['publish_at'] - 86401))
        self.assertIsNotNone(self.store.claim(now=first['publish_at'] - 86400))
        status = self.controller.handle(message('/status 1', 2))[1]
        self.assertIn('YouTube công khai:', status)

    def test_redelivery_and_crash_recovery_do_not_duplicate_daily_jobs(self):
        plan = plan_daily(1, '2099-01-01')
        self.store.enqueue_daily(1, 'story', plan, {'upload_youtube': True}, 42, 42)
        self.controller.handle(message('/schedule-day story 1 2099-01-01'))
        self.assertEqual(len(self.store.list(42)), 5)
        self.controller.handle(message('/schedule-day story 1 2099-01-01'))
        self.assertEqual(len(self.store.list(42)), 5)

    def test_conflict_rolls_back_entire_group(self):
        self.store.enqueue('story', 3, {}, 42, 42, 0)
        reply = self.controller.handle(message('/schedule-day story 1 2099-01-01'))[1]
        self.assertIn('đã có job', reply)
        self.assertEqual(len(self.store.list(42)), 1)

    def test_daily_schedule_requires_upload_enabled(self):
        self.controller.profiles['story']['upload_youtube'] = False
        reply = self.controller.handle(message('/schedule-day story 1 2099-01-01'))[1]
        self.assertIn('tắt upload', reply)
        self.assertEqual(self.store.list(42), [])

    def test_json_and_pipeline_spec_preserve_publish_at(self):
        config = self.root / 'metadata.json'
        config.write_text(json.dumps({'publish_at': '2099-01-01T06:30:00+07:00', 'privacy': 'private'}))
        spec = build_upload_spec(self.root / 'video.mp4', channel_id='channel', metadata_file=config)
        self.assertEqual(spec.publish_at, '2099-01-01T06:30:00+07:00')
        PublishingRunner._validate(spec, check_media=False)
        from dataclasses import replace
        with self.assertRaises(ValueError):
            PublishingRunner._validate(replace(spec, privacy='public'), check_media=False)
        with self.assertRaises(ValueError):
            PublishingRunner._validate(replace(spec, publish_at='2099-01-01T06:30:00'), check_media=False)

    def test_youtube_insert_uses_private_and_utc_publish_at(self):
        http = Mock()
        http.request.return_value.status_code = 200
        http.request.return_value.headers = {'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'}
        publisher = YouTubePublisher(token_path=self.root / 'unused', session=http)
        spec = UploadSpec(self.root / 'video.mp4', 'Title', 'channel', publish_at='2099-01-01T06:30:00+07:00')
        publisher.start(spec, 100)
        status = http.request.call_args.kwargs['json']['status']
        self.assertEqual(status['privacyStatus'], 'private')
        self.assertEqual(status['publishAt'], '2098-12-31T23:30:00Z')

    def test_late_upload_does_not_initiate_or_publish_immediately(self):
        video = self.root / 'video.mp4'
        video.write_bytes(b'video')
        publisher = Mock()
        publisher.channel_id.return_value = 'channel'
        spec = UploadSpec(video, 'Title', 'channel', publish_at='2020-01-01T00:00:00Z')
        runner = PublishingRunner(publisher, self.root / 'state')
        with self.assertRaises(ValueError):
            runner.publish(spec)
        publisher.start.assert_not_called()

    def test_nearer_publish_day_is_prioritized_over_earlier_enqueued_batch(self):
        self.controller.handle(message('/schedule-day story 20 2099-01-05', 1))
        self.controller.handle(message('/schedule-day story 10 2099-01-01', 2))
        self.assertEqual(self.store.claim(now=datetime(2099, 1, 10, tzinfo=timezone.utc).timestamp())['chapter'], 10)

    def test_failed_chapter_cannot_create_new_daily_attempt(self):
        job, _ = self.store.enqueue('story', 3, {}, 42, 42, 0)
        self.store.finish(job['id'], 'failed', error='failure')
        reply = self.controller.handle(message('/schedule-day story 1 2099-01-01'))[1]
        self.assertIn('đã có job', reply)
        self.assertEqual(len(self.store.list(42)), 1)

    def test_old_database_migrates_publish_deadlines(self):
        import sqlite3
        path = self.root / 'legacy.sqlite3'
        # Recreate the previous schema by removing the new column from a fresh DB.
        BotStore(path)
        with sqlite3.connect(path) as db:
            db.execute('DROP INDEX jobs_ready')
            db.execute('ALTER TABLE jobs DROP COLUMN publish_at')
            for chapter, when in [(20, '2099-01-05T06:30:00+07:00'), (10, '2099-01-01T06:30:00+07:00')]:
                db.execute('INSERT INTO jobs(profile,chapter,settings,user_id,chat_id,run_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                    ('story', chapter, json.dumps({'youtube_publish_at': when}), 42, 42, 0, 0))
        migrated = BotStore(path)
        self.assertEqual(migrated.claim(now=datetime(2099, 1, 10, tzinfo=timezone.utc).timestamp())['chapter'], 10)
