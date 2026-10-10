"""Persistent, bounded TTS jobs. SQLite records metadata; audio stays on disk."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console

console = Console()


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def provider_signature(provider):
    # Explicit allowlist: never persist API keys, tokens or mutable model objects.
    fields = ('voice', 'rate', 'volume', 'pitch', 'model', 'mode', 'backbone_repo',
              'backbone_device', 'precision', 'codec_repo', 'codec_device',
              'model_name', 'model_path', 'config_path', 'ref_audio', 'ref_text')
    settings = {key: getattr(provider, key, None) for key in fields}
    settings['provider'] = type(provider).__name__
    settings['schema'] = 1
    from importlib.metadata import version, PackageNotFoundError
    for package in ('vieneu', 'edge-tts', 'openai', 'piper-tts'):
        try:
            settings[package] = version(package)
        except PackageNotFoundError:
            pass
    settings['endpoint'] = digest(str(getattr(provider, 'api_base', None) or
                                      getattr(provider, 'base_url', None)))
    for key in ('model_path', 'config_path', 'ref_audio'):
        value = getattr(provider, key, None)
        if value and Path(value).is_file():
            settings[key] = file_digest(Path(value))
    return digest(json.dumps(settings, sort_keys=True))


class JobStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'jobs.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, output TEXT NOT NULL,
                    status TEXT NOT NULL, error TEXT, audio_hash TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    cache_key TEXT PRIMARY KEY, audio_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    job_id TEXT NOT NULL, position INTEGER NOT NULL, cache_key TEXT NOT NULL,
                    status TEXT NOT NULL, attempts INTEGER DEFAULT 0, error TEXT,
                    PRIMARY KEY (job_id, position)
                );
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def execute(self, sql, params=()):
        with self.connect() as db:
            db.execute(sql, params)

    def get(self, job_id):
        with self.connect() as db:
            return db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()

    def rows(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM jobs ORDER BY updated_at DESC, id')]

    def status(self, job_id, status, error=None, audio_hash=None):
        self.execute('''UPDATE jobs SET status=?, error=?, audio_hash=?,
                        updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                     (status, error, audio_hash, job_id))

    @contextmanager
    def lock(self):
        # Serialize invocations sharing the cache, including concurrent CLI runs.
        import fcntl
        with (self.directory / 'runner.lock').open('a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Một tiến trình TTS khác đang dùng state-dir này.')
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


class TTSJobRunner:
    def __init__(self, provider, merger, chunker, state_dir, concurrency=3, retries=2):
        if concurrency < 1 or retries < 0:
            raise ValueError('concurrency phải >= 1; retries phải >= 0.')
        self.provider = provider
        self.merger = merger
        self.chunker = chunker
        self.store = JobStore(state_dir)
        self.cache = self.store.directory / 'chunks'
        self.cache.mkdir(exist_ok=True)
        self.concurrency = concurrency
        self.retries = retries
        self.signature = provider_signature(provider)

    def valid(self, path):
        return self.merger.validate_audio(path)

    def run(self, source, output, resume=True, cleanup=True):
        source, output = Path(source).resolve(), Path(output).resolve()
        if output.suffix.lower() != '.mp3':
            raise ValueError('Đầu ra TTS phải có đuôi .mp3.')
        try:
            text = source.read_text(encoding='utf-8-sig').strip()
            if not text:
                raise ValueError(f'File {source.name} rỗng.')
        except Exception as error:
            with self.store.lock():
                preparation_id = digest(json.dumps([str(source), str(output), 'input-error']))
                self.store.execute("""INSERT INTO jobs (id, source, output, status, error)
                    VALUES (?, ?, ?, 'failed', ?) ON CONFLICT(id) DO UPDATE SET
                    status='failed', error=excluded.error, updated_at=CURRENT_TIMESTAMP""",
                    (preparation_id, str(source), str(output), str(error)))
            raise
        chunks = self.chunker.chunk_text(text)
        keys = [digest(self.signature + '\n' + chunk) for chunk in chunks]
        job_id = digest(json.dumps([str(source), str(output), keys]))
        with self.store.lock():
            previous = self.store.get(job_id)
            if (resume and previous and previous['status'] == 'completed'
                    and self.valid(output) and previous['audio_hash'] == file_digest(output)):
                console.print(f'[green]✔ Tái sử dụng chương: {source.name}[/green]')
                return output
            self.store.execute('''INSERT INTO jobs (id, source, output, status)
                VALUES (?, ?, ?, 'running') ON CONFLICT(id) DO UPDATE SET
                status='running', error=NULL, audio_hash=NULL, updated_at=CURRENT_TIMESTAMP''',
                (job_id, str(source), str(output)))
            paths = [self.cache / f'{key}.mp3' for key in keys]
            for index, key in enumerate(keys):
                self.store.execute('''INSERT INTO chunks (job_id, position, cache_key, status)
                    VALUES (?, ?, ?, 'pending') ON CONFLICT(job_id, position)
                    DO UPDATE SET status='pending', error=NULL''', (job_id, index, key))
            try:
                # De-duplicate identical text; preserve original order for merging.
                pending = {}
                for index, (chunk, path) in enumerate(zip(chunks, paths)):
                    if resume and self.cached(keys[index], path):
                        self._chunk_status(job_id, keys[index], 'completed')
                    else:
                        pending[keys[index]] = (chunk, path)
                console.print(f'[cyan]>> {source.name}: {len(chunks)} đoạn, '
                              f'{len(pending)} đoạn cần tạo.[/cyan]')
                items = list(pending.items())
                for offset in range(0, len(items), self.concurrency):
                    self._generate(job_id, items[offset:offset + self.concurrency])
                if not all(self.valid(path) for path in paths):
                    raise RuntimeError('Thiếu đoạn hoặc audio không hợp lệ trước khi ghép.')
                self.store.status(job_id, 'merging')
                self.merge(paths, output)
                self.store.status(job_id, 'completed', audio_hash=file_digest(output))
                if cleanup:
                    for path in set(paths):
                        path.unlink(missing_ok=True)
                console.print(f'[green]✔ Hoàn thành: {output}[/green]')
                return output
            except BaseException as error:
                self.store.status(job_id, 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit))
                                  else 'failed', str(error) or type(error).__name__)
                raise

    def cached(self, key, path):
        with self.store.connect() as db:
            row = db.execute('SELECT audio_hash FROM artifacts WHERE cache_key=?', (key,)).fetchone()
        return bool(row and self.valid(path) and row['audio_hash'] == file_digest(path))

    def _chunk_status(self, job_id, key, status, error=None):
        self.store.execute('UPDATE chunks SET status=?, error=? WHERE job_id=? AND cache_key=?',
                           (status, error, job_id, key))

    def _generate(self, job_id, items):
        remaining = dict(items)
        last_error = None
        for attempt in range(self.retries + 1):
            tasks = []
            for key, (text, final) in remaining.items():
                partial = final.with_suffix('.partial.mp3')
                partial.unlink(missing_ok=True)
                tasks.append((text, partial))
                self._chunk_status(job_id, key, 'running')
                self.store.execute('UPDATE chunks SET attempts=attempts+1 WHERE job_id=? AND cache_key=?',
                                   (job_id, key))
            interrupted = None
            try:
                self.provider.generate_batch(tasks, max_concurrency=self.concurrency, show_progress=True)
            except Exception as error:
                last_error = error
            except BaseException as error:
                interrupted = error
            # Recover valid partial outputs even when a batch fails midway.
            for key, (_, final) in list(remaining.items()):
                partial = final.with_suffix('.partial.mp3')
                if self.valid(partial):
                    partial.replace(final)
                    self.store.execute("""INSERT INTO artifacts (cache_key, audio_hash) VALUES (?, ?)
                        ON CONFLICT(cache_key) DO UPDATE SET audio_hash=excluded.audio_hash""",
                        (key, file_digest(final)))
                    self._chunk_status(job_id, key, 'completed')
                    del remaining[key]
                else:
                    self._chunk_status(job_id, key, 'failed',
                                       str(last_error or interrupted or 'Audio thiếu/không hợp lệ'))
            if interrupted:
                raise interrupted
            if not remaining:
                return
            if attempt < self.retries:
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f'TTS thất bại cho {len(remaining)} đoạn sau '
                           f'{self.retries + 1} lần thử: {last_error or "audio không hợp lệ"}')

    def combine(self, paths, output, resume=True):
        output = Path(output).resolve()
        with self.store.lock():
            if not paths or not all(self.valid(path) for path in paths):
                raise RuntimeError('Không thể ghép tập: thiếu audio chương hợp lệ.')
            identity = [(str(path.resolve()), file_digest(path)) for path in paths]
            job_id = digest(json.dumps(['combine', str(output), identity]))
            previous = self.store.get(job_id)
            if (resume and previous and previous['status'] == 'completed'
                    and self.valid(output) and previous['audio_hash'] == file_digest(output)):
                return output
            self.store.execute("""INSERT INTO jobs (id, source, output, status)
                VALUES (?, ?, ?, 'merging') ON CONFLICT(id) DO UPDATE SET
                status='merging', error=NULL, audio_hash=NULL, updated_at=CURRENT_TIMESTAMP""",
                (job_id, 'combine: ' + json.dumps([str(p) for p in paths], ensure_ascii=False), str(output)))
            try:
                self.merge(paths, output)
                self.store.status(job_id, 'completed', audio_hash=file_digest(output))
            except BaseException as error:
                self.store.status(job_id, 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit))
                                  else 'failed', str(error) or type(error).__name__)
                raise
            return output

    def merge(self, paths, output):
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not paths or not all(self.valid(path) for path in paths):
            raise RuntimeError('Không thể ghép: audio đầu vào thiếu hoặc không hợp lệ.')
        partial = output.with_name(f'.{output.stem}.partial.mp3')
        try:
            self.merger.merge_mp3_files(paths, partial)
            if not self.valid(partial):
                raise RuntimeError('Audio ghép không hợp lệ.')
            expected = sum(self.merger.get_duration(path) for path in paths)
            actual = self.merger.get_duration(partial)
            if abs(actual - expected) > max(1.0, expected * 0.02):
                raise RuntimeError('Thời lượng audio ghép không khớp các đoạn đầu vào.')
            partial.replace(output)
        finally:
            partial.unlink(missing_ok=True)
