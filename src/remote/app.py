"""Long-polling Telegram control with a separate, serial pipeline worker."""
import logging
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from src import config
from src.publishing.base import UploadLimitExceeded
from .controller import BotController, format_job
from .executor import FullPipelineExecutor, ProgressTracker
from .profiles import load_profiles
from .store import BotStore
from .transport import TelegramMessenger

logger = logging.getLogger(__name__)


def safe_error(error, secrets=()):
    message = str(error) or type(error).__name__
    for secret in secrets:
        if secret:
            message = message.replace(secret, '[redacted]')
    message = re.sub(r'https?://\S+', '[URL]', message)
    message = re.sub(r'(?i)bearer\s+\S+', 'Bearer [redacted]', message)
    return message[:600]


class BotApplication:
    def __init__(self, store, controller, messenger, executor, *, notify_interval=30, secrets=(), ui=None):
        self.store, self.controller, self.messenger, self.executor = store, controller, messenger, executor
        self.notify_interval, self.secrets = notify_interval, secrets
        self.ui = ui
        self.stop = threading.Event()

    def work_once(self):
        job = self.store.claim()
        if not job:
            return False
        if job['user_id'] not in self.controller.allowed_users:
            self.store.finish(job['id'], 'cancelled', error='Quyền điều khiển đã bị gỡ.')
            return True
        try:
            import json
            tracker = ProgressTracker(self.store, job, notify_interval=self.notify_interval)
            settings = json.loads(job['settings'])
            settings['_job_dir'] = str(self.store.path.parent / 'artifacts' / str(job['id']))
            result = self.executor.run(settings, job['chapter'], tracker)
            self.store.finish(job['id'], 'succeeded', result=result)
        except UploadLimitExceeded as error:
            self.store.pause_uploads(time.time() + 24 * 3600)
            self.store.finish(job['id'], 'failed', error=safe_error(error, self.secrets)
                + f" Dùng /retry {job['id']} để xếp lại; job chờ hết cooldown trước khi chạy.")
        except BaseException as error:
            self.store.finish(job['id'], 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                              error=safe_error(error, self.secrets))
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                self.stop.set()
        return True

    def flush_notifications(self):
        for job in self.store.notifications():
            if job['user_id'] not in self.controller.allowed_users:
                self.store.notified(job['id'], job['message_id'], job['updated_at'])
                continue
            try:
                if self.ui:
                    screen = self.ui.job_view(job)
                    message_id = self.messenger.send(job['chat_id'], screen['text'], job['message_id'], reply_markup=screen['reply_markup'])
                else:
                    message_id = self.messenger.send(job['chat_id'], format_job(job, self.controller.timezone), job['message_id'])
                self.store.notified(job['id'], message_id, job['updated_at'])
            except RuntimeError:
                # Keep notification pending; a Telegram outage must not restart a pipeline.
                logger.warning('Chưa gửi được tiến độ Telegram; sẽ thử lại.')

    def poll_once(self):
        offset = self.store.offset()
        for update in self.messenger.poll(offset):
            if update.get('update_id', -1) < offset:
                continue
            callback = update.get('callback_query')
            if self.ui and callback and self.ui.identity(update) is not None:
                try:
                    self.messenger.answer_callback(callback['id'])
                except RuntimeError:
                    logger.warning('Chưa xác nhận được nút bấm Telegram; vẫn xử lý thao tác.')
            result = self.ui.handle(update) if self.ui else self.controller.handle(update)
            if result:
                try:
                    if self.ui:
                        chat_id, screen = result
                        message_id = callback.get('message', {}).get('message_id') if callback else None
                        # Keep the dedicated progress card alive. Navigation from
                        # it opens a separate message so worker updates cannot
                        # overwrite the user's menu or confirmation screen.
                        if message_id and self.store.is_notification_message(chat_id, message_id):
                            message_id = None
                        self.messenger.send(chat_id, screen['text'], message_id, reply_markup=screen['reply_markup'])
                    else:
                        self.messenger.send(*result)
                except RuntimeError:
                    # Do not acknowledge the update yet. Command receipt prevents duplicate execution.
                    break
            offset = update['update_id'] + 1
            self.store.set_offset(offset)
        self.flush_notifications()

    def _worker(self):
        while not self.stop.is_set():
            try:
                if not self.work_once():
                    self.stop.wait(1)
            except Exception:
                logger.warning('Hàng đợi tạm thời lỗi; sẽ thử lại.')
                self.stop.wait(5)

    def run(self):
        self.store.recover()
        worker = threading.Thread(target=self._worker, name='novel2voice-worker')
        worker.start()
        try:
            while not self.stop.is_set():
                try:
                    self.poll_once()
                except RuntimeError as error:
                    logger.warning('%s Tự thử lại sau 5 giây.', safe_error(error, self.secrets))
                    self.stop.wait(5)
        except KeyboardInterrupt:
            logger.info('Dừng nhận lệnh; chờ job hiện tại kết thúc trước khi thoát.')
        finally:
            self.stop.set()
            worker.join()
            self.messenger.close()


@contextmanager
def instance_lock(path):
    import fcntl
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Bot đã chạy với state-dir này.')
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def run_bot(profiles_file, state_dir):
    token = config.TELEGRAM_BOT_TOKEN
    try:
        allowed = tuple(int(value.strip()) for value in config.TELEGRAM_ALLOWED_USER_IDS.split(',') if value.strip())
        interval = max(10, int(config.TELEGRAM_PROGRESS_INTERVAL_SECONDS))
    except ValueError:
        raise ValueError('TELEGRAM_ALLOWED_USER_IDS cần numeric ID; TELEGRAM_PROGRESS_INTERVAL_SECONDS cần số giây.') from None
    if any(value <= 0 for value in allowed):
        raise ValueError('Telegram user ID phải là số nguyên dương.')
    if not token or not allowed:
        raise ValueError('Cần TELEGRAM_BOT_TOKEN và TELEGRAM_ALLOWED_USER_IDS trong .env.')
    # httpx INFO logs include request URLs, which contain bot tokens.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    profiles = load_profiles(profiles_file)
    with instance_lock(Path(state_dir) / 'bot.lock'):
        store = BotStore(Path(state_dir) / 'bot.sqlite3')
        controller = BotController(store, profiles, allowed)
        messenger = TelegramMessenger(token)
        logger.info('Đang kiểm tra kết nối Telegram...')
        try:
            identity = messenger.identity()
        except Exception:
            messenger.close()
            raise
        logger.info('Telegram đã kết nối: @%s. Gửi /menu trong chat riêng để mở bảng điều khiển.', identity.get('username', 'bot'))
        from .ui import TelegramUI, COMMANDS
        try:
            messenger.configure_commands(COMMANDS, allowed)
        except RuntimeError:
            logger.warning('Chưa đăng ký được menu lệnh Telegram; /menu vẫn hoạt động.')
        application = BotApplication(store, controller, messenger, FullPipelineExecutor(), ui=TelegramUI(controller),
            notify_interval=interval,
            secrets=(token, config.OPENAI_API_KEY, config.HF_TOKEN))
        application.run()
