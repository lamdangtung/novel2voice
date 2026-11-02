"""Chapter removal is scoped, revision-checked, job-safe and preserves output history."""
import hashlib,json
from uuid import uuid4
from unittest.mock import patch
import test_chapters as fixtures
from sqlalchemy import text
from sqlmodel import select
from api.storage import session_scope
from api.storage.models import Artifact,Job,Chapter,BookArtifact,ImportSession

class ChapterDeletionTests(fixtures.ChapterTests):
    test_natural_order_pages_filters_and_range=None
    test_detail_and_download_exact_bytes_and_isolation=None
    def row(self):return self.c.get(self.url+'/chapters').json()['items'][0]
    def remove(self,row,book_url=None,revision=None):return self.c.request('DELETE',(book_url or self.url)+'/chapters/'+row['id'],json={'revision':revision or row['revision']},headers=self.h)
    def test_remove_scoped_artifacts_keeps_files_job_history_merges_and_reimport(self):
        row=self.row();detail=self.c.get(self.url+'/chapters/'+row['id']).json();source=detail['source']['artifact_id']
        vi=self.root/'translation.txt';vi.write_text('Bản dịch');audio=self.root/'speech.mp3';audio.write_bytes(b'old audio');merged=self.root/'merged.mp3';merged.write_bytes(b'old merge')
        historical=str(uuid4());merged_id=str(uuid4());audio_id=str(uuid4())
        with session_scope(self.c.app.state.repository.engine) as db:
            db.add(Job(id=historical,book_id=self.book,chapter_id=row['id'],kind='tts',status='completed',config_json=json.dumps({'plan':{'chapters':[{'id':row['id']}]}})));db.flush()
            for identifier,kind,path in [(str(uuid4()),'translation_txt',vi),(audio_id,'audio',audio)]:db.add(Artifact(id=identifier,chapter_id=row['id'],kind=kind,relative_path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),provenance='{}',verified=True))
            db.add(BookArtifact(id=merged_id,book_id=self.book,job_id=historical,relative_path=merged.name,sha256=hashlib.sha256(merged.read_bytes()).hexdigest(),duration=1,source_signature='sig',source_manifest='[]'))
        response=self.remove(row);self.assertEqual(response.status_code,200,response.text);self.assertFalse(response.json()['files_removed'])
        self.assertEqual(self.c.get(self.url+'/chapters').json()['total'],44)
        for path in ['/chapters/'+row['id'],'/artifacts/'+source+'/download','/audio/'+audio_id]:self.assertEqual(self.c.get(self.url+path).status_code,404)
        self.assertEqual(self.c.get(self.url+'/merged/'+merged_id).content,b'old merge')
        self.assertEqual(vi.read_text(),'Bản dịch');self.assertEqual(audio.read_bytes(),b'old audio')
        with session_scope(self.c.app.state.repository.engine) as db:
            self.assertIsNone(db.get(Job,historical).chapter_id);self.assertEqual(json.loads(db.get(Job,historical).config_json)['plan']['chapters'][0]['id'],row['id'])
            self.assertEqual(db.exec(select(Artifact).where(Artifact.chapter_id==row['id'])).all(),[])
            self.assertEqual(db.exec(text('PRAGMA foreign_key_check')).all(),[])
        archive=json.loads(next((self.root/'deleted-chapters').glob('*.json')).read_text());self.assertEqual(archive['chapter']['id'],row['id']);self.assertEqual(len(archive['artifacts']),3)
        p=self.post(self.url+'/text-imports',{'number':1,'content':'Nhập lại'}).json()
        recreated=self.post(self.url+'/imports/'+p['id']+'/confirm',{'items':[{'item_id':p['items'][0]['id'],'number':1}]})
        self.assertEqual(recreated.status_code,200);self.assertNotEqual(recreated.json()['chapter_ids'][0],row['id'])
        self.assertEqual(self.c.get(self.url+'/chapters').json()['total'],45)
    def test_active_job_revision_cross_book_and_local_boundary(self):
        row=self.row();other=self.post('/api/v1/books',{'name':'B','language':'vi','request_id':str(uuid4())}).json()['id']
        self.assertEqual(self.remove(row,'/api/v1/books/'+other).status_code,404)
        self.assertEqual(self.remove(row,revision=99).status_code,409)
        self.assertEqual(self.c.request('DELETE',self.url+'/chapters/'+row['id'],json={'revision':1}).status_code,403)
        self.assertEqual(self.c.request('DELETE',self.url+'/chapters/'+row['id'],json={},headers=self.h).status_code,422)
        for status in ['queued','running','stop_requested']:
            identifier=str(uuid4())
            with session_scope(self.c.app.state.repository.engine) as db:db.add(Job(id=identifier,book_id=self.book,kind='tts',status=status,config_json=json.dumps({'plan':{'chapters':[{'id':row['id']}]}})))
            blocked=self.remove(row);self.assertEqual(blocked.status_code,409);self.assertIn(identifier,blocked.text)
            with session_scope(self.c.app.state.repository.engine) as db:db.delete(db.get(Job,identifier))
        remaining=self.c.get(self.url+'/chapters').json()['items'][1]
        with session_scope(self.c.app.state.repository.engine) as db:db.add(Job(book_id=self.book,kind='tts',status='running',config_json=json.dumps({'plan':{'chapters':[{'id':remaining['id']}]}})))
        self.assertEqual(self.remove(row).status_code,200)
    def test_failed_delete_rolls_back_archive_and_old_previews_cannot_resurrect(self):
        row=self.row()
        with patch('api.chapter_deletion.delete',side_effect=RuntimeError('injected database failure')):
            with self.assertRaises(RuntimeError):self.remove(row)
        self.assertEqual(self.c.get(self.url+'/chapters/'+row['id']).status_code,200)
        self.assertEqual(list((self.root/'deleted-chapters').glob('*.json')),[])
        p=self.post(self.url+'/text-imports',{'number':1,'content':'Changed'}).json()
        with session_scope(self.c.app.state.repository.engine) as db:
            original=next(s for s in db.exec(select(ImportSession)).all() if s.status=='confirmed' and row['id'] in json.loads(s.result_json)['chapter_ids'])
            saved=json.loads(original.result_json);original_id=original.id
        self.assertEqual(self.remove(row).status_code,200)
        self.assertEqual(self.post(self.url+'/imports/'+p['id']+'/confirm',{'items':[{'item_id':p['items'][0]['id'],'number':1,'action':'update'}]}).status_code,409)
        self.assertEqual(self.post(self.url+'/imports/'+original_id+'/confirm',{'items':[{'item_id':item,'number':number,'action':action} for item,number,action in saved['selection']]}).status_code,409)
        self.assertEqual(self.c.get(self.url+'/chapters').json()['total'],44)
    def test_archive_path_guard_and_backup_retains_deleted_sources(self):
        import shutil
        from api.backup import backup,restore
        row=self.row();outside=self.root/'archive-target';outside.mkdir();link=self.root/'deleted-chapters';link.symlink_to(outside)
        self.assertEqual(self.remove(row).status_code,409);self.assertEqual(self.c.get(self.url+'/chapters/'+row['id']).status_code,200)
        self.assertEqual(list(outside.iterdir()),[]);link.unlink()
        self.assertEqual(self.remove(row).status_code,200)
        copy=self.root.parent/('deletion-backup-'+str(uuid4()));restored=self.root.parent/('deletion-restore-'+str(uuid4()))
        self.addCleanup(lambda:shutil.rmtree(copy,ignore_errors=True));self.addCleanup(lambda:shutil.rmtree(restored,ignore_errors=True))
        self.assertEqual(backup(self.root,copy)['status'],'verified');self.assertEqual(restore(copy,restored)['status'],'verified')
        self.assertTrue(list((restored/'deleted-chapters').glob('*.json')))
        self.assertEqual((restored/'books'/self.book/'chapters'/row['id']/'source.txt').read_bytes(),self.raw)
        from api.books import BookRepository
        from api.chapters import listing
        repo=BookRepository(restored)
        try:self.assertEqual(listing(repo,self.book).total,44)
        finally:repo.engine.dispose()
