"""T25 catalog stays offline, sample never creates a chapter, invalid voice blocked."""
from uuid import uuid4
from unittest.mock import patch
import test_web_tts as base_tests
from api.voices import catalog,preview,VoiceRequest
from api.job_plans import confirm
from api.worker import claim,execute
from api.storage import session_scope
from api.storage.models import Job,Chapter,Artifact,BookArtifact
from api.jobs import job_view
from api.books import BookError
from sqlmodel import select


class VoiceSampleTests(base_tests.WebTTSTests):
    test_generate_then_reuse_no_provider_calls_and_voice_invalidates=None
    def test_catalog_sample_isolation_reuse_and_invalid_voice(self):
        self.assertEqual(len(catalog('edge-tts')['voices']),2)
        self.assertFalse(catalog('vieneu')['runtime_verified'])
        with session_scope(self.repo.engine) as s:before=(len(s.exec(select(Chapter)).all()),len(s.exec(select(Artifact)).all()))
        body=VoiceRequest(request_id=uuid4(),provider='edge-tts',voice='vi-VN-HoaiMyNeural',text='Xin chào, đây là câu thử giọng.')
        first=preview(self.repo,self.book,body,True);confirm(self.repo,first['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as s:
            report=job_view(s.get(Job,first['id']),self.repo.root,True)
            self.assertEqual(report['status'],'completed',report);self.assertTrue(report['report']['voice_artifact_id'])
            self.assertEqual((len(s.exec(select(Chapter)).all()),len(s.exec(select(Artifact)).all())),before)
            self.assertEqual(s.get(BookArtifact,report['report']['voice_artifact_id']).kind,'voice_sample')
        again=preview(self.repo,self.book,body.model_copy(update={'request_id':uuid4()}),True);confirm(self.repo,again['id']);execute(self.repo,claim(self.repo),True)
        with session_scope(self.repo.engine) as s:self.assertEqual(job_view(s.get(Job,again['id']),self.repo.root,True)['report']['provider_calls'],0)
        with self.assertRaises(BookError):preview(self.repo,self.book,body.model_copy(update={'voice':'not-a-valid-voice','request_id':uuid4()}),True)
        with patch('api.voices.check_environment',return_value={'checks':[{'label':'Thư viện','status':'missing','message':'Chưa cài.'}]}):
            blocked=preview(self.repo,self.book,body.model_copy(update={'request_id':uuid4()}),False)
            self.assertTrue(blocked['plan']['blocked'])
            with self.assertRaises(BookError):confirm(self.repo,blocked['id'])
