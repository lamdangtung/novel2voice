"""T22 original/translation separate, actual glossary context and whole-chapter retry."""
import base64
import json
from uuid import uuid4
import test_web_tts as base_tests
from api.books import EditBook
from api.configuration import save,SaveConfig
from api.glossaries import save as save_glossary,GlossaryUpload
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
from api.retry_plans import preview_retry,RetryRequest
from api.worker import execute,claim
from api.jobs import job_view
from api.storage import session_scope
from api.storage.models import Job,Artifact


class TranslationTests(base_tests.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def setUp(self):
        super().setUp();self.repo.edit(self.book,EditBook(name='English',language='en',revision=1))
        self.original='\n\n'.join(f'Part {n}. North starts a different journey number {n}. '*3 for n in range(1,5)).encode()
        p=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(self.original).decode()}]))
        txt_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':p.items[0].id,'number':1,'action':'update'}]))
        self.glossary('en,vi\nNorth,Phương Bắc\n',0)
    def glossary(self,text,revision):return save_glossary(self.repo,self.book,GlossaryUpload(name='terms.csv',content_base64=base64.b64encode(text.encode()).decode(),revision=revision))
    def request(self,**kwargs):return PlanRequest(book_id=self.book,chapter_ids=[self.chapter],request_id=uuid4(),action='translate',**kwargs)
    def run_translation(self,plan):
        confirm(self.repo,plan['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as s:return job_view(s.get(Job,plan['id']),self.repo.root,True)
    def test_glossary_actual_context_reuse_and_full_chapter_retry(self):
        plan=preview(self.repo,self.request(),True);first=self.run_translation(plan);self.assertEqual(first['status'],'completed',first)
        with session_scope(self.repo.engine) as s:artifact=s.get(Artifact,first['report']['artifact_id']);path=self.repo.root/artifact.relative_path
        self.assertIn('North → Phương Bắc',path.read_text());self.assertEqual((self.repo.root/'books'/self.book/'chapters'/self.chapter/'source.txt').read_bytes(),('Nội dung Việt. '*60).encode())
        from api.chapters import detail
        self.assertEqual(detail(self.repo,self.book,self.chapter)['source']['text'].encode(),self.original)
        contexts=[e for e in first['events'] if e.get('status')=='request_context'];self.assertTrue(contexts)
        self.assertTrue(all(e['glossary_hash']==plan['plan']['translation']['glossary_hash'] and e['prompt_hash']==plan['plan']['translation']['prompt_hash'] for e in contexts))
        second=self.run_translation(preview(self.repo,self.request(),True));self.assertEqual(second['report']['provider_calls'],0)
        self.glossary('en,vi\nNorth,Bắc mới\n',1)
        blocked=preview(self.repo,self.request(),True);self.assertTrue(blocked['plan']['chapters'][0]['blocked'])
        failing=preview(self.repo,self.request(policies=Policies(force=True,verification_fail_chapters=[self.chapter],verification_fail_on_call=2)),True)
        failed=self.run_translation(failing);self.assertEqual(failed['status'],'failed');self.assertEqual(failed['report']['retry_scope'],'whole_chapter')
        self.assertIn('Phương Bắc',path.read_text())
        retry=preview_retry(self.repo,failed['id'],RetryRequest(request_id=uuid4(),clear_verification_faults=True),True)
        retried=self.run_translation(retry);self.assertEqual(retried['status'],'completed',retried)
        self.assertEqual(retried['report']['provider_calls'],retried['steps'])
        with session_scope(self.repo.engine) as s:latest=s.get(Artifact,retried['report']['artifact_id']);self.assertIn('Bắc mới',(self.repo.root/latest.relative_path).read_text())
