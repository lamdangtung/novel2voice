"""Static-image audiobook MP4 renderer with durable job checkpoints."""
import hashlib
import json
import math
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from PIL import Image

from src.tts_jobs import file_digest
from src.progress import emit
from .artwork import PillowThumbnailGenerator
from .base import VideoSpec, ThumbnailGenerator


class FFmpegVideoRenderer:
    def __init__(self, *, state_dir: Path, artwork: ThumbnailGenerator | None = None,
                 ffmpeg='ffmpeg', ffprobe='ffprobe', progress=None):
        self.progress = progress
        self._expected_duration = 0
        self.state_dir = Path(state_dir)
        self.artwork = artwork if artwork is not None else PillowThumbnailGenerator()
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe

    def _run(self, command):
        if self.progress is None:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError('Render video thất bại: ' + result.stderr[-4000:])
            return result
        command = command[:-1] + ['-progress', 'pipe:1', '-nostats', command[-1]]
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as errors:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True)
            try:
                for line in process.stdout:
                    key, _, value = line.strip().partition('=')
                    if key == 'out_time_us':
                        try:
                            seconds = min(float(value) / 1_000_000, self._expected_duration)
                        except ValueError:
                            continue
                        emit(self.progress, 'render', max(0, seconds), self._expected_duration, 'giây video')
                code = process.wait()
                if code:
                    errors.seek(0)
                    raise RuntimeError('Render video thất bại: ' + errors.read()[-4000:])
                return subprocess.CompletedProcess(command, code)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()

    def _probe(self, path):
        result = subprocess.run([self.ffprobe, '-v', 'error', '-show_format', '-show_streams',
                                 '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError(f'Không đọc được media: {path}')
        return json.loads(result.stdout)

    def _duration(self, info):
        duration = float(info['format']['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Thời lượng media không hợp lệ.')
        return duration

    def _validate(self, path, spec, expected):
        info = self._probe(path)
        video = [s for s in info['streams'] if s['codec_type'] == 'video']
        audio = [s for s in info['streams'] if s['codec_type'] == 'audio']
        if (not video or not audio or video[0]['codec_name'] != 'h264'
                or audio[0]['codec_name'] != 'aac' or video[0]['width'] != spec.width
                or video[0]['height'] != spec.height or video[0].get('pix_fmt') != 'yuv420p'):
            raise ValueError('Video đầu ra thiếu stream hoặc sai định dạng.')
        if abs(self._duration(info) - expected) > max(1.0, expected * 0.02):
            raise ValueError('Thời lượng video không khớp tổng audio chương.')

    @contextmanager
    def _store(self):
        import fcntl
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / 'video.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Một tiến trình khác đang render trong state-dir này.')
            try:
                with sqlite3.connect(self.state_dir / 'videos.sqlite3') as db:
                    db.execute('''CREATE TABLE IF NOT EXISTS video_jobs (
                        id TEXT PRIMARY KEY, output TEXT NOT NULL, status TEXT NOT NULL,
                        artifacts TEXT, error TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
                    yield db
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def render(self, spec: VideoSpec, *, resume=True):
        if not shutil.which(self.ffmpeg) or not shutil.which(self.ffprobe):
            raise RuntimeError('Cần ffmpeg và ffprobe để render video.')
        if (any(isinstance(v, bool) or not isinstance(v, int) for v in (spec.width, spec.height, spec.fps))
                or spec.width < 16 or spec.height < 16 or spec.width % 2 or spec.height % 2
                or not 1 <= spec.fps <= 60):
            raise ValueError('Kích thước phải là số chẵn >= 16; fps từ 1 đến 60.')
        output = Path(spec.output).resolve()
        if output.suffix.lower() != '.mp4':
            raise ValueError('Video đầu ra phải có đuôi .mp4.')
        paths = [Path(p).resolve() for p in spec.chapter_audio]
        if not paths or len(set(paths)) != len(paths):
            raise ValueError('Danh sách audio chương rỗng hoặc trùng.')
        background = Path(spec.background).resolve()
        inputs = paths + [background] + ([Path(spec.font_path).resolve()] if spec.font_path else [])
        thumbnail = output.with_suffix('.jpg')
        metadata = output.with_suffix('.json')
        targets = [output, thumbnail, metadata]
        if any(target in inputs for target in targets):
            raise ValueError('Đầu ra video/thumbnail/metadata phải khác các file đầu vào.')
        for path in inputs:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f'File đầu vào không tồn tại hoặc rỗng: {path}')
        with Image.open(background) as image:
            image.verify()
        durations = []
        for path in paths:
            info = self._probe(path)
            if not any(s['codec_type'] == 'audio' for s in info['streams']):
                raise ValueError(f'File không có audio: {path}')
            durations.append(self._duration(info))
        expected = sum(durations)
        self._expected_duration = expected
        emit(self.progress, "render", 0, expected, "giây video")
        identity = {'schema': 1, 'inputs': [(str(p), file_digest(p)) for p in inputs],
                    'output': str(output), 'title': spec.title, 'width': spec.width,
                    'height': spec.height, 'fps': spec.fps}
        if spec.thumbnail_text is not None:
            identity['thumbnail_text'] = spec.thumbnail_text
        job_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._store() as db:
            row = db.execute('SELECT status, artifacts FROM video_jobs WHERE id=?', (job_id,)).fetchone()
            if resume and row and row[0] == 'completed':
                hashes = json.loads(row[1])
                if all(p.is_file() and hashes.get(str(p)) == file_digest(p) for p in targets):
                    try:
                        self._validate(output, spec, expected)
                    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
                        pass
                    else:
                        emit(self.progress, "render", expected, expected, "giây video")
                        return output
            db.execute('''INSERT INTO video_jobs(id, output, status) VALUES (?,?,'running')
                       ON CONFLICT(id) DO UPDATE SET status='running',error=NULL,
                       artifacts=NULL,updated_at=CURRENT_TIMESTAMP''', (job_id, str(output)))
            db.commit()
            try:
                with tempfile.TemporaryDirectory(prefix='.render-', dir=output.parent) as directory:
                    temporary = Path(directory)
                    artwork = temporary / 'background.png'
                    self.artwork.generate(spec, artwork)
                    candidate = temporary / 'video.mp4'
                    command = [self.ffmpeg, '-nostdin', '-y', '-v', 'error', '-loop', '1',
                               '-framerate', str(spec.fps), '-i', str(artwork)]
                    filters = []
                    for index, path in enumerate(paths, 1):
                        command += ['-i', str(path)]
                        filters.append(f'[{index}:a:0]aresample=48000,'
                                       f'aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]')
                    filters.append(''.join(f'[a{i}]' for i in range(1, len(paths) + 1))
                                   + f'concat=n={len(paths)}:v=0:a=1[audio]')
                    command += ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[audio]',
                                '-c:v', 'libx264', '-preset', 'medium', '-tune', 'stillimage',
                                '-crf', '23', '-pix_fmt', 'yuv420p', '-r', str(spec.fps),
                                '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                                '-t', str(expected), '-shortest', '-movflags', '+faststart', str(candidate)]
                    self._run(command)
                    self._validate(candidate, spec, expected)
                    thumb = temporary / 'thumbnail.jpg'
                    thumbnail_artwork = artwork
                    if spec.thumbnail_text is not None:
                        thumbnail_artwork = temporary / 'thumbnail-artwork.png'
                        self.artwork.generate(replace(spec, title=spec.thumbnail_text), thumbnail_artwork)
                    with Image.open(thumbnail_artwork) as image:
                        image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                        image.convert('RGB').save(thumb, quality=90)
                    chapters, position = [], 0.0
                    for path, duration in zip(paths, durations):
                        chapters.append({'audio': str(path), 'start_seconds': position, 'duration_seconds': duration})
                        position += duration
                    meta = temporary / 'metadata.json'
                    meta.write_text(json.dumps({'title': spec.title, 'video': str(output),
                        'thumbnail': str(thumbnail), 'duration_seconds': self._duration(self._probe(candidate)),
                        'chapters': chapters, 'width': spec.width, 'height': spec.height, 'fps': spec.fps},
                        ensure_ascii=False, indent=2), encoding='utf-8')
                    for source, target in ((candidate, output), (thumb, thumbnail), (meta, metadata)):
                        source.replace(target)
                hashes = {str(p): file_digest(p) for p in targets}
                db.execute("UPDATE video_jobs SET status='completed',artifacts=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                           (json.dumps(hashes), job_id))
                db.commit()
            except BaseException as error:
                status = 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed'
                db.execute('UPDATE video_jobs SET status=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                           (status, str(error), job_id))
                db.commit()
                raise
        emit(self.progress, "render", expected, expected, "giây video")
        return output
