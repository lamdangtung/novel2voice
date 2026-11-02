"""T04 replayable fixture audit, confined to an owned verification workspace."""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from api.storage.migration import migrate_copy, inventory, sha256, readonly
from api.verification.workspace import WorkspaceManager, PROJECT_ROOT, atomic_json


def self_check(manager, name):
    manager.create(name)
    with manager.lock(name) as root:
        manager.describe(name)
        # A new audit folder per run; no destructive reset is needed.
        index = 1
        while (root / f'migration-{index:04}').exists():
            index += 1
        folder = root / f'migration-{index:04}'
        folder.mkdir()
        source = folder / 'legacy.sqlite3'
        fixture = json.loads((PROJECT_ROOT / 'tests/fixtures/t04.json').read_text())
        with sqlite3.connect(source) as db:
            db.executescript('''CREATE TABLE jobs(id TEXT PRIMARY KEY, source TEXT NOT NULL, output TEXT NOT NULL,
                status TEXT NOT NULL, error TEXT, audio_hash TEXT, updated_at TEXT);
                CREATE TABLE chunks(job_id TEXT NOT NULL, position INTEGER NOT NULL, cache_key TEXT NOT NULL,
                status TEXT NOT NULL, attempts INTEGER DEFAULT 0, error TEXT, PRIMARY KEY(job_id, position));
                CREATE TABLE artifacts(cache_key TEXT PRIMARY KEY, audio_hash TEXT NOT NULL);''')
            for table, rows in fixture.items():
                db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in rows[0])+')', rows)
        # Use a valid T02 audio fixture to prove migration leaves it byte-for-byte intact.
        # Locate by manifest rather than assume a production audio path.
        samples = list((root/'fixtures').rglob('*.mp3'))
        audio = folder / 'existing.mp3'; shutil.copyfile(samples[0], audio)
        hashes = {'database': sha256(source), 'audio': sha256(audio)}
        first = migrate_copy(source, folder/'upgraded.sqlite3')
        second = migrate_copy(source, folder/'upgraded.sqlite3')
        failed = folder/'failure.sqlite3'
        try:
            migrate_copy(source, failed, fail_after_schema=True)
            raise AssertionError('Expected failure was not raised')
        except RuntimeError as exc:
            if 'chủ động' not in str(exc):
                raise
        restored = sha256(failed) == sha256(failed.with_name(failed.name+'.v1-backup'))
        with readonly(folder/'upgraded.sqlite3') as db:
            books = db.execute('SELECT count(*) FROM n2v_books').fetchone()[0]
            artifacts = db.execute('SELECT count(*) FROM n2v_artifacts').fetchone()[0]
        result = {'status':'passed', 'first':first, 'second':second, 'failure_restored_exactly':restored,
                  'source_unchanged':sha256(source)==hashes['database'], 'audio_unchanged':sha256(audio)==hashes['audio'],
                  'automatic_books':books, 'automatic_audio_mappings':artifacts, 'directory':str(folder)}
        assert restored and result['source_unchanged'] and result['audio_unchanged'] and books==artifacts==0
        atomic_json(folder/'report.json',result)
        return result


def main():
    parser=argparse.ArgumentParser(description='T04 schema/migration self-check on isolated fixtures only.')
    parser.add_argument('command', choices=['self-check'])
    parser.add_argument('--workspace', default='migration-demo')
    args=parser.parse_args()
    print(json.dumps(self_check(WorkspaceManager(),args.workspace),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
