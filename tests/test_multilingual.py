"""Source languages cover API/UI catalog, prompt identity and safe existing-db upgrade."""
import json,re,sqlite3,tempfile,unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from api.books import BookRepository,CreateBook,EditBook
from api.storage import initialize,engine_for,session_scope,SCHEMA_VERSION
from api.storage.models import Book,Chapter,Artifact,SchemaVersion
from src.languages import LANGUAGES
from src.translation_contract import prompt,identity

class LanguageTests(unittest.TestCase):
    def test_all_languages_roundtrip_and_validation(self):
        from fastapi.testclient import TestClient
        from api.main import create_app
        from api.settings import Settings
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(data_dir=Path(tmp).resolve())
            headers={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
            with TestClient(create_app(settings),base_url='http://127.0.0.1:8001') as c:
                catalog=c.get('/api/v1/books/workspace/languages').json()['items']
                self.assertEqual({x['code'] for x in catalog},set(LANGUAGES))
                for code in LANGUAGES:
                    result=c.post('/api/v1/books',json={'name':code,'language':code,'request_id':str(uuid4())},headers=headers)
                    self.assertEqual(result.status_code,201,result.text)
                for code in ['xx','zh-CN','EN','',"en'); DROP TABLE n2v_books;--"]:
                    self.assertEqual(c.post('/api/v1/books',json={'name':'invalid','language':code,'request_id':str(uuid4())},headers=headers).status_code,422)
                row=c.get('/api/v1/books').json()['items'][0]
                changed=c.patch('/api/v1/books/'+row['id'],json={'name':'Truyện Nhật','language':'ja','revision':row['revision']},headers=headers)
                self.assertEqual(changed.status_code,200);identifier=row['id']
            with TestClient(create_app(settings),base_url='http://127.0.0.1:8001') as c:
                self.assertEqual(c.get('/api/v1/books/'+identifier).json()['language'],'ja')
                self.assertEqual(c.get('/api/v1/books').json()['total'],len(LANGUAGES))

    def test_prompt_uses_source_and_invalidates_translation_identity(self):
        values={'translation_model':'model','chunk_chars':100}
        self.assertIn('từ tiếng Trung sang tiếng Việt',prompt([], 'zh'))
        self.assertNotIn('từ tiếng Anh',prompt([], 'ja'))
        self.assertEqual(prompt([]),prompt([], 'en'))
        self.assertNotEqual(identity(values,[],True,'zh'),identity(values,[],True,'ja'))

    def test_upgrade_schema_two_preserves_children_and_unique_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();path=root/'library.sqlite3';engine=engine_for(path);initialize(engine)
            with session_scope(engine) as db:
                db.add(Book(id='book',name='Original',language='en',create_token='token'));db.flush()
                db.add(Chapter(id='chapter',book_id='book',number=1,title='Original',source_hash='hash'));db.flush()
                db.add(Artifact(id='artifact',chapter_id='chapter',kind='source_txt',relative_path='source.txt',sha256='hash',provenance='{}'))
            engine.dispose()
            # Reproduce the previous schema's actual restrictive CHECK constraint.
            with sqlite3.connect(path) as db:
                db.execute('PRAGMA foreign_keys=OFF')
                ddl=db.execute("SELECT sql FROM sqlite_master WHERE name='n2v_books'").fetchone()[0]
                ddl=re.sub(r'CHECK \(language IN \([^)]+\)\)', "CHECK (language IN ('vi','en'))",ddl)
                db.execute(ddl.replace('CREATE TABLE n2v_books','CREATE TABLE n2v_books_old',1))
                db.execute('INSERT INTO n2v_books_old SELECT * FROM n2v_books');db.execute('DROP TABLE n2v_books');db.execute('ALTER TABLE n2v_books_old RENAME TO n2v_books')
                db.execute('CREATE UNIQUE INDEX ix_n2v_books_create_token ON n2v_books(create_token)')
                db.execute('UPDATE n2v_schema SET version=2')
            repo=BookRepository(root)
            try:
                with session_scope(repo.engine) as db:
                    self.assertEqual(db.get(SchemaVersion,1).version,SCHEMA_VERSION)
                    self.assertEqual(db.get(Chapter,'chapter').book_id,'book');self.assertEqual(db.get(Artifact,'artifact').chapter_id,'chapter')
                self.assertEqual(repo.create(CreateBook(name='中文',language='zh',request_id=uuid4())).language,'zh')
                with self.assertRaises(IntegrityError):
                    with session_scope(repo.engine) as db:db.add(Book(name='Duplicate',language='ja',create_token='token'))
                with sqlite3.connect(path) as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                backups=list(root.glob('*.backup'));self.assertEqual(len(backups),1)
                with sqlite3.connect(backups[0]) as db:
                    self.assertEqual(db.execute('SELECT version FROM n2v_schema').fetchone()[0],2)
                    self.assertIn("language IN ('vi','en')",db.execute("SELECT sql FROM sqlite_master WHERE name='n2v_books'").fetchone()[0])
                repo.engine.dispose();again=BookRepository(root);again.engine.dispose();self.assertEqual(len(list(root.glob('*.backup'))),1)
            finally:repo.engine.dispose()
