import json
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.translation_providers.deepseek_scheduler import DeepSeekScheduler
from src.translation_providers.deepseek import DeepSeekTranslationProvider


class FakeTime:
    def __init__(self, value=10000):
        self.value = value
        self.sleeps = []
    def now(self): return self.value
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


def process_slot(directory, count, maximum, times, gate_start):
    # Test clock advances without real API pacing waits; real OS locks still serialize.
    def now():
        with times.get_lock():
            return times.value
    def sleep(seconds):
        with times.get_lock():
            times.value += seconds
    gate_start.wait(5)
    scheduler = DeepSeekScheduler(directory, min_gap=10, max_gap=10, clock=now, sleep=sleep,
                                 uniform=lambda low, high: low)
    with scheduler.slot():
        with count.get_lock():
            count.value += 1
            maximum.value = max(maximum.value, count.value)
        time.sleep(.03)
        with count.get_lock():
            count.value -= 1


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.clock = FakeTime()

    def gate(self, **kwargs):
        return DeepSeekScheduler(self.directory, min_gap=20, max_gap=45,
            clock=self.clock.now, sleep=self.clock.sleep, uniform=lambda low, high: low, **kwargs)

    def test_gap_is_from_completion_and_shared_by_new_instances(self):
        with self.gate().slot():
            self.clock.value += 100  # Slow model call.
        completed = self.clock.now()
        with self.gate().slot():
            self.assertGreaterEqual(self.clock.now() - completed, 20)
        self.assertGreater(len(self.clock.sleeps), 0)

    def test_jitter_stays_within_configured_bounds(self):
        gate = DeepSeekScheduler(self.directory, min_gap=20, max_gap=45,
            clock=self.clock.now, sleep=self.clock.sleep, uniform=lambda low, high: high)
        with gate.slot(): pass
        completed = self.clock.now()
        with gate.slot():
            self.assertEqual(self.clock.now() - completed, 45)

    def test_sliding_minute_limit_prevents_burst(self):
        gate = self.gate(per_minute=1)
        with gate.slot(): pass
        first = self.clock.now()
        with gate.slot():
            self.assertGreaterEqual(self.clock.now() - first, 60)

    def test_sliding_hour_limit_persists(self):
        with self.gate(per_hour=1).slot(): pass
        first = self.clock.now()
        with self.gate(per_hour=1).slot():
            self.assertGreaterEqual(self.clock.now() - first, 3600)
        self.assertTrue(all(seconds <= 30 for seconds in self.clock.sleeps))

    def test_failure_backoff_retry_after_and_success_reset(self):
        error = RuntimeError('rate limited')
        error.response = Mock(headers={'Retry-After': '600'})
        with self.assertRaises(RuntimeError):
            with self.gate().slot():
                raise error
        failed_at = self.clock.now()
        with self.assertRaises(RuntimeError):
            with self.gate().slot():
                self.assertGreaterEqual(self.clock.now() - failed_at, 600)
                raise RuntimeError('again')
        state = json.loads((self.directory / 'requests.json').read_text())
        self.assertEqual(state['failures'], 2)
        self.assertGreaterEqual(state['not_before'] - self.clock.now(), 240)
        with self.gate().slot(): pass
        self.assertEqual(json.loads((self.directory / 'requests.json').read_text())['failures'], 0)

    def test_inflight_crash_marker_requires_cooldown(self):
        self.directory.joinpath('requests.json').write_text(json.dumps({
            'starts': [9000], 'not_before': 0, 'failures': 0, 'inflight': True}))
        started = self.clock.now()
        with self.gate().slot():
            self.assertGreaterEqual(self.clock.now() - started, 120)

    def test_corrupt_state_fails_closed(self):
        self.directory.joinpath('requests.json').write_text('bad JSON')
        with self.assertRaises(RuntimeError):
            with self.gate().slot():
                self.fail('must not issue request')

    def test_minimum_gap_cannot_be_disabled(self):
        for gap in (0, 1, 9, float('nan')):
            with self.assertRaises(ValueError):
                DeepSeekScheduler(self.directory, min_gap=gap)

    def test_provider_initialization_and_completion_are_inside_slot(self):
        entered = []
        from contextlib import contextmanager
        class Scheduler:
            @contextmanager
            def slot(self):
                entered.append(True)
                try: yield
                finally: entered.pop()
        client = Mock()
        def chat(*args, **kwargs):
            self.assertTrue(entered)
            return Mock(text='VI', conversation_id='chat:1')
        client.chat.side_effect = chat
        provider = DeepSeekTranslationProvider(client=client, scheduler=Scheduler())
        self.assertEqual(provider.generate(system_prompt='S', user_prompt='U'), 'VI')
        self.assertEqual(entered, [])

    def test_two_processes_never_overlap(self):
        ctx = multiprocessing.get_context('spawn')
        count, maximum, clock = ctx.Value('i', 0), ctx.Value('i', 0), ctx.Value('d', 10000)
        event = ctx.Event()
        workers = [ctx.Process(target=process_slot, args=(str(self.directory), count, maximum, clock, event))
                   for _ in range(2)]
        try:
            for worker in workers: worker.start()
            event.set()
            for worker in workers:
                worker.join(timeout=10)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual(maximum.value, 1)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()

    def test_wait_boundary_never_passes_negative_time_to_sleep(self):
        from unittest.mock import Mock
        clock = Mock(side_effect=[0, .99, 1.01])
        waits = []
        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            waits.append(seconds)
        gate = DeepSeekScheduler(self.directory, clock=clock, sleep=sleep)
        gate._wait_until(1)
        self.assertTrue(all(value >= 0 for value in waits))
