"""T05 durable books, idempotency, revision conflicts and isolated storage."""
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings
from api.books import BookRepository, CreateBook, EditBook, BookError


class BooksTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.headers={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}

    def client(self):
        return TestClient(create_app(Settings(data_dir=self.root)),base_url='http://127.0.0.1:8001')

    def test_flow_create_two_edit_restart_same_ids_and_directories(self):
        with self.client() as c:
            self.assertEqual(c.get('/api/v1/books').json()['total'],0)
            rows=[]
            for name,lang in [('Truyện A','vi'),('Story B','en')]:
                r=c.post('/api/v1/books',json={'name':name,'language':lang,'request_id':str(uuid4())},headers=self.headers)
                self.assertEqual(r.status_code,201);rows.append(r.json())
            a,b=rows
            r=c.patch('/api/v1/books/'+a['id'],json={'name':'Tên mới A','language':'en','revision':1},headers=self.headers)
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()['revision'],2)
            self.assertNotIn('create_token',r.json())
            self.assertEqual(c.get('/api/v1/health').json()['components']['database'],'ready')
        with self.client() as c:
            self.assertEqual(c.get('/api/v1/books/'+a['id']).json()['name'],'Tên mới A')
            self.assertEqual(c.get('/api/v1/books/'+b['id']).json()['name'],'Story B')
            self.assertEqual(c.get('/api/v1/books').json()['total'],2)
        self.assertTrue((self.root/a['storage']).is_dir());self.assertNotEqual(a['storage'],b['storage'])

    def test_retries_are_idempotent_and_payload_conflicts(self):
        data={'name':'A','language':'vi','request_id':str(uuid4())}
        with self.client() as c:
            first=c.post('/api/v1/books',json=data,headers=self.headers).json()
            self.assertEqual(c.post('/api/v1/books',json=data,headers=self.headers).json()['id'],first['id'])
            self.assertEqual(c.post('/api/v1/books',json={**data,'name':'B'},headers=self.headers).status_code,409)
            self.assertEqual(c.get('/api/v1/books').json()['total'],1)

    def test_concurrent_same_request_has_one_book(self):
        repo=BookRepository(self.root);self.addCleanup(repo.engine.dispose)
        data=CreateBook(name='Concurrent',language='vi',request_id=uuid4())
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(lambda _:repo.create(data).id,range(4)))
        self.assertEqual(len(set(ids)),1);self.assertEqual(repo.list().total,1)

    def test_validation_and_stale_revision(self):
        with self.client() as c:
            for name in ['', '  ', 'x\nfoo']:
                self.assertEqual(c.post('/api/v1/books',json={'name':name,'language':'vi','request_id':str(uuid4())},headers=self.headers).status_code,422)
            b=c.post('/api/v1/books',json={'name':'A','language':'vi','request_id':str(uuid4())},headers=self.headers).json()
            patch={'name':'B','language':'vi','revision':1}
            self.assertEqual(c.patch('/api/v1/books/'+b['id'],json=patch,headers=self.headers).status_code,200)
            self.assertEqual(c.patch('/api/v1/books/'+b['id'],json=patch,headers=self.headers).status_code,409)
            self.assertEqual(c.get('/api/v1/books/'+str(uuid4())).status_code,404)
            self.assertEqual(c.post('/api/v1/books',json={'name':'A','language':'vi','request_id':str(uuid4())}).status_code,403)

    def test_symlink_data_root_rejected(self):
        target=self.root/'real';target.mkdir();link=self.root/'link';link.symlink_to(target)
        with self.assertRaises(BookError):BookRepository(link)
