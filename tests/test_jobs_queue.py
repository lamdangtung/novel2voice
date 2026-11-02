"""T15 durable claim and duplicate request protection; real fake provider output."""
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest
from uuid import uuid4
from api.books import BookRepository,CreateBook
from api.jobs import enqueue_test,TestJobRequest,job_view
from api.worker import claim,execute
from api.storage.models import Job
from api.storage import session_scope


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.repo=BookRepository(Path(self.tmp.name).resolve());self.addCleanup(self.repo.engine.dispose)
        self.book=self.repo.create(CreateBook(name='Queue',language='vi',request_id=uuid4())).id
    def request(self,**kwargs):return TestJobRequest(book_id=self.book,request_id=uuid4(),delay_ms=0,steps=2,**kwargs)
    def test_enqueue_retry_and_concurrent_claim_once(self):
        body=self.request();first=enqueue_test(self.repo,body);self.assertEqual(enqueue_test(self.repo,body)['id'],first['id'])
        with ThreadPoolExecutor(max_workers=4) as p:results=list(p.map(lambda _:claim(self.repo),range(4)))
        self.assertEqual(sum(x is not None for x in results),1)
        other=BookRepository(self.repo.root);self.addCleanup(other.engine.dispose)
        with session_scope(other.engine) as s:self.assertEqual(s.get(Job,first['id']).status,'running')
    def test_execute_success_and_fault_report(self):
        for fail in [None,2]:
            created=enqueue_test(self.repo,self.request(fail_on_call=fail));job=claim(self.repo);execute(self.repo,job,True)
            with session_scope(self.repo.engine) as s:
                view=job_view(s.get(Job,created['id']),self.repo.root,True)
                self.assertEqual(view['status'],'completed' if fail is None else 'failed')
                self.assertEqual(view['completed_steps'],2 if fail is None else 1)
                self.assertIsNotNone(view['report'])
