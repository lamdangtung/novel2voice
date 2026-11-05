"""Strict, timezone-aware YouTube publication timestamps."""
from datetime import datetime, timezone, timedelta


def parse_publish_at(value):
    if not isinstance(value, str):
        raise ValueError('publish_at phải là timestamp ISO 8601 có múi giờ.')
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('publish_at không hợp lệ; ví dụ 2026-11-04T06:30:00+07:00.') from None
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('publish_at bắt buộc có múi giờ.')
    return instant


def normalize_publish_at(value):
    return parse_publish_at(value).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def require_future(value, *, buffer_seconds=0):
    if parse_publish_at(value) <= datetime.now(timezone.utc) + timedelta(seconds=buffer_seconds):
        raise ValueError('Đã lỡ giờ publish hoặc không còn đủ thời gian đệm; không tiếp tục upload. Dùng /retry <job_id> YYYY-MM-DD HH:MM để đặt giờ publish mới (giờ Việt Nam). Nếu video đã upload, đổi lịch trong YouTube Studio.')
