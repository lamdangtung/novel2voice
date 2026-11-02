"""Durable upload orchestration. Never restart an ambiguous/expired session automatically."""
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from src.tts_jobs import file_digest
from src.progress import emit
from .base import UploadSpec, VideoPublisher, PublishedVideo, RetryableUploadError
from .schedule import parse_publish_at, normalize_publish_at, require_future


class PublishingRunner:
    def __init__(self, publisher: VideoPublisher, state_dir: Path, *, chunk_size=8 * 1024 * 1024, retries=3, progress=None):
        if chunk_size < 256 * 1024 or chunk_size % (256 * 1024) or retries < 0:
            raise ValueError('Chunk upload phải là bội 256 KiB; retries >= 0.')
        self.publisher, self.state_dir = publisher, Path(state_dir)
        self.progress = progress
        self.chunk_size, self.retries = chunk_size, retries

    @contextmanager
    def _store(self):
        import fcntl
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / 'upload.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Một tiến trình khác đang dùng upload state-dir.')
            try:
                path = self.state_dir / 'uploads.sqlite3'
                # Create with restricted permissions before storing a resumable session URL.
                fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
                os.close(fd)
                os.chmod(path, 0o600)
                with sqlite3.connect(path) as db:
                    db.row_factory = sqlite3.Row
                    db.execute('''CREATE TABLE IF NOT EXISTS uploads (
                        id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, video_hash TEXT NOT NULL,
                        metadata TEXT NOT NULL, session TEXT, offset INTEGER DEFAULT 0,
                        video_id TEXT, privacy TEXT, thumbnail_hash TEXT,
                        status TEXT NOT NULL, error TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
                    yield db
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _retry(self, action):
        for attempt in range(self.retries + 1):
            try:
                return action()
            except RetryableUploadError:
                if attempt >= self.retries:
                    raise
                time.sleep(min(2 ** attempt, 8))

    @staticmethod
    def _validate(spec, *, require_channel=True, check_media=True):
        if require_channel and not spec.channel_id.strip():
            raise ValueError('Cần YOUTUBE_CHANNEL_ID hoặc --channel-id. Chạy youtube-auth để xem ID kênh.')
        if spec.privacy not in {'private', 'unlisted', 'public'}:
            raise ValueError('Privacy phải là private, unlisted hoặc public.')
        if not spec.title.strip() or len(spec.title) > 100 or any(c in spec.title for c in '<>'):
            raise ValueError('Tiêu đề phải từ 1–100 ký tự và không chứa < >.')
        if len(spec.description.encode('utf-8')) > 5000 or any(c in spec.description for c in '<>'):
            raise ValueError('Mô tả tối đa 5000 byte UTF-8 và không chứa < >.')
        if not spec.category_id.isdigit():
            raise ValueError('category_id phải là số.')
        if any(not tag.strip() for tag in spec.tags) or sum(len(t) + 3 for t in spec.tags) > 500:
            raise ValueError('Tags rỗng hoặc quá dài (giới hạn 500 ký tự).')
        for field in ('made_for_kids', 'notify_subscribers'):
            if type(getattr(spec, field)) is not bool:
                raise ValueError(f'{field} phải là boolean.')
        if spec.contains_synthetic_media is not None and type(spec.contains_synthetic_media) is not bool:
            raise ValueError('contains_synthetic_media phải là boolean.')
        for field in ('default_language', 'default_audio_language'):
            value = getattr(spec, field)
            if value is not None and not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value):
                raise ValueError(f'{field} không hợp lệ.')
        if spec.publish_at is not None:
            parse_publish_at(spec.publish_at)
            if spec.privacy != 'private':
                raise ValueError('publish_at chỉ dùng với privacy=private.')
        if not check_media:
            return
        path = Path(spec.video)
        if path.suffix.lower() != '.mp4' or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Video MP4 không tồn tại hoặc rỗng: {path}')
        if spec.thumbnail:
            thumb = Path(spec.thumbnail)
            if not thumb.is_file() or not 0 < thumb.stat().st_size <= 2 * 1024 * 1024:
                raise ValueError('Thumbnail cần là ảnh không rỗng, tối đa 2 MiB.')
            with Image.open(thumb) as image:
                if image.format not in {'JPEG', 'PNG'}:
                    raise ValueError('Thumbnail phải là JPEG hoặc PNG.')
                image.verify()

    def publish(self, spec: UploadSpec) -> PublishedVideo:
        self._validate(spec)
        channel = self._retry(self.publisher.channel_id)
        if channel != spec.channel_id:
            raise ValueError('Kênh OAuth khác channel-id yêu cầu; chưa upload video.')
        video = Path(spec.video)
        size, video_hash = video.stat().st_size, file_digest(video)
        job_id = hashlib.sha256(f'{channel}:{video_hash}'.encode()).hexdigest()
        metadata_values = {'title': spec.title, 'description': spec.description,
            'privacy': spec.privacy, 'tags': spec.tags, 'category_id': spec.category_id,
            'made_for_kids': spec.made_for_kids}
        # Preserve the identity of existing checkpoints with default extra fields.
        for field in ('default_language', 'default_audio_language', 'contains_synthetic_media'):
            value = getattr(spec, field)
            if value is not None:
                metadata_values[field] = value
        if not spec.notify_subscribers:
            metadata_values['notify_subscribers'] = False
        if spec.publish_at is not None:
            metadata_values['publish_at'] = normalize_publish_at(spec.publish_at)
        metadata = json.dumps(metadata_values, sort_keys=True, ensure_ascii=False)
        thumbnail_hash = file_digest(Path(spec.thumbnail)) if spec.thumbnail else None
        with self._store() as db:
            row = db.execute('SELECT * FROM uploads WHERE id=?', (job_id,)).fetchone()
            if row and row['metadata'] != metadata and not row['session'] and not row['video_id']:
                # A rejected initiation uploaded no bytes: corrected metadata is safe.
                db.execute("UPDATE uploads SET metadata=?,status='pending',error=NULL WHERE id=?", (metadata, job_id))
                db.commit()
                row = db.execute('SELECT * FROM uploads WHERE id=?', (job_id,)).fetchone()
            if row and row['metadata'] != metadata:
                raise ValueError('Video này đã có upload với metadata khác. Không tạo bản trùng; '
                                 'chỉnh metadata trong YouTube Studio hoặc dùng lại metadata ban đầu.')
            if not row:
                db.execute("INSERT INTO uploads(id,channel_id,video_hash,metadata,status) VALUES (?,?,?,?,'pending')",
                           (job_id, channel, video_hash, metadata))
                db.commit()
                row = db.execute('SELECT * FROM uploads WHERE id=?', (job_id,)).fetchone()
            try:
                video_id = row['video_id']
                if not video_id:
                    session = row['session']
                    if not session:
                        if spec.publish_at is not None:
                            require_future(spec.publish_at, buffer_seconds=900)
                        session = self._retry(lambda: self.publisher.start(spec, size))
                        db.execute("UPDATE uploads SET session=?,status='uploading',error=NULL WHERE id=?", (session, job_id))
                        db.commit()
                    # Server is authoritative after a crash or a lost final response.
                    progress = self._retry(lambda: self.publisher.query(session, size))
                    stalled = 0
                    with video.open('rb') as stream:
                        while True:
                            emit(self.progress, "upload", progress.offset, size, "byte")
                            if not 0 <= progress.offset <= size:
                                raise ValueError('Server trả offset upload không hợp lệ.')
                            if progress.video_id:
                                if not re.fullmatch(r'[A-Za-z0-9_-]{11}', progress.video_id):
                                    raise ValueError('Server trả video ID không hợp lệ.')
                                video_id = progress.video_id
                                db.execute("UPDATE uploads SET video_id=?,offset=?,privacy=?,status='uploaded',error=NULL WHERE id=?",
                                           (video_id, size, progress.privacy, job_id))
                                db.commit()  # Persist before thumbnail or reporting completion.
                                break
                            if progress.offset >= size:
                                raise RuntimeError('Upload đủ byte nhưng chưa nhận video ID. Chạy lại để truy vấn trạng thái; không tạo phiên mới.')
                            db.execute("UPDATE uploads SET offset=?,status='uploading',error=NULL WHERE id=?", (progress.offset, job_id))
                            db.commit()
                            if spec.publish_at is not None:
                                require_future(spec.publish_at, buffer_seconds=900)
                            previous = progress.offset
                            stream.seek(previous)
                            data = stream.read(min(self.chunk_size, size - previous))
                            if not data:
                                raise RuntimeError('File video thay đổi trong khi upload.')
                            try:
                                progress = self.publisher.send(session, data, previous, size)
                            except RetryableUploadError:
                                time.sleep(min(2 ** min(stalled, 3), 8))
                                progress = self._retry(lambda: self.publisher.query(session, size))
                            stalled = stalled + 1 if progress.offset <= previous and not progress.video_id else 0
                            if stalled > self.retries:
                                raise RetryableUploadError('Upload không tiến triển; checkpoint giữ nguyên để chạy lại.')
                if spec.thumbnail and row['thumbnail_hash'] != thumbnail_hash:
                    self._retry(lambda: self.publisher.set_thumbnail(video_id, Path(spec.thumbnail)))
                    db.execute('UPDATE uploads SET thumbnail_hash=? WHERE id=?', (thumbnail_hash, job_id))
                    db.commit()
                db.execute("UPDATE uploads SET status='completed',error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?", (job_id,))
                db.commit()
            except BaseException as error:
                status = 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed'
                db.execute('UPDATE uploads SET status=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                           (status, str(error), job_id))
                db.commit()
                raise
        emit(self.progress, "upload", size, size, "byte")
        return PublishedVideo(video_id, f'https://www.youtube.com/watch?v={video_id}', channel)
