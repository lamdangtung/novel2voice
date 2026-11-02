"""Five sequential chapters/day with explicit local publish slots."""
from datetime import datetime, timedelta, timezone as utc_timezone
from zoneinfo import ZoneInfo
import re

DEFAULT_PUBLISH_TIMES = ('06:30', '11:30', '17:00', '19:30', '22:00')


def validate_times(times):
    if not isinstance(times, (list, tuple)) or len(times) != 5:
        raise ValueError('daily_publish_times cần đúng 5 mốc HH:MM.')
    if any(not isinstance(t, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in times):
        raise ValueError('Khung giờ publish phải có dạng HH:MM.')
    if list(times) != sorted(set(times)):
        raise ValueError('Khung giờ publish phải khác nhau và tăng dần.')
    return tuple(times)


def plan_daily(start_chapter, date, days=1, *, times=DEFAULT_PUBLISH_TIMES,
               timezone='Asia/Ho_Chi_Minh', now=None):
    times = validate_times(times)
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError('Mỗi lệnh hỗ trợ từ 1 đến 7 ngày.')
    if type(start_chapter) is not int or not 1 <= start_chapter <= 1_000_000 - days * 5 + 1:
        raise ValueError('Số chương không hợp lệ.')
    start = datetime.strptime(date, '%Y-%m-%d').date()
    if start.year >= 9999:
        raise ValueError('Ngày publish nằm ngoài phạm vi hỗ trợ.')
    zone = ZoneInfo(timezone)
    current = now if now is not None else datetime.now(utc_timezone.utc)
    result = []
    for day in range(days):
        for index, slot in enumerate(times):
            instant = datetime.combine(start + timedelta(days=day), datetime.strptime(slot, '%H:%M').time(), tzinfo=zone)
            if instant <= current:
                raise ValueError('Có giờ publish đã qua; chọn ngày tương lai để giữ đủ 5 chương/ngày.')
            result.append((start_chapter + day * 5 + index, instant.isoformat()))
    return result
