"""T24 ordered standalone merge, cache, injected failure preserves previous output."""
import base64
import hashlib
from uuid import uuid4
import test_web_tts as base_tests
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings
from api.imports import preview as txt_preview,confirm as txt_confirm,PreviewRequest,ConfirmRequest
from api.audio_imports import preview as audio_preview,confirm as audio_confirm,AudioPreview,AudioConfirm
from api.job_plans import preview,confirm,PlanRequest,Policies
from api.worker import execute,claim
from api.jobs import job_view
from api.storage import session_scope
from api.storage.models import Job,Artifact,BookArtifact
from sqlmodel import select
from api.books import CreateBook


class MergeTests(base_tests.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def test_order_cache_failure_and_range_download(self):
        p=txt_preview(self.repo,self.book,PreviewRequest(files=[{'name':f'{n}.txt','content_base64':base64.b64encode(f'Chương {n}'.encode()).decode()} for n in [2,10]]))
        new=txt_confirm(self.repo,self.book,p.id,ConfirmRequest(items=[{'item_id':i.id,'number':i.number} for i in p.items]))
        chapters=[self.chapter,*new.chapter_ids];tone=(self.manager.target(self.name)/'fixtures/tone.mp3').read_bytes()
        for chapter in chapters:
            audio=audio_preview(self.repo,self.book,AudioPreview(files=[{'name':'sample.mp3','content_base64':base64.b64encode(tone).decode()}]))
            audio_confirm(self.repo,self.book,audio['id'],AudioConfirm(items=[{'item_id':audio['items'][0]['id'],'chapter_id':chapter}]))
        with session_scope(self.repo.engine) as s:originals={a.relative_path:a.sha256 for a in s.exec(select(Artifact).where(Artifact.kind=='audio')).all()}
        def run(policies):
            body=PlanRequest(book_id=self.book,chapter_ids=[chapters[2],chapters[0],chapters[1]],request_id=uuid4(),action='merge',policies=policies)
            plan=preview(self.repo,body,True);self.assertEqual([i['number'] for i in plan['plan']['chapters']],[1,2,10])
            confirm(self.repo,plan['id']);execute(self.repo,claim(self.repo),True)
            with session_scope(self.repo.engine) as s:return job_view(s.get(Job,plan['id']),self.repo.root,True)
        first=run(Policies());self.assertEqual(first['status'],'completed',first);self.assertEqual(first['report']['provider_calls'],0)
        artifact_id=first['report']['merged_artifact_id']
        with session_scope(self.repo.engine) as s:path=self.repo.root/s.get(BookArtifact,artifact_id).relative_path
        before=path.read_bytes();self.assertLess(abs(first['report']['duration']-first['report']['input_duration']),1)
        reused=run(Policies());self.assertTrue(reused['report']['reused']);self.assertEqual(reused['report']['merged_artifact_id'],artifact_id)
        failed=run(Policies(force=True,verification_merge_failure=True));self.assertEqual(failed['status'],'failed');self.assertEqual(path.read_bytes(),before)
        repaired=run(Policies(force=True));self.assertEqual(repaired['status'],'completed')
        for relative,sha in originals.items():self.assertEqual(hashlib.sha256((self.repo.root/relative).read_bytes()).hexdigest(),sha)
        with TestClient(create_app(Settings(data_dir=self.repo.root)),base_url='http://127.0.0.1:8001') as c:
            url=f'/api/v1/books/{self.book}/merged/{artifact_id}'
            self.assertEqual(c.get(url+'?download=true').content,before)
            self.assertEqual(c.get(url,headers={'range':'bytes=0-99'}).status_code,206)
            other=self.repo.create(CreateBook(name='Other',language='vi',request_id=uuid4())).id
            self.assertEqual(c.get(f'/api/v1/books/{other}/merged/{artifact_id}').status_code,404)
