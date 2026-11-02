"""T21 retry failed chunks; corrupt MP3+cache regenerate only invalid chunk."""
import base64
import hashlib
from pathlib import Path
import subprocess
from uuid import uuid4
import test_web_tts as base_tests
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.retry_plans import preview_retry,RetryRequest
from api.worker import claim,execute
from api.storage import session_scope
from api.storage.models import Job,Artifact
from api.jobs import job_view


class RetryTests(base_tests.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def execute_plan(self,plan):
        confirm(self.repo,plan['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as s:return job_view(s.get(Job,plan['id']),self.repo.root,True)
    def test_retry_prefix_and_valid_but_changed_cache_chunk(self):
        content='\n\n'.join(f'Phần {i}. '+f'Nội dung riêng số {i}. '*5 for i in range(1,7))
        p=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(content.encode()).decode()}]))
        txt_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':p.items[0].id,'number':1,'action':'update'}]))
        body=PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='tts',policies=Policies(retries=0,cleanup=False,verification_fail_chapters=[self.chapter],verification_fail_on_call=2))
        first=self.execute_plan(preview(self.repo,body,True));self.assertEqual(first['status'],'failed');self.assertEqual(first['report']['provider_calls'],2)
        retry_body=RetryRequest(request_id=uuid4(),clear_verification_faults=True)
        retry=preview_retry(self.repo,first['id'],retry_body,True);self.assertEqual(preview_retry(self.repo,first['id'],retry_body,True)['id'],retry['id'])
        finished=self.execute_plan(retry);self.assertEqual(finished['status'],'completed',finished)
        self.assertLess(finished['report']['provider_calls'],finished['steps'])
        with session_scope(self.repo.engine) as s:artifact=s.get(Artifact,finished['report']['artifact_id']);audio_path=self.repo.root/artifact.relative_path
        audio_path.write_bytes(b'corrupt final')
        cached=sorted((self.repo.root/'books'/self.book/'.tts-cache/chunks').glob('*.mp3'));self.assertGreater(len(cached),2)
        other=self.repo.root/'different.mp3';subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=600:duration=0.4','-c:a','libmp3lame',str(other)],check=True)
        bad=cached[0];bad.write_bytes(other.read_bytes());preserved={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cached[1:]}
        repair=preview_retry(self.repo,finished['id'],RetryRequest(request_id=uuid4()),True);repaired=self.execute_plan(repair)
        self.assertEqual(repaired['status'],'completed',repaired);self.assertEqual(repaired['report']['provider_calls'],1)
        self.assertEqual(audio_path.read_bytes(),b'corrupt final')
        for p in cached[1:]:self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),preserved[p.name])
