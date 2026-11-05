"""Authorized Telegram commands with explicit local-time scheduling."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

HELP = '''/menu — bảng điều khiển bằng nút bấm
/new — hướng dẫn chạy/hẹn giờ một chương
/plan — hướng dẫn lên lịch 5 chương/ngày
/abort — thoát thao tác đang nhập
/stories — danh sách truyện
/run <truyện> <chương> — chạy ngay
/schedule <truyện> <chương> YYYY-MM-DD HH:MM — hẹn giờ
/schedule-day <truyện> <chương_đầu> YYYY-MM-DD [số_ngày] — 5 chương/ngày
/status — danh sách job, trang đầu
/status page <số_trang> — xem trang khác
/status <job_id> — chi tiết tiến độ/ETA
/cancel <job_id> [job_id ...] — hủy một hoặc nhiều lịch chưa chạy
/now <job_id> — chạy/retry ngay, bỏ lịch và cooldown; upload private
/retry <job_id> [YYYY-MM-DD HH:MM] — chạy lại, tùy chọn đổi giờ publish
/clear <job_id|finished|failed> — dọn lịch sử job
Mỗi job xử lý một chương thành một video. Lịch là giờ Việt Nam (Asia/Ho_Chi_Minh).'''

STAGES = {'fetch': 'Lấy truyện', 'translate': 'Dịch / glossary', 'tts': 'Tạo audio',
          'metadata': 'Tạo metadata', 'render': 'Render video', 'upload': 'Upload YouTube'}


def format_job(job, timezone='Asia/Ho_Chi_Minh'):
    labels = {'queued': 'Chờ chạy', 'running': 'Đang chạy', 'succeeded': 'Hoàn thành',
              'failed': 'Lỗi', 'cancelled': 'Đã hủy', 'interrupted': 'Bị ngắt'}
    lines = [f"Job #{job['id']} · {job['profile']} · Chương {job['chapter']}", labels[job['status']]]
    settings = json.loads(job['settings'])
    if settings.get('youtube_publish_at'):
        from src.publishing.schedule import parse_publish_at
        lines.append('YouTube công khai: ' + parse_publish_at(settings['youtube_publish_at']).astimezone(ZoneInfo(timezone)).strftime('%d/%m/%Y %H:%M'))
    if settings.get('manual_upload_now'):
        lines.append('Chạy ngay: bỏ lịch/cooldown upload; video private, không đặt lịch. Vẫn giữ giới hạn LLM.')
    progress = json.loads(job['progress'])
    if job['status'] == 'queued':
        lines.append('Lịch: ' + datetime.fromtimestamp(job['run_at'], ZoneInfo(timezone)).strftime('%d/%m/%Y %H:%M'))
        lines.append('Đây là giờ bắt đầu xử lý; job xếp hàng nếu máy bận hoặc đang tạm giữ upload.')
    elif job['status'] == 'running' and progress:
        lines.append(f"{STAGES.get(progress['stage'], progress['stage'])}: {progress['fraction']:.0%}")
        if progress.get('unit') == 'byte':
            lines.append(f"Upload: {progress['current'] / 1024**2:.1f}/{progress['total'] / 1024**2:.1f} MiB")
        else:
            lines.append(f"{progress['current']:.0f}/{progress['total']:.0f} {progress.get('unit', '')}")
        lines.append(f"Toàn luồng: ~{progress['overall']:.0%} (ước tính)")
        eta = progress.get('eta_at')
        if eta and eta > time.time():
            lines.append('Dự kiến xong: ~' + datetime.fromtimestamp(eta, ZoneInfo(timezone)).strftime('%d/%m %H:%M'))
        else:
            lines.append('ETA: đang thu thập dữ liệu / tính lại.')
    if job['status'] == 'running' and not progress:
        lines.append('Đang khởi động; ETA sẽ xuất hiện khi có tiến độ.')
    if job.get('result'):
        result = json.loads(job['result'])
        lines += result.get('youtube', []) or ['Video: ' + p for p in result.get('videos', [])]
        if job['status'] == 'succeeded' and settings.get('youtube_publish_at') and result.get('youtube'):
            lines.append('Đã upload / đặt lịch; xem YouTube Studio để kiểm tra trạng thái công khai.')
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
            reply = self._command(parts, user['id'], chat['id'], request_id=update['update_id'])
        except (ValueError, KeyError, IndexError):
            reply = 'Lệnh không hợp lệ hoặc không tìm thấy job/truyện.\n' + HELP
        self.store.receipt(update['update_id'], reply)
        return chat['id'], reply

    def _command(self, parts, user, chat, request_id=None):
        if not parts or parts[0] in {'/start', '/help'}:
            return HELP
        command = parts[0].split('@')[0]
        if command == '/stories' and len(parts) == 1:
            return '\n'.join(f"{key}: upload={entry.get('upload_youtube', True)}, privacy={entry.get('youtube_privacy', 'private')}"
                             for key, entry in self.profiles.items())
        if command == '/schedule-day':
            from .scheduling import plan_daily, DEFAULT_PUBLISH_TIMES
            if len(parts) not in (4, 5) or parts[1] not in self.profiles:
                raise ValueError()
            profile = parts[1]
            settings = self.profiles[profile]
            if not settings.get('upload_youtube', True):
                return 'Profile này tắt upload YouTube; không thể hẹn giờ publish.'
            try:
                plan = plan_daily(int(parts[2]), parts[3], int(parts[4]) if len(parts) == 5 else 1,
                    times=settings.get('daily_publish_times', DEFAULT_PUBLISH_TIMES), timezone=self.timezone)
                jobs = self.store.enqueue_daily(request_id, profile, plan, settings, user, chat)
            except ValueError as error:
                return str(error)
            lines = [f'Đã tạo {len(jobs)} job, 5 chương/ngày (giờ Việt Nam).',
                     'Bot chuẩn bị trong 24 giờ trước mỗi mốc publish; YouTube giữ private đến giờ hẹn.']
            from src.publishing.schedule import parse_publish_at
            for job in jobs:
                instant = parse_publish_at(json.loads(job['settings'])['youtube_publish_at'])
                lines.append(f"#{job['id']} · Chương {job['chapter']} → " + instant.astimezone(ZoneInfo(self.timezone)).strftime('%d/%m %H:%M'))
            return '\n'.join(lines)
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
            note = 'Đã tạo lịch/job.\n' if created else 'Chương này đã có job, không tạo trùng.\n'
            if job['status'] in {'failed', 'interrupted'}:
                note += f"Dùng /retry {job['id']} để giữ checkpoint.\n"
            return note + format_job(job, self.timezone)
        if command == '/status' and len(parts) in (1, 2, 3):
            pause = self.store.upload_pause_until()
            header = ''
            if pause > time.time():
                header = ('YouTube đang tạm giữ upload do giới hạn kênh đến khoảng '
                    + datetime.fromtimestamp(pause, ZoneInfo(self.timezone)).strftime('%d/%m %H:%M')
                    + '. Đây là thời gian thử lại, không bảo đảm YouTube đã mở giới hạn.\n\n')
            if len(parts) == 2:
                job = self.store.get(int(parts[1]), user)
                if not job:
                    raise ValueError()
                return header + format_job(job, self.timezone)
            page = 1
            if len(parts) == 3:
                if parts[1] != 'page':
                    raise ValueError()
                page = int(parts[2])
                if page < 1:
                    return 'Số trang phải >= 1. Ví dụ: /status page 2'
            jobs, total = self.store.list_page(user, page)
            pages = max(1, (total + 9) // 10)
            if page > pages:
                return header + f'Trang {page} không tồn tại. Có {pages} trang. Dùng /status page {pages}'
            if not total:
                return header + 'Chưa có job.'
            lines = [header + f'Trang {page}/{pages} · {total} job · mới nhất trước']
            for job in jobs:
                # Keep list entries compact so Telegram does not truncate navigation.
                summary = format_job(dict(job, profile=job['profile'][:60]), self.timezone).splitlines()
                lines.append(summary[0] + ' · ' + summary[1])
                for line in summary[2:]:
                    if line.startswith(('YouTube công khai:', 'Lịch:', 'Toàn luồng:', 'Dự kiến xong:')):
                        lines.append(line)
            lines.append('Chi tiết: /status <job_id>')
            if page > 1:
                lines.append(f'Trang trước: /status page {page - 1}')
            if page < pages:
                lines.append(f'Trang sau: /status page {page + 1}')
            return '\n'.join(lines)
        if command == '/clear' and len(parts) == 2:
            target = parts[1]
            if target not in {'finished', 'failed'}:
                job = self.store.get(int(target), user)
                if not job:
                    return 'Không tìm thấy job của bạn.'
                if job['status'] == 'queued':
                    return f'Job đang chờ; dùng /cancel {job["id"]} trước khi /clear.'
                if job['status'] == 'running':
                    return 'Không thể dọn job đang chạy.'
            count = self.store.clear(target, user)
            return (f'Đã dọn {count} job khỏi danh sách. Giữ nguyên file, checkpoint và video/lịch YouTube. '
                    'Dấu vết nội bộ được giữ để tránh xử lý trùng; /run lại chương sẽ hiện lại job cũ (trừ job đã hủy).')
        if command == '/cancel' and len(parts) >= 2:
            # Validate the entire command before mutating any job.
            job_ids = list(dict.fromkeys(int(value) for value in parts[1:]))
            if any(job_id <= 0 for job_id in job_ids):
                raise ValueError()
            lines = []
            for job_id in job_ids:
                if self.store.cancel(job_id, user):
                    lines.append(f'#{job_id}: Đã hủy lịch.')
                    continue
                job = self.store.get(job_id, user)
                if not job:
                    reason = 'Không tìm thấy job của bạn.'
                elif job['status'] == 'running':
                    reason = 'Đang chạy, không thể hủy.'
                else:
                    reason = 'Không còn chờ chạy, không thể hủy.'
                lines.append(f'#{job_id}: {reason}')
            return '\n'.join(lines)
        if command == '/now' and len(parts) == 2:
            job_id = int(parts[1])
            if not self.store.retry(job_id, user, immediate=True):
                return 'Chỉ chạy ngay job đang chờ, lỗi hoặc bị ngắt của bạn; không chạy lại job đang chạy/đã hoàn thành.'
            return ('Đã ưu tiên chạy ngay. Nếu máy đang bận, job chờ luồng hiện tại kết thúc. '
                    'Bỏ giờ chờ, lịch publish và cooldown upload; video sẽ upload private, không đặt lịch. '
                    'Vẫn giữ giới hạn gọi LLM.\n' + format_job(self.store.get(job_id, user), self.timezone))
        if command == '/retry' and len(parts) in (2, 4):
            job_id = int(parts[1])
            publish_at = None
            if len(parts) == 4:
                publish_at = datetime.strptime(parts[2] + ' ' + parts[3], '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(self.timezone)).isoformat()
            try:
                success = self.store.retry(job_id, user, publish_at=publish_at)
            except ValueError as error:
                return str(error) + f'\nĐổi giờ publish: /retry {job_id} YYYY-MM-DD HH:MM (giờ Việt Nam, cách hiện tại hơn 15 phút).'
            if not success:
                return 'Không thể thực hiện; chỉ retry job lỗi/bị ngắt của bạn. Kiểm tra /status.'
            return 'Đã xếp hàng chạy lại.\n' + format_job(self.store.get(job_id, user), self.timezone)
        return HELP
