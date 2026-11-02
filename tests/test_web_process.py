"""T23 saved translation survives TTS failure; retry only TTS, stale VI blocks."""
import test_web_translation as translation_tests
from uuid import uuid4
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.retry_plans import preview_retry,RetryRequest
from api.worker import execute,claim
from api.storage import session_scope
from api.storage.models import Job,Artifact
from api.jobs import job_view
from api.books import BookError


class ProcessTests(translation_tests.TranslationTests):
    test_glossary_actual_context_reuse_and_full_chapter_retry=None
    def run_process(self,plan):
        confirm(self.repo,plan['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as s:return job_view(s.get(Job,plan['id']),self.repo.root,True)
    def test_tts_retry_preserves_translation_and_changed_translation_requires_new_plan(self):
        body=PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='process',policies=Policies(retries=0,cleanup=False,verification_fail_chapters=[self.chapter],verification_fail_stage='tts',verification_fail_on_call=2))
        plan=preview(self.repo,body,True);failed=self.run_process(plan)
        self.assertEqual(failed['status'],'failed',failed);self.assertTrue(failed['report']['translation_completed'])
        self.assertGreater(failed['report']['translator_calls'],0);translated=failed['report']['translation_artifact_id']
        retry=preview_retry(self.repo,failed['id'],RetryRequest(request_id=uuid4(),clear_verification_faults=True),True)
        self.assertEqual(retry['plan']['chapters'][0]['translation_artifact_id'],translated)
        completed=self.run_process(retry);self.assertEqual(completed['status'],'completed',completed)
        self.assertEqual(completed['report']['translator_calls'],0);self.assertEqual(completed['report']['translation_artifact_id'],translated)
        with session_scope(self.repo.engine) as s:
            audio=s.get(Artifact,completed['report']['artifact_id']);vi=s.get(Artifact,translated)
            import json
            self.assertEqual(json.loads(audio.provenance)['translation_sha256'],vi.sha256)
        self.glossary('en,vi\nNorth,Bắc khác\n',1)
        self.run_translation(preview(self.repo,self.request(policies=Policies(force=True)),True))
        with self.assertRaisesRegex(BookError,'Bản dịch đã đổi'):
            preview_retry(self.repo,failed['id'],RetryRequest(request_id=uuid4(),clear_verification_faults=True),True)
