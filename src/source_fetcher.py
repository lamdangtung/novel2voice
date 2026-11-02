"""Bounded sequential chapter fetching and atomic local artifacts."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.sources import NovelSource, get_novel_source


def _atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def fetch_chapters(url: str, output_dir: Path, *, max_chapters=1,
                   source: NovelSource | None = None) -> list[Path]:
    if max_chapters < 1:
        raise ValueError('max_chapters phải >= 1.')
    owned = source is None
    source = source if source is not None else get_novel_source(url)
    paths, visited = [], set()
    book = None
    try:
        for _ in range(max_chapters):
            if url in visited:
                raise ValueError('Phát hiện vòng lặp liên kết chương.')
            visited.add(url)
            chapter = source.fetch_chapter(url)
            identity = (chapter.source, chapter.book_id)
            if book is not None and book != identity:
                raise ValueError('Nguồn trả chương thuộc truyện khác.')
            book = identity
            # Adapters return identifiers, never filesystem paths.
            import re
            if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value)
                   for value in (chapter.source, chapter.book_id, chapter.chapter_id, chapter.language)):
                raise ValueError('Định danh chương không hợp lệ.')
            if not chapter.title.strip() or not chapter.text.strip():
                raise ValueError('Nguồn trả chương rỗng.')
            stem = f'{chapter.source}_{chapter.book_id}_{chapter.chapter_id}_{chapter.language}'
            target = Path(output_dir) / chapter.source / chapter.book_id / f'{stem}.txt'
            _atomic_write(target, chapter.title + '\n\n' + chapter.text + '\n')
            metadata = {**chapter.__dict__, 'fetched_at': datetime.now(timezone.utc).isoformat()}
            metadata.pop('text')
            _atomic_write(target.with_suffix('.json'), json.dumps(metadata, ensure_ascii=False, indent=2))
            paths.append(target)
            if not chapter.next_url:
                break
            url = chapter.next_url
        return paths
    finally:
        if owned:
            source.close()
