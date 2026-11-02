"""T17 real CLI checkpoint bridge using tone provider, final artifact reuse."""
import base64
import json
from pathlib import Path
import shutil
import unittest
from uuid import uuid4
from api.books import BookRepository,CreateBook
from api.configuration import save,SaveConfig
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
from api.job_plans import preview,confirm,PlanRequest
from api.worker import claim,execute
from api.storage import session_scope
from api.storage.models import Job
from api.jobs import job_view
from api.verification import WorkspaceManager


class WebTTSTests(unittest.TestCase):
    def setUp(self):
        self.manager=WorkspaceManager();self.name='t17-test-'+uuid4().hex[:8];self.manager.create(self.name)
        root=self.manager.target(self.name);self.addCleanup(lambda:shutil.rmtree(root))
        self.repo=BookRepository(root/'web');self.addCleanup(self.repo.engine.dispose)
        self.book=self.repo.create(CreateBook(name='TTS',language='vi',request_id=uuid4())).id
        save(self.repo,SaveConfig(revision=0,values={'provider':'edge-tts','voice':'fake-voice','chunk_chars':100,'cleanup':False}))
        p=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(('Nội dung Việt. '*60).encode()).decode()}]))
        self.chapter=txt_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':p.items[0].id,'number':1}])).chapter_ids[0]
    def request(self):return PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='tts')
    def run_plan(self,body=None):
        plan=preview(self.repo,body or self.request(),True);confirm(self.repo,plan['id']);job=claim(self.repo);execute(self.repo,job,True)
        with session_scope(self.repo.engine) as s:view=job_view(s.get(Job,plan['id']),self.repo.root,True)
        self.assertEqual(view['status'],'completed',view)
        return plan,view
    def test_generate_then_reuse_no_provider_calls_and_voice_invalidates(self):
        body=self.request();first=preview(self.repo,body,True);self.assertEqual(preview(self.repo,body,True)['id'],first['id'])
        _,generated=self.run_plan(body);self.assertGreater(generated['report']['provider_calls'],0)
        _,reused=self.run_plan();self.assertTrue(reused['report']['reused']);self.assertEqual(reused['report']['provider_calls'],0)
        self.assertEqual(reused['report']['artifact_id'],generated['report']['artifact_id'])
        save(self.repo,SaveConfig(revision=1,values={'provider':'edge-tts','voice':'different-fake-voice','chunk_chars':100,'cleanup':False}))
        plan,changed=self.run_plan();self.assertEqual(plan['plan']['chapters'][0]['action'],'create_tts');self.assertGreater(changed['report']['provider_calls'],0)
        self.assertNotEqual(changed['report']['artifact_id'],generated['report']['artifact_id'])
