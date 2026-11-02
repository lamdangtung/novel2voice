"""Overview counts physical, selected audio and independent job attention."""
import hashlib,json
from uuid import uuid4
import test_chapters as fixtures
from api.storage import session_scope
from api.storage.models import Artifact,Job

class OverviewTests(fixtures.ChapterTests):
    test_natural_order_pages_filters_and_range=None
    test_detail_and_download_exact_bytes_and_isolation=None
    def test_counts_scopes_corruption_and_history(self):
        chapters=self.c.get(self.url+'/chapters').json()['items']
        for index in range(3):
            path=self.root/f'audio-{index}.mp3';path.write_bytes(b'audio')
            with session_scope(self.c.app.state.repository.engine) as db:
                db.add(Artifact(id=str(uuid4()),chapter_id=chapters[index]['id'],kind='audio',relative_path=path.name,sha256=hashlib.sha256(b'audio').hexdigest(),verified=index!=1,provenance=json.dumps({'selected':True,'source_hash':hashlib.sha256(self.raw).hexdigest()})))
        with session_scope(self.c.app.state.repository.engine) as db:
            for status in ['completed','failed','stopped','preview']:
                db.add(Job(id=str(uuid4()),book_id=self.book,kind='tts',status=status,config_json='{}'))
        value=self.c.get('/api/v1/overview').json()
        self.assertEqual(value['counts'],dict(books=1,chapters=45,current_audio=2,audio_attention=1,merged_saved=0,jobs_attention=2))
        (self.root/'audio-0.mp3').write_bytes(b'bad')
        value=self.c.get('/api/v1/overview?resource=attention').json()
        self.assertEqual(value['total'],2);self.assertEqual(value['counts']['current_audio'],1)
        self.assertEqual(self.c.get(self.url+'/chapters?status=needs_refresh').json()['total'],2)
        jobs=self.c.get('/api/v1/jobs?status=attention&limit=1').json()
        self.assertEqual(jobs['total'],2);self.assertEqual(len(jobs['items']),1)
        self.assertEqual(self.c.get('/api/v1/jobs?status=unknown').status_code,422)
        self.assertEqual(self.c.get('/api/v1/overview?book_id='+str(uuid4())).status_code,404)
        page=self.c.get('/api/v1/overview?resource=chapters&offset=40').json()
        self.assertEqual(len(page['items']),5)
