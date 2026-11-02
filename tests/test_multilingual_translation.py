"""Non-English translation/process reaches the bridge with the captured language."""
import json
from uuid import uuid4
import test_web_tts as fixtures
from api.books import EditBook,BookError
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.worker import claim,execute
from api.storage import session_scope
from api.storage.models import Job,Artifact
from api.jobs import job_view
from api.retry_plans import preview_retry,RetryRequest

class MultilingualTranslationTests(fixtures.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def test_chinese_process_retry_and_changed_language_guard(self):
        self.repo.edit(self.book,EditBook(name='中文',language='zh',revision=1))
        request=PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='process',policies=Policies(verification_fail_chapters=[self.chapter],verification_fail_stage='tts',retries=0))
        plan=preview(self.repo,request,True)
        self.assertEqual(plan['plan']['translation']['source_language'],'zh');self.assertFalse(plan['plan']['chapters'][0]['blocked'])
        confirm(self.repo,plan['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as db:
            failed=job_view(db.get(Job,plan['id']),self.repo.root,True)
            translated=db.get(Artifact,failed['report']['translation_artifact_id'])
            self.assertEqual(json.loads(translated.provenance)['source_language'],'zh')
        retry=preview_retry(self.repo,plan['id'],RetryRequest(request_id=uuid4(),clear_verification_faults=True),True)
        confirm(self.repo,retry['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as db:
            done=job_view(db.get(Job,retry['id']),self.repo.root,True)
            self.assertEqual(done['status'],'completed',done);self.assertEqual(done['report']['translator_calls'],0)
        pending=preview(self.repo,request.model_copy(update={'request_id':uuid4()}),True)
        current=self.repo.get(self.book);self.repo.edit(self.book,EditBook(name='日本語',language='ja',revision=current.revision))
        with self.assertRaises(BookError):confirm(self.repo,pending['id'])
        with session_scope(self.repo.engine) as db:self.assertFalse(db.get(Artifact,translated.id).verified)
        vi=self.repo.get(self.book);self.repo.edit(self.book,EditBook(name='VI',language='vi',revision=vi.revision))
        blocked=preview(self.repo,request.model_copy(update={'request_id':uuid4()}),True)
        self.assertTrue(blocked['plan']['chapters'][0]['blocked'])
