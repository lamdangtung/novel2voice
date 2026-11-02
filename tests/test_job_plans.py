"""T16 immutable config snapshots, source freshness and one job per request."""
import base64
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from api.books import BookRepository,CreateBook,BookError
from api.configuration import save,SaveConfig
from api.imports import preview as import_preview,confirm as import_confirm,PreviewRequest,ConfirmRequest
from api.job_plans import preview,confirm,PlanRequest
from api.storage import session_scope
from api.storage.models import Job


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.repo=BookRepository(Path(self.tmp.name).resolve());self.addCleanup(self.repo.engine.dispose)
        self.book=self.repo.create(CreateBook(name='Plan',language='vi',request_id=uuid4())).id
        p=import_preview(self.repo,self.book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(b'One').decode()}]))
        self.chapter=import_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':p.items[0].id,'number':1}])).chapter_ids[0]
    def request(self):return PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4())
    def test_snapshot_kept_after_config_changes_and_confirm_repeated(self):
        save(self.repo,SaveConfig(revision=0,values={'provider':'edge-tts','voice':'before'}))
        body=self.request();first=preview(self.repo,body,True)
        save(self.repo,SaveConfig(revision=1,values={'provider':'edge-tts','voice':'after'}))
        self.assertEqual(preview(self.repo,body,True)['plan']['configuration']['voice'],'before')
        confirmed=confirm(self.repo,first['id']);self.assertEqual(confirmed['status'],'queued')
        self.assertEqual(confirm(self.repo,first['id'])['id'],confirmed['id'])
        with session_scope(self.repo.engine) as s:
            snapshot=s.get(Job,first['id']).config_json;self.assertIn('before',snapshot);self.assertNotIn('after',snapshot)
            self.assertNotIn('API_KEY',snapshot)
    def test_changed_bytes_blocks_confirm_and_unavailable_action_rejected(self):
        first=preview(self.repo,self.request(),True)
        (self.repo.root/'books'/self.book/'chapters'/self.chapter/'source.txt').write_bytes(b'changed')
        with self.assertRaises(BookError):confirm(self.repo,first['id'])
        with self.assertRaises(BookError):preview(self.repo,self.request(),False)
