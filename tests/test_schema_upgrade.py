"""T24 additive schema2 upgrade backs up and preserves schema1 data."""
from pathlib import Path
import tempfile
import sqlite3
import unittest
from sqlalchemy import text
from sqlmodel import Session,select
from api.storage import engine_for,initialize,session_scope,SCHEMA_VERSION
from api.storage.models import Book,BookArtifact,SchemaVersion


class SchemaUpgradeTests(unittest.TestCase):
    def test_existing_books_preserved_backup_and_second_run_no_extra_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'library.sqlite3';engine=engine_for(path)
            try:
                initialize(engine)
                with session_scope(engine) as s:
                    s.add(Book(id='fixture-book',name='Truyện trước nâng cấp',language='vi',create_token='schema-one'))
                    s.get(SchemaVersion,1).version=1
                with engine.begin() as connection:connection.exec_driver_sql('DROP TABLE n2v_book_artifacts')
                initialize(engine)
                backups=list(path.parent.glob('*.backup'));self.assertEqual(len(backups),1)
                with sqlite3.connect(backups[0]) as db:
                    self.assertEqual(db.execute('SELECT version FROM n2v_schema').fetchone()[0],1)
                    self.assertEqual(db.execute('SELECT name FROM n2v_books').fetchone()[0],'Truyện trước nâng cấp')
                with Session(engine) as s:
                    self.assertEqual(s.get(SchemaVersion,1).version,SCHEMA_VERSION)
                    self.assertEqual(s.get(Book,'fixture-book').name,'Truyện trước nâng cấp')
                    self.assertEqual(s.exec(select(BookArtifact)).all(),[])
                initialize(engine);self.assertEqual(list(path.parent.glob('*.backup')),backups)
            finally:engine.dispose()

    def test_failed_upgrade_rolls_back_schema_and_keeps_backup(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'library.sqlite3';engine=engine_for(path)
            try:
                initialize(engine)
                with session_scope(engine) as db:db.get(SchemaVersion,1).version=1
                with engine.begin() as db:db.exec_driver_sql('DROP TABLE n2v_book_artifacts')
                original=BookArtifact.__table__.create
                def fail(connection,**kwargs):
                    original(connection,**kwargs)
                    raise RuntimeError('injected upgrade failure')
                with patch.object(BookArtifact.__table__,'create',side_effect=fail):
                    with self.assertRaises(RuntimeError):initialize(engine)
                with sqlite3.connect(path) as db:
                    self.assertEqual(db.execute('SELECT version FROM n2v_schema').fetchone()[0],1)
                    self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='n2v_book_artifacts'").fetchall())
                self.assertEqual(len(list(path.parent.glob('*.backup'))),1)
                initialize(engine)
                with Session(engine) as db:self.assertEqual(db.get(SchemaVersion,1).version,SCHEMA_VERSION)
            finally:engine.dispose()
