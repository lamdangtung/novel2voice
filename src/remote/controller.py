"""Authorized Telegram commands with explicit local-time scheduling."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

HELP = '''/stories — danh sách truyện
/run <truyện> <chương> — chạy ngay
/schedule <truyện> <chương> YYYY-MM-DD HH:MM — hẹn giờ
/status [job_id] — xem tiến độ/ETA
/cancel <job_id> — hủy lịch chưa chạy
/retry <job_id> — chạy lại job lỗi/bị ngắt
Mỗi job xử lý một chương thành một video. Lịch là giờ Việt Nam (Asia/Ho_Chi_Minh).'''

STAGES = {'fetch': 'Lấy truyện', 'translate': 'Dịch / glossary', 'tts': 'Tạo audio',
          'metadata': 'Tạo metadata', 'render': 'Render video', 'upload': 'Upload YouTube'}


def format_job(job, timezone='Asia/Ho_Chi_Minh'):
    labels = {'queued': 'Chờ chạy', 'running': 'Đang chạy', 'succeeded': 'Hoàn thành',
              'failed': 'Lỗi', 'cancelled': 'Đã hủy', 'interrupted': 'Bị ngắt'}
    lines = [f"Job #{job['id']} · {job['profile']} · Chương {job['chapter']}", labels[job['status']]]
    progress = json.loads(job['progress'])
    if job['status'] == 'queued':
        lines.append('Lịch: ' + datetime.fromtimestamp(job['run_at'], ZoneInfo(timezone)).strftime('%d/%m/%Y %H:%M'))
        lines.append('Job đến giờ sẽ xếp hàng nếu máy còn bận.')
    elif job['status'] == 'running' and progress:
        lines.append(f"{STAGES.get(progress['stage'], progress['stage'])}: {progress['fraction']:.0%}")
        if progress.get('unit') == 'byte':
            lines.append(f"Upload: {progress['current'] / 1024**2:.1f}/{progress['total'] / 1024**2:.1f} MiB")
        else:
            lines.append(f"{progress['current']:.0f}/{progress['total']:.0f} {progress.get('unit', '')}")
        lines.append(f"Toàn luồng: ~{progress['overall']:.0%} (ước tính)")
        eta = progress.get('eta_at')
        if eta and eta > time.time():
            lines.append('Dự kiến xong: ~' + datetime.fromtimestamp(eta, ZoneInfo(timezone)).strftime('%H:%M:%S'))
        else:
            lines.append('ETA: đang thu thập dữ liệu / tính lại.')
    if job.get('result'):
        result = json.loads(job['result'])
        lines += result.get('youtube', []) or ['Video: ' + p for p in result.get('videos', [])]
    if job.get('error'):
        lines.append('Lỗi: ' + job['error'])
    return '\n'.join(lines)


class BotController:
    def __init__(self, store, profiles, allowed_users, *, timezone='Asia/Ho_Chi_Minh'):
        if not allowed_users:
            raise ValueError('Cần ít nhất một TELEGRAM_ALLOWED_USER_IDS.')
        self.store, self.profiles = store, profiles
        self.allowed_users, self.timezone = set(allowed_users), timezone

    def handle(self, update):
        message = update.get('message', {})
        user = message.get('from', {})
        chat = message.get('chat', {})
        if (chat.get('type') != 'private' or user.get('id') not in self.allowed_users
                or user.get('is_bot') or chat.get('id') != user.get('id')):
            return None
        old = self.store.receipt(update['update_id'])
        if old is not None:
            return chat['id'], old
        text = message.get('text', '')
        parts = text.split() if isinstance(text, str) else []
        try:
            reply = self._command(parts, user['id'], chat['id'])
        except (ValueError, KeyError, IndexError):
            reply = 'Lệnh không hợp lệ hoặc không tìm thấy job/truyện.\n' + HELP
        self.store.receipt(update['update_id'], reply)
        return chat['id'], reply

    def _command(self, parts, user, chat):
        if not parts or parts[0] in {'/start', '/help'}:
            return HELP
        command = parts[0].split('@')[0]
        if command == '/stories' and len(parts) == 1:
            return '\n'.join(f"{key}: upload={entry.get('upload_youtube', True)}, privacy={entry.get('youtube_privacy', 'private')}"
                             for key, entry in self.profiles.items())
        if command in {'/run', '/schedule'}:
            if len(parts) != (3 if command == '/run' else 5):
                raise ValueError()
            profile, chapter = parts[1], int(parts[2])
            if not 1 <= chapter <= 1_000_000 or profile not in self.profiles:
                raise ValueError()
            run_at = time.time()
            if command == '/schedule':
                local = datetime.strptime(parts[3] + ' ' + parts[4], '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(self.timezone))
                run_at = local.timestamp()
                if run_at <= time.time():
                    return 'Thời gian hẹn phải ở tương lai (giờ Việt Nam).'
            job, created = self.store.enqueue(profile, chapter, self.profiles[profile], user, chat, run_at)
            if job['user_id'] != user:
                return 'Chương này đã được xếp hàng hoặc xử lý bởi người dùng khác.'
            return ('Đã tạo lịch/job.\n' if created else 'Chương này đã có job, không tạo trùng.\n') + format_job(job, self.timezone)
        if command == '/status' and len(parts) in (1, 2):
            if len(parts) == 2:
                job = self.store.get(int(parts[1]), user)
                if not job:
                    raise ValueError()
                return format_job(job, self.timezone)
            return '\n\n'.join(format_job(j, self.timezone) for j in self.store.list(user)) or 'Chưa có job.'
        if command in {'/cancel', '/retry'} and len(parts) == 2:
            job_id = int(parts[1])
            success = self.store.cancel(job_id, user) if command == '/cancel' else self.store.retry(job_id, user)
            return ('Đã hủy lịch.' if command == '/cancel' else 'Đã xếp hàng chạy lại.') if success else 'Không thể thực hiện; kiểm tra /status. Chỉ hủy job chưa chạy.'
        return HELP
