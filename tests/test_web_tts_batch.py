"""T18 mixed batch policies, retries, fail-fast, force and cleanup."""
import base64
import json
from sqlmodel import select
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
from api.audio_imports import preview as audio_preview,confirm as audio_confirm,AudioPreview,AudioConfirm
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.worker import claim,execute
from api.storage import session_scope
from api.storage.models import Job
from api.jobs import job_view
import test_web_tts as base_tests
from uuid import uuid4


class BatchTTSTests(base_tests.WebTTSTests):
    # Don't inherit the single-feature test as a duplicate case.
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def test_mixed_batch_retry_failfast_force_cleanup(self):
        self.run_plan()
        p=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':f'{n}.txt','content_base64':base64.b64encode(f'Chương {n} ngắn.'.encode()).decode()} for n in [2,3]]))
        imported=txt_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':i.id,'number':i.number} for i in p.items]))
        second,third=imported.chapter_ids
        tone=(self.manager.target('queue-fixture')/'fixtures/tone.mp3').read_bytes()
        audio=audio_preview(self.repo,self.book,AudioPreview(files=[{'name':'chapter_2.mp3','content_base64':base64.b64encode(tone).decode()}]))
        audio_confirm(self.repo,self.book,audio['id'],AudioConfirm(items=[{'item_id':audio['items'][0]['id'],'chapter_id':second}]))
        def run(policies):
            body=PlanRequest(book_id=self.book,chapter_ids=[self.chapter,second,third],request_id=uuid4(),action='tts',policies=policies)
            plan=preview(self.repo,body,True);confirm(self.repo,plan['id']);execute(self.repo,claim(self.repo),True)
            with session_scope(self.repo.engine) as s:result=job_view(s.get(Job,plan['id']),self.repo.root,True)
            return plan,result
        plan,continued=run(Policies(verification_fail_chapters=[third],retries=1,cleanup=False))
        self.assertEqual([i['action'] for i in plan['plan']['chapters']],['reuse','keep_imported','create_tts'])
        self.assertEqual(continued['status'],'failed');self.assertEqual(continued['report']['processed_chapters'],3)
        self.assertEqual(continued['report']['chapters'][-1]['provider_calls'],2)
        _,fast=run(Policies(force=True,verification_fail_chapters=[self.chapter],continue_on_error=False,retries=0))
        self.assertEqual(fast['status'],'failed');self.assertEqual(fast['report']['processed_chapters'],1);self.assertEqual(fast['report']['remaining_chapters'],2)
        _,forced=run(Policies(force=True,keep_imported=False,cleanup=True,retries=0))
        self.assertEqual(forced['status'],'completed')
        self.assertTrue(all(c['provider_calls']>0 for c in forced['report']['chapters']))
        self.assertEqual(list((self.repo.root/'books'/self.book/'.tts-cache/chunks').glob('*.mp3')),[])
