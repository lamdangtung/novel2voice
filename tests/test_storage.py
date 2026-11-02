"""T04: lossless copy migration, rollback and relational integrity."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from api.storage import engine_for, initialize, session_scope, SCHEMA_VERSION
from api.storage.models import Book, Chapter, Artifact, Job, SchemaVersion
from api.storage.migration import migrate_copy, inventory, sha256


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()

    def legacy(self):
        path=self.root/'legacy.db'
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE jobs(id TEXT PRIMARY KEY, source TEXT, output TEXT, status TEXT, error TEXT, audio_hash TEXT, updated_at TEXT); CREATE TABLE chunks(job_id TEXT, position INTEGER, cache_key TEXT, status TEXT, attempts INTEGER, error TEXT, PRIMARY KEY(job_id,position)); CREATE TABLE artifacts(cache_key TEXT PRIMARY KEY,audio_hash TEXT);')
            fixture=json.loads(Path('tests/fixtures/t04.json').read_text())
            for table,rows in fixture.items():db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
        return path

    def test_migration_twice_preserves_all_legacy_rows_and_source(self):
        source=self.legacy(); before=sha256(source);target=self.root/'new.db'
        report=migrate_copy(source,target)
        self.assertEqual(report['before'],report['after']);self.assertEqual(sha256(source),before)
        self.assertEqual(inventory(source),inventory(target))
        self.assertEqual(migrate_copy(source,target)['status'],'already_current')
        engine=engine_for(target);self.addCleanup(engine.dispose)
        with Session(engine) as s:
            self.assertEqual(s.get(SchemaVersion,1).version,SCHEMA_VERSION)
            self.assertEqual(s.exec(select(Book)).all(),[]);self.assertEqual(s.exec(select(Artifact)).all(),[])

    def test_failure_restores_exact_backup(self):
        source=self.legacy(); target=self.root/'failed.db'
        with self.assertRaises(RuntimeError):migrate_copy(source,target,fail_after_schema=True)
        self.assertEqual(sha256(target),sha256(self.root/'failed.db.v1-backup'))
        self.assertEqual(inventory(source),inventory(target))
        with sqlite3.connect(target) as db:self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='n2v_schema'").fetchone())

    def test_refuses_inplace_existing_and_links(self):
        source=self.legacy()
        with self.assertRaises(ValueError):migrate_copy(source,source)
        target=self.root/'existing.db';target.write_bytes(b'do not replace')
        with self.assertRaises((ValueError,sqlite3.DatabaseError)):migrate_copy(source,target)
        self.assertEqual(target.read_bytes(),b'do not replace')
        link=self.root/'link';link.symlink_to(source)
        with self.assertRaises(ValueError):migrate_copy(link,self.root/'other.db')

    def test_schema_constraints_and_rollback(self):
        engine=engine_for(self.root/'schema.db');self.addCleanup(engine.dispose);initialize(engine);initialize(engine)
        with session_scope(engine) as s:
            a=Book(name='Truyện A',create_token='a');b=Book(name='Truyện B',create_token='b');s.add(a);s.add(b);s.flush()
            s.add(Chapter(book_id=a.id,number=1,title='A',source_hash='aaa'))
            s.add(Chapter(book_id=b.id,number=1,title='B',source_hash='bbb'))
        with self.assertRaises(IntegrityError),session_scope(engine) as s:
            s.add(Chapter(book_id=a.id,number=1,title='duplicate',source_hash='ccc'))
        with self.assertRaises(IntegrityError),session_scope(engine) as s:
            s.add(Job(book_id='missing-book',kind='tts'))
        with Session(engine) as s:self.assertEqual(len(s.exec(select(Chapter)).all()),2)

    def test_legacy_requires_explicit_migration_and_future_schema_refused(self):
        engine=engine_for(self.legacy());self.addCleanup(engine.dispose)
        with self.assertRaises(ValueError):initialize(engine)
        engine2=engine_for(self.root/'future.db');self.addCleanup(engine2.dispose);initialize(engine2)
        with session_scope(engine2) as s:s.get(SchemaVersion,1).version=99
        with self.assertRaises(ValueError):initialize(engine2)

    def test_snapshot_includes_committed_wal(self):
        source=self.legacy()
        with sqlite3.connect(source) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute("UPDATE jobs SET status='interrupted' WHERE id='legacy-b'");db.commit()
            report=migrate_copy(source,self.root/'wal-copy.db')
            self.assertEqual(report['before'],report['after'])
