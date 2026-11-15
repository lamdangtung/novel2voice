"""Static and illustrated audiobook MP4 renderer with durable checkpoints."""
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
        if spec.scenes:
            if (len(spec.scenes) > 48 or not math.isfinite(spec.transition_seconds)
                    or not 0 < spec.transition_seconds <= 5 or not math.isfinite(spec.zoom_amount)
                    or not 0 <= spec.zoom_amount <= .2):
                raise ValueError('Tối đa 48 ảnh; chuyển cảnh > 0 đến 5 giây; zoom từ 0 đến 0.2.')
            if any(not math.isfinite(s.duration_seconds) or s.duration_seconds <= 0 for s in spec.scenes):
                raise ValueError('Thời lượng mỗi cảnh phải dương.')
            inputs += [Path(scene.image).resolve() for scene in spec.scenes]
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
        for scene in spec.scenes:
            with Image.open(scene.image) as image:
                image.verify()
        durations = []
        for path in paths:
            info = self._probe(path)
            if not any(s['codec_type'] == 'audio' for s in info['streams']):
                raise ValueError(f'File không có audio: {path}')
            durations.append(self._duration(info))
        expected = sum(durations)
        if spec.scenes and abs(sum(s.duration_seconds for s in spec.scenes) - expected) > .05:
            raise ValueError('Tổng thời lượng ảnh không khớp audio.')
        self._expected_duration = expected
        emit(self.progress, "render", 0, expected, "giây video")
        identity = {'schema': 1, 'inputs': [(str(p), file_digest(p)) for p in inputs],
                    'output': str(output), 'title': spec.title, 'width': spec.width,
                    'height': spec.height, 'fps': spec.fps}
        if spec.thumbnail_text is not None:
            identity['thumbnail_text'] = spec.thumbnail_text
        if spec.scenes:
            identity['slideshow'] = {'schema': 1, 'durations': [s.duration_seconds for s in spec.scenes],
                'transition': spec.transition_seconds, 'zoom': spec.zoom_amount,
                'sources': [s.source_text for s in spec.scenes], 'prompts': [s.prompt for s in spec.scenes]}
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
                    self.artwork.generate(replace(spec, background=spec.scenes[0].image) if spec.scenes else spec, artwork)
                    candidate = temporary / 'video.mp4'
                    if spec.scenes:
                        command = self._slideshow_command(spec, paths, candidate, temporary, expected)
                    else:
                        command = self._static_command(spec, paths, artwork, candidate, expected)
                    self._run(command)
                    self._validate(candidate, spec, expected)
                    thumb = temporary / 'thumbnail.jpg'
                    thumbnail_artwork = artwork
                    if spec.thumbnail_text is not None:
                        thumbnail_artwork = temporary / 'thumbnail-artwork.png'
                        self.artwork.generate(replace(spec, background=spec.scenes[0].image if spec.scenes else spec.background, title=spec.thumbnail_text), thumbnail_artwork)
                    with Image.open(thumbnail_artwork) as image:
                        image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                        image.convert('RGB').save(thumb, quality=90)
                    chapters, position = [], 0.0
                    for path, duration in zip(paths, durations):
                        chapters.append({'audio': str(path), 'start_seconds': position, 'duration_seconds': duration})
                        position += duration
                    scene_metadata, position = [], 0.0
                    for scene in spec.scenes:
                        scene_metadata.append({'image': str(scene.image), 'start_seconds': position,
                            'duration_seconds': scene.duration_seconds, 'source_text': scene.source_text,
                            'prompt': scene.prompt})
                        position += scene.duration_seconds
                    meta = temporary / 'metadata.json'
                    metadata_values = {'title': spec.title, 'video': str(output),
                        'thumbnail': str(thumbnail), 'duration_seconds': self._duration(self._probe(candidate)),
                        'chapters': chapters, 'width': spec.width, 'height': spec.height, 'fps': spec.fps}
                    if scene_metadata:
                        _, _, fade = self._slideshow_timing(spec)
                        metadata_values.update(scenes=scene_metadata, transition_seconds=fade if len(spec.scenes) > 1 else 0,
                                               zoom_amount=spec.zoom_amount, timing='proportional_text_length')
                    meta.write_text(json.dumps(metadata_values, ensure_ascii=False, indent=2), encoding='utf-8')
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

    def _audio_filters(self, paths, first_input):
        filters = []
        for index, _ in enumerate(paths):
            filters.append(f'[{first_input + index}:a:0]aresample=48000,'
                           f'aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]')
        filters.append(''.join(f'[a{i}]' for i in range(len(paths)))
                       + f'concat=n={len(paths)}:v=0:a=1[audio]')
        return filters

    def _encoding_options(self, spec, candidate, expected):
        return ['-c:v', 'libx264', '-preset', 'medium', '-tune', 'stillimage',
                '-crf', '23', '-pix_fmt', 'yuv420p', '-r', str(spec.fps),
                '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                '-t', str(expected), '-shortest', '-movflags', '+faststart', str(candidate)]

    def _static_command(self, spec, paths, artwork, candidate, expected):
        command = [self.ffmpeg, '-nostdin', '-y', '-v', 'error', '-loop', '1',
                   '-framerate', str(spec.fps), '-i', str(artwork)]
        for path in paths:
            command += ['-i', str(path)]
        command += ['-filter_complex', ';'.join(self._audio_filters(paths, 1)),
                    '-map', '0:v:0', '-map', '[audio]']
        return command + self._encoding_options(spec, candidate, expected)

    def _slideshow_timing(self, spec):
        # Integer frame boundaries prevent long xfade chains from drifting or ending early.
        boundaries, elapsed = [0], 0.0
        for scene in spec.scenes:
            elapsed += scene.duration_seconds
            boundaries.append(round(elapsed * spec.fps))
        frames = [b - a for a, b in zip(boundaries, boundaries[1:])]
        if min(frames) < 1:
            raise ValueError('Cảnh quá ngắn so với FPS; giảm số ảnh mỗi chương.')
        fade_frames = max(1, min(round(spec.transition_seconds * spec.fps), max(1, min(frames) // 2)))
        fade = fade_frames / spec.fps
        return boundaries, frames, fade

    def _slideshow_command(self, spec, paths, candidate, temporary, expected):
        boundaries, frames, fade = self._slideshow_timing(spec)
        fade_frames = round(fade * spec.fps)
        command = [self.ffmpeg, '-nostdin', '-y', '-v', 'error', '-filter_complex_threads', '1']
        filters = []
        for index, (scene, length) in enumerate(zip(spec.scenes, frames)):
            image_path = temporary / f'scene_{index}.png'
            # Full-screen illustrations; title remains on the thumbnail rather than covering each scene.
            self.artwork.generate(replace(spec, background=scene.image, title=''), image_path)
            segment_frames = length + (fade_frames if index < len(frames) - 1 else 0)
            command += ['-loop', '1', '-framerate', str(spec.fps),
                        '-t', str(segment_frames / spec.fps), '-i', str(image_path)]
            zoom = f'1+{spec.zoom_amount:.8f}*on/{max(1, segment_frames - 1)}'
            filters.append(f"[{index}:v]zoompan=z='{zoom}':x='iw/2-iw/zoom/2':"
                           f"y='ih/2-ih/zoom/2':d=1:s={spec.width}x{spec.height}:fps={spec.fps},"
                           f"setsar=1,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{index}]")
        video = 'v0'
        for index in range(1, len(frames)):
            next_video = f'fade{index}'
            filters.append(f'[{video}][v{index}]xfade=transition=fade:duration={fade:.8f}:'
                           f'offset={boundaries[index] / spec.fps:.8f}[{next_video}]')
            video = next_video
        for path in paths:
            command += ['-i', str(path)]
        filters += self._audio_filters(paths, len(frames))
        command += ['-filter_complex', ';'.join(filters), '-map', f'[{video}]', '-map', '[audio]']
        return command + self._encoding_options(spec, candidate, expected)
