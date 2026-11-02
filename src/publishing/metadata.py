"""Strict external metadata loading and offline upload-spec composition."""
import json
import re
import math
import subprocess
from pathlib import Path

from .base import UploadSpec

_FIELDS = {'title', 'description', 'privacy', 'tags', 'hashtags', 'category_id',
           'made_for_kids', 'thumbnail', 'default_language', 'default_audio_language',
           'contains_synthetic_media', 'notify_subscribers', 'chapters'}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'JSON có key trùng: {key}')
        result[key] = value
    return result


def _validate_fields(data):
    if not isinstance(data, dict):
        raise ValueError('Metadata phải là JSON object.')
    unknown = data.keys() - _FIELDS
    if unknown:
        raise ValueError('Metadata có trường chưa hỗ trợ: ' + ', '.join(sorted(unknown)))
    for key, value in data.items():
        if key in {'made_for_kids', 'notify_subscribers', 'contains_synthetic_media'}:
            if type(value) is not bool:
                raise ValueError(f'{key} phải là boolean true/false.')
        elif key in {'tags', 'hashtags'}:
            if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
                raise ValueError(f'{key} phải là array các string không rỗng.')
        elif key == 'chapters':
            if not isinstance(value, list):
                raise ValueError('chapters phải là array.')
        elif key == 'thumbnail' and value is None:
            continue
        elif not isinstance(value, str):
            raise ValueError(f'{key} phải là string.')
    if 'privacy' in data and data['privacy'] not in {'private', 'unlisted', 'public'}:
        raise ValueError('privacy phải là private, unlisted hoặc public.')
    for key in ('default_language', 'default_audio_language'):
        if key in data and not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', data[key]):
            raise ValueError(f'{key} cần mã ngôn ngữ, ví dụ vi hoặc en-US.')


def load_metadata(path, video):
    """Flat object, or shared defaults plus filename-specific replacements."""
    if path is None:
        return {}
    path = Path(path).resolve()
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Metadata JSON tối đa 1 MiB.')
    try:
        document = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(f'Metadata JSON lỗi tại dòng {error.lineno}, cột {error.colno}.') from None
    if not isinstance(document, dict):
        raise ValueError('File metadata phải là JSON object.')
    if 'defaults' in document or 'videos' in document:
        if document.keys() - {'schema_version', 'defaults', 'videos'}:
            raise ValueError('Metadata nhiều video chỉ nhận schema_version, defaults, videos.')
        if type(document.get('schema_version', 1)) is not int or document.get('schema_version', 1) != 1:
            raise ValueError('Chỉ hỗ trợ schema_version=1.')
        defaults, videos = document.get('defaults', {}), document.get('videos', {})
        _validate_fields(defaults)
        if not isinstance(videos, dict):
            raise ValueError('videos phải là object với key là tên file MP4.')
        for name, item in videos.items():
            if '/' in name or '\\' in name or not name.lower().endswith('.mp4'):
                raise ValueError('Key trong videos phải là tên file MP4, không kèm thư mục.')
            _validate_fields(item)
        data = {**defaults, **videos.get(Path(video).name, {})}
    else:
        _validate_fields(document)
        data = dict(document)
    if data.get('thumbnail') is not None:
        thumbnail = Path(data['thumbnail']).expanduser()
        data['thumbnail'] = thumbnail if thumbnail.is_absolute() else path.parent / thumbnail
    return data


def _chapter_lines(chapters, rendered):
    if not chapters:
        return ''
    if len(chapters) < 3:
        raise ValueError('YouTube chapters cần ít nhất 3 mốc; bỏ chapters nếu video chỉ có một chương.')
    stamps, lines = [], []
    for chapter in chapters:
        if (not isinstance(chapter, dict) or set(chapter) != {'start_seconds', 'title'}
                or type(chapter['start_seconds']) is not int or chapter['start_seconds'] < 0
                or not isinstance(chapter['title'], str) or not chapter['title'].strip()
                or any(c in chapter['title'] for c in '\r\n')):
            raise ValueError('Mỗi chapter cần start_seconds nguyên >= 0 và title không rỗng, một dòng.')
        second = chapter['start_seconds']
        stamps.append(second)
        hours, rest = divmod(second, 3600)
        minutes, seconds = divmod(rest, 60)
        label = f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'
        lines.append(f'{label} {chapter["title"]}')
    if stamps[0] != 0 or any(b - a < 10 for a, b in zip(stamps, stamps[1:])):
        raise ValueError('Chapters phải bắt đầu 00:00, tăng dần và cách nhau ít nhất 10 giây.')
    duration = rendered.get('duration_seconds')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Thời lượng video không hợp lệ để kiểm tra chapters.')
    if stamps[-1] + 10 > duration:
        raise ValueError('Chapter cuối phải nằm trong video và dài ít nhất 10 giây.')
    return '\n'.join(lines)


def build_upload_spec(video, *, channel_id, title=None, description=None, privacy=None,
                      tags=None, category_id='22', made_for_kids=None, use_thumbnail=None,
                      metadata_file=None, default_privacy='private'):
    video = Path(video)
    sidecar = video.with_suffix('.json')
    rendered = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.is_file() else {}
    generated = video.with_suffix('.youtube.json')
    effective_file = metadata_file if metadata_file is not None else (generated if generated.is_file() else None)
    data = load_metadata(effective_file, video)
    resolved_title = title if title is not None else data.get('title', rendered.get('title') or video.stem)
    resolved_description = description if description is not None else data.get('description', '')
    if data.get('chapters') and not isinstance(rendered.get('duration_seconds'), (int, float)):
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(video)],
            capture_output=True, text=True, timeout=30)
        try:
            duration = float(probe.stdout.strip())
        except ValueError:
            raise ValueError('Không đọc được thời lượng video để kiểm tra chapters.') from None
        if probe.returncode or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Thời lượng video không hợp lệ để kiểm tra chapters.')
        rendered['duration_seconds'] = duration
    chapters = _chapter_lines(data.get('chapters', []), rendered)
    if chapters:
        resolved_description += ('\n\n' if resolved_description else '') + chapters
    hashtags = []
    for tag in data.get('hashtags', []):
        tag = tag.removeprefix('#')
        if not re.fullmatch(r'\w+', tag, flags=re.UNICODE):
            raise ValueError('Hashtag chỉ gồm chữ, số, dấu gạch dưới; không chứa dấu cách.')
        if tag.casefold() not in {h.casefold() for h in hashtags}:
            hashtags.append(tag)
    if len(hashtags) > 60:
        raise ValueError('Tối đa 60 hashtag; nên chỉ dùng vài hashtag sát nội dung.')
    if hashtags:
        resolved_description += ('\n\n' if resolved_description else '') + ' '.join('#' + t for t in hashtags)
    thumbnail = video.with_suffix('.jpg')
    if 'thumbnail' in data:
        thumbnail = data['thumbnail']
    elif not thumbnail.is_file():
        thumbnail = None
    if use_thumbnail is False:
        thumbnail = None
    elif use_thumbnail is True and thumbnail is None:
        candidate = video.with_suffix('.jpg')
        thumbnail = candidate if candidate.is_file() else None
    return UploadSpec(
        video=video, title=resolved_title, channel_id=channel_id, description=resolved_description,
        privacy=privacy if privacy is not None else data.get('privacy', default_privacy),
        tags=tuple(tags if tags is not None else data.get('tags', [])),
        category_id=data.get('category_id', category_id),
        made_for_kids=made_for_kids if made_for_kids is not None else data.get('made_for_kids', False),
        thumbnail=thumbnail, default_language=data.get('default_language'),
        default_audio_language=data.get('default_audio_language'),
        contains_synthetic_media=data.get('contains_synthetic_media'),
        notify_subscribers=data.get('notify_subscribers', True))
