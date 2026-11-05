"""Shared presentation limit for YouTube titles from every metadata source."""
import logging
import re
import unicodedata

MAX_TITLE_LENGTH = 100
logger = logging.getLogger(__name__)


def normalize_title(value):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '<>'):
        raise ValueError('Tiêu đề phải là chuỗi không rỗng và không chứa < >.')
    cleaned = re.sub(r'\.{3,}|…+', ' ', unicodedata.normalize('NFC', value))
    title = ' '.join(cleaned.split())
    if not title:
        raise ValueError('Tiêu đề không được chỉ chứa dấu ba chấm.')
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    prefix = title[:MAX_TITLE_LENGTH]
    # Prefer a word boundary, without reducing a title to a tiny fragment when
    # it contains one very long token. Do not append an ellipsis.
    boundary = prefix.rfind(' ')
    if len(title) > len(prefix) and not title[len(prefix)].isspace() and boundary >= MAX_TITLE_LENGTH // 2:
        prefix = prefix[:boundary]
    shortened = prefix.rstrip(' |–—-')
    logger.warning('Tiêu đề YouTube được rút gọn từ %s xuống %s ký tự.', len(title), len(shortened))
    return shortened
