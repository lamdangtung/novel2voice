"""Local profiles; remote users select IDs, never shell commands or filesystem paths."""
import json
import re
from pathlib import Path
from string import Formatter

from src.publishing.episode_metadata import load_story_config
from src.sources import get_novel_source


def load_profiles(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'stories'} or not isinstance(data['stories'], dict):
        raise ValueError('Bot config cần object stories.')
    profiles = {}
    allowed = {'chapter_url_template', 'story_config', 'background', 'glossary',
               'translation_provider', 'translation_model', 'tts_provider', 'youtube_privacy', 'upload_youtube', 'daily_publish_times'}
    for name, entry in data['stories'].items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', name) or not isinstance(entry, dict) or entry.keys() - allowed:
            raise ValueError(f'Profile Telegram không hợp lệ: {name}')
        entry = dict(entry)
        template = entry.get('chapter_url_template')
        if not isinstance(template, str) or [f for _, f, _, _ in Formatter().parse(template) if f] != ['chapter']:
            raise ValueError(f'{name}: URL template cần đúng một biến {{chapter}}.')
        url = template.format(chapter=1)
        source = get_novel_source(url)
        source.close()
        for field in ('story_config', 'background', 'glossary'):
            if not isinstance(entry.get(field), str):
                raise ValueError(f'{name}: thiếu {field}.')
            value = Path(entry[field]).expanduser()
            entry[field] = str(value.resolve() if value.is_absolute() else (path.parent / value).resolve())
        load_story_config(Path(entry['story_config']))
        if not Path(entry['background']).is_file():
            raise ValueError(f'{name}: không có ảnh nền.')
        if entry.get('translation_provider', 'deepseek') not in {'deepseek', 'openai'}:
            raise ValueError('translation_provider phải là deepseek hoặc openai.')
        if entry.get('tts_provider', 'vieneu') not in {'vieneu', 'piper', 'edge-tts', 'openai'}:
            raise ValueError('tts_provider không hợp lệ.')
        if type(entry.get('upload_youtube', True)) is not bool:
            raise ValueError('upload_youtube phải là boolean.')
        if entry.get('youtube_privacy', 'private') not in {'private', 'unlisted', 'public'}:
            raise ValueError('youtube_privacy không hợp lệ.')
        if 'daily_publish_times' in entry:
            from .scheduling import validate_times
            validate_times(entry['daily_publish_times'])
        profiles[name] = entry
    if not profiles:
        raise ValueError('Cần ít nhất một profile truyện.')
    return profiles
