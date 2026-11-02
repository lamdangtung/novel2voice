"""Shared, persistent pacing for all native DeepSeek model requests.

The lock spans client initialization, the entire completion, and final state write.
Jitter spreads workload; it does not bypass upstream limits or account policies.
"""
import json
import logging
import math
import os
import random
import tempfile
import time
from contextlib import contextmanager
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import ContextManager, Protocol

from src import config

logger = logging.getLogger(__name__)


class RequestScheduler(Protocol):
    def slot(self) -> ContextManager[None]: ...


class DeepSeekScheduler:
    def __init__(self, directory, *, min_gap=20, max_gap=45, per_minute=3, per_hour=60,
                 cooldown_base=120, cooldown_max=1800, clock=time.time, sleep=time.sleep,
                 uniform=None):
        if (any(not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (min_gap, max_gap, cooldown_base, cooldown_max))
                or min_gap < 10 or max_gap < min_gap or cooldown_base < max_gap
                or cooldown_max < cooldown_base):
            raise ValueError('DeepSeek: min gap >= 10s; max >= min; cooldown base >= max gap; cooldown max >= base.')
        if (type(per_minute) is not int or type(per_hour) is not int
                or per_minute < 1 or per_hour < 1):
            raise ValueError('DeepSeek: giới hạn mỗi phút/giờ phải là số nguyên >= 1.')
        self.directory = Path(directory).resolve()
        self.min_gap, self.max_gap = min_gap, max_gap
        self.per_minute, self.per_hour = per_minute, per_hour
        self.cooldown_base, self.cooldown_max = cooldown_base, cooldown_max
        self.clock, self.sleep = clock, sleep
        self.uniform = uniform or random.SystemRandom().uniform

    def _read(self):
        path = self.directory / 'requests.json'
        if not path.exists():
            return {'starts': [], 'not_before': 0, 'failures': 0, 'inflight': False}
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(state, dict) or type(state['starts']) is not list
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in state['starts'])
                    or type(state['not_before']) not in (int, float) or not math.isfinite(state['not_before'])
                    or type(state['failures']) is not int or not 0 <= state['failures'] <= 30
                    or type(state['inflight']) is not bool):
                raise ValueError()
            return state
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('State điều phối DeepSeek bị lỗi; dừng gọi API để không bỏ qua giới hạn.') from None

    def _write(self, state):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                json.dump(state, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.directory / 'requests.json')
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _wait_until(self, target):
        remaining = target - self.clock()
        if remaining > .01:
            logger.info('DeepSeek: chờ khoảng %.0f giây trước lượt gọi tiếp theo.', remaining)
        while True:
            remaining = target - self.clock()
            if remaining <= 0:
                break
            self.sleep(min(30, remaining))

    def _retry_after(self, error):
        response = getattr(error, 'response', None)
        headers = getattr(response, 'headers', {}) or {}
        value = headers.get('Retry-After') or headers.get('retry-after')
        if not value:
            return 0
        try:
            seconds = float(value)
        except (ValueError, TypeError):
            try:
                instant = parsedate_to_datetime(value)
                if instant.tzinfo is None:
                    instant = instant.replace(tzinfo=timezone.utc)
                seconds = instant.timestamp() - self.clock()
            except (ValueError, TypeError, OverflowError):
                return 0
        return max(0, seconds) if math.isfinite(seconds) else 0

    @contextmanager
    def slot(self):
        import fcntl
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / 'requests.lock').open('a') as lock:
            # Separate open file descriptions serialize threads and processes alike.
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = self._read()
                now = self.clock()
                # Even after a long idle, take a fresh minimum pause. This also avoids
                # a clock jump bypassing the completion-to-start gap.
                target = max(state['not_before'], now + self.uniform(self.min_gap, self.max_gap)) if state['starts'] else state['not_before']
                if state['inflight']:
                    target = max(target, now + self.cooldown_base)
                while True:
                    self._wait_until(target)
                    now = self.clock()
                    state['starts'] = sorted(v for v in state['starts'] if v > now - 3600)
                    recent = [v for v in state['starts'] if v > now - 60]
                    targets = [now]
                    if len(recent) >= self.per_minute:
                        targets.append(recent[-self.per_minute] + 60)
                    if len(state['starts']) >= self.per_hour:
                        targets.append(state['starts'][-self.per_hour] + 3600)
                    target = max(targets)
                    if target <= now:
                        break
                state['starts'].append(now)
                state['inflight'] = True
                # Reserved before touching the client; an interrupted process leaves evidence.
                state['not_before'] = max(state['not_before'], now + self.cooldown_base)
                self._write(state)
                try:
                    yield
                except BaseException as error:
                    state['failures'] = min(30, state['failures'] + 1)
                    cooldown = min(self.cooldown_max, self.cooldown_base * 2 ** (state['failures'] - 1))
                    cooldown = max(cooldown, self._retry_after(error))
                    state['not_before'] = self.clock() + cooldown + self.uniform(0, self.max_gap - self.min_gap)
                    raise
                else:
                    state['failures'] = 0
                    state['not_before'] = self.clock() + self.uniform(self.min_gap, self.max_gap)
                finally:
                    state['inflight'] = False
                    self._write(state)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def get_deepseek_scheduler():
    return DeepSeekScheduler(config.DEEPSEEK_REQUEST_STATE_DIR,
        min_gap=config.DEEPSEEK_REQUEST_MIN_GAP_SECONDS,
        max_gap=config.DEEPSEEK_REQUEST_MAX_GAP_SECONDS,
        per_minute=config.DEEPSEEK_MAX_REQUESTS_PER_MINUTE,
        per_hour=config.DEEPSEEK_MAX_REQUESTS_PER_HOUR,
        cooldown_base=config.DEEPSEEK_COOLDOWN_BASE_SECONDS,
        cooldown_max=config.DEEPSEEK_COOLDOWN_MAX_SECONDS)
