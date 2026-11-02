"""T19 stop actual bridge during a chunk; resume cached chunks with same snapshot."""
import json
import base64
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import test_web_tts as base_tests
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.worker import claim,execute
from api.job_control import stop,resume
from api.storage import session_scope
from api.storage.models import Job
from api.jobs import job_view


class StopTests(base_tests.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def test_stop_mid_chunk_resume_does_not_regenerate_finished_prefix(self):
        content='\n\n'.join(f'Đoạn {i}. '+f'Nội dung riêng số {i}. '*5 for i in range(1,9))
        changed=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(content.encode()).decode()}]))
        txt_confirm(self.repo,self.book,changed.id,ConfirmRequest(items=[{'item_id':changed.items[0].id,'number':1,'action':'update'}]))
        body=PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='tts',policies=Policies(verification_delay_ms=300,force=True,cleanup=False))
        plan=preview(self.repo,body,True);confirm(self.repo,plan['id']);job=claim(self.repo)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(execute,self.repo,job,True)
            log=self.repo.root/'job-results'/job['id']/'calls.jsonl';deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if log.is_file() and 'completed' in log.read_text():break
                time.sleep(.03)
            else:self.fail('No completed chunk before deadline')
            self.assertEqual(stop(self.repo,job['id'])['status'],'stop_requested');future.result(timeout=15)
        with session_scope(self.repo.engine) as s:
            stopped=job_view(s.get(Job,job['id']),self.repo.root,True);snapshot=s.get(Job,job['id']).config_json
        self.assertEqual(stopped['status'],'stopped',stopped);self.assertGreater(stopped['completed_steps'],0)
        self.assertLess(stopped['completed_steps'],stopped['steps'])
        self.assertEqual(resume(self.repo,job['id'])['status'],'queued')
        self.assertEqual(resume(self.repo,job['id'])['status'],'queued')
        execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as s:
            finished=job_view(s.get(Job,job['id']),self.repo.root,True);self.assertEqual(s.get(Job,job['id']).config_json,snapshot)
        self.assertEqual(finished['status'],'completed',finished)
        self.assertLess(finished['report']['provider_calls'],finished['steps'])
