"""Copy-only checkpoint upgrade; never attach legacy MP3s to chapters."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from sqlmodel import SQLModel, Session
from api.storage import SCHEMA_VERSION, engine_for
from api.storage.models import SchemaVersion, LegacyCheckpoint

LEGACY = ('jobs', 'chunks', 'artifacts')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


@contextmanager
def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        yield db
    finally:
        db.close()


def inventory(path):
    with readonly(path) as db:
        data = {}
        for table in LEGACY:
            # Table identifiers are constants, never user input.
            rows = db.execute(f'SELECT * FROM {table}').fetchall()
            data[table] = sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=False))
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return {'counts': {k: len(v) for k, v in data.items()}, 'logical_sha256': digest}


def migrate_copy(source, target, *, fail_after_schema=False):
    source, target = Path(source).absolute(), Path(target).absolute()
    if not source.is_file() or source.resolve() == target.resolve():
        raise ValueError('Nâng cấp cần source tồn tại và target là bản sao riêng.')
    for path in (source, target):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Không nâng cấp qua symlink.')
        if path.exists() and path.stat().st_nlink > 1:
            raise ValueError('Không nâng cấp qua hardlink.')
    before = inventory(source)
    source_hash = sha256(source)
    backup = target.with_name(target.name + '.v1-backup')
    if target.exists():
        with readonly(target) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'n2v_schema' in tables:
                version = db.execute('SELECT version FROM n2v_schema WHERE id=1').fetchone()
                reference = db.execute('SELECT logical_sha256 FROM n2v_legacy_checkpoints').fetchone()
                if version == (SCHEMA_VERSION,) and reference == (before['logical_sha256'],) and inventory(target) == before:
                    return {'status': 'already_current', 'before': before, 'after': inventory(target), 'backup': str(backup)}
            raise ValueError('Target đã có dữ liệu hoặc schema không phù hợp; chọn target mới.')
    if backup.exists():
        raise ValueError('Backup đã tồn tại; không ghi đè.')
    target.parent.mkdir(parents=True, exist_ok=True)
    # SQLite backup API includes committed WAL content, unlike raw file copying.
    target.touch(exist_ok=False)
    with readonly(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with target.open('rb') as src, backup.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    backup_hash = sha256(backup)
    engine = engine_for(target)
    try:
        SQLModel.metadata.create_all(engine)
        if fail_after_schema:
            raise RuntimeError('Lỗi nâng cấp chủ động để kiểm tra khôi phục.')
        with Session(engine) as session:
            session.add(SchemaVersion(version=SCHEMA_VERSION))
            session.add(LegacyCheckpoint(source_sha256=source_hash, logical_sha256=before['logical_sha256'], source_name=source.name))
            session.commit()
        after = inventory(target)
        if before != after or sha256(source) != source_hash:
            raise RuntimeError('Dữ liệu nguồn hoặc checkpoint thay đổi trong nâng cấp.')
        return {'status': 'migrated', 'before': before, 'after': after, 'backup': str(backup),
                'backup_sha256': backup_hash, 'source_sha256': source_hash, 'automatic_audio_mappings': 0}
    except BaseException as exc:
        engine.dispose()
        shutil.copyfile(backup, target)
        if sha256(target) != backup_hash:
            raise RuntimeError('Không thể khôi phục backup.') from exc
        raise
    finally:
        engine.dispose()
