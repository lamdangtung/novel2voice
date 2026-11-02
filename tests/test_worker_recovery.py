"""T20 SIGKILL worker mid-chunk, restart, interrupted state and explicit resume."""
import base64
import os
from pathlib import Path
import signal
import subprocess
import time
from uuid import uuid4
import test_web_tts as base_tests
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.job_control import resume
from api.jobs import job_view
from api.storage import session_scope
from api.storage.models import Job
from api.verification.workspace import PROJECT_ROOT


class RecoveryTests(base_tests.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def spawn_worker(self):
        code='import sys;from pathlib import Path;from api.worker import run;run(Path(sys.argv[1]),True)'
        process=subprocess.Popen([str(PROJECT_ROOT/'api/.venv/bin/python'),'-c',code,str(self.repo.root)],cwd=PROJECT_ROOT,
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        def cleanup():
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=5)
        self.addCleanup(cleanup);return process
    def view(self,identifier):
        with session_scope(self.repo.engine) as s:return job_view(s.get(Job,identifier),self.repo.root,True)
    def wait_status(self,identifier,status,timeout=25):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            row=self.view(identifier)
            if row['status']==status:return row
            time.sleep(.1)
        self.fail(f'Expected {status}, got {row}')
    def test_restart_marks_interrupted_and_resume_reuses_completed_chunks(self):
        content='\n\n'.join(f'Phần {i}. '+f'Nội dung riêng số {i}. '*5 for i in range(1,9))
        p=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(content.encode()).decode()}]))
        txt_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':p.items[0].id,'number':1,'action':'update'}]))
        body=PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='tts',policies=Policies(verification_delay_ms=300,force=True,cleanup=False))
        plan=preview(self.repo,body,True);confirm(self.repo,plan['id']);first=self.spawn_worker()
        log=self.repo.root/'job-results'/plan['id']/'calls.jsonl';deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if log.is_file() and 'completed' in log.read_text():break
            time.sleep(.03)
        else:self.fail('Worker did not produce a chunk')
        first.kill();first.wait(timeout=5)
        second=self.spawn_worker();interrupted=self.wait_status(plan['id'],'interrupted')
        self.assertGreater(interrupted['completed_steps'],0);self.assertLess(interrupted['completed_steps'],interrupted['steps'])
        self.assertEqual(resume(self.repo,plan['id'])['status'],'queued')
        completed=self.wait_status(plan['id'],'completed')
        self.assertLess(completed['report']['provider_calls'],completed['steps']);self.assertIsNone(second.poll())
