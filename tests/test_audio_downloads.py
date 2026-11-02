"""ZIP exports respect scope, selected current audio, snapshots and bounded resources."""
import hashlib,io,json,zipfile
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import test_chapters as fixtures
from sqlmodel import select
from api.storage import session_scope
from api.storage.models import Artifact,Chapter
from api.audio_downloads import cleanup,locked,MAX_BYTES

class AudioDownloadTests(fixtures.ChapterTests):
    test_natural_order_pages_filters_and_range=None
    test_detail_and_download_exact_bytes_and_isolation=None
    def setUp(self):
        super().setUp();self.chapters=self.c.get(self.url+'/chapters?limit=100').json()['items'];self.artifacts={}
        for number in [1,2,10,21,45]:self.add_audio(number)
    def add_audio(self,number,selected=True,verified=True):
        chapter=next(c for c in self.chapters if c['number']==number);identifier=str(uuid4());path=self.root/'books'/self.book/f'{identifier}.mp3';raw=('Audio '+str(number)).encode();path.write_bytes(raw)
        with session_scope(self.c.app.state.repository.engine) as db:
            source=db.get(Chapter,chapter['id'])
            db.add(Artifact(id=identifier,chapter_id=chapter['id'],kind='audio',relative_path=path.relative_to(self.root).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),verified=verified,provenance=json.dumps({'method':'imported','selected':selected,'source_hash':source.source_hash})))
        self.artifacts[number]=(identifier,path,raw)
    def preview(self,body):
        r=self.post(self.url+'/audio-downloads/preview',body);self.assertEqual(r.status_code,201,r.text);return r.json()
    def prepare(self,p):return self.post(self.url+'/audio-downloads/'+p['id']+'/prepare',{})
    def test_range_gaps_missing_natural_order_exact_zip_and_repeated_prepare(self):
        p=self.preview({'mode':'range','start':1,'end':10});self.assertEqual(p['ready_count'],3);self.assertEqual(p['skipped_count'],7)
        result=self.prepare(p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.prepare(p).json(),result.json())
        response=self.c.get(result.json()['download_path']);self.assertEqual(response.status_code,200);self.assertIn('attachment',response.headers['content-disposition'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            self.assertEqual([n.split(' - ')[0] for n in z.namelist()],['0001','0002','0010'])
            for number,name in zip([1,2,10],z.namelist()):self.assertEqual(z.read(name),self.artifacts[number][2])
        self.assertEqual(self.c.get(result.json()['download_path'],headers={'range':'bytes=0-99'}).status_code,206)
        p=self.preview({'mode':'range','start':44,'end':47});self.assertEqual(p['ready_count'],1);self.assertEqual(p['skipped_count'],3)
        self.assertTrue(any(i['number']==46 and 'Không có chương' in i['reason'] for i in p['items']))
    def test_selected_across_pages_exact_scope_validation_and_filename_safety(self):
        chosen=[self.chapters[n-1]['id'] for n in [45,21,1]]
        with session_scope(self.c.app.state.repository.engine) as db:db.get(Chapter,chosen[-1]).title='../../evil\\path <script>👋'
        p=self.preview({'mode':'selected','chapter_ids':chosen});self.assertEqual([i['number'] for i in p['items']],[1,21,45])
        response=self.c.get(self.prepare(p).json()['download_path'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            self.assertEqual(len(z.namelist()),3)
            self.assertTrue(all('/' not in n and '\\' not in n for n in z.namelist()))
        for body in [{'mode':'selected','chapter_ids':[]},{'mode':'selected','chapter_ids':[chosen[0],chosen[0]]},{'mode':'range','start':10,'end':1},{'mode':'range','start':0,'end':500},{'mode':'selected','chapter_ids':chosen,'start':1},{'mode':'range','start':1,'end':2,'chapter_ids':chosen}]:
            self.assertEqual(self.post(self.url+'/audio-downloads/preview',body).status_code,422)
        self.assertEqual(self.post(self.url+'/audio-downloads/preview',{'mode':'selected','chapter_ids':[str(uuid4())]}).status_code,409)
        self.assertEqual(self.c.post(self.url+'/audio-downloads/preview',json={'mode':'range','start':1,'end':2}).status_code,403)
        other=self.post('/api/v1/books',{'name':'Other','language':'vi','request_id':str(uuid4())}).json()['id']
        self.assertEqual(self.post('/api/v1/books/'+other+'/audio-downloads/'+p['id']+'/prepare',{}).status_code,404)
        self.assertEqual(self.c.get('/api/v1/books/'+other+'/audio-downloads/'+p['id']+'/file').status_code,404)
    def test_stale_corrupt_unselected_and_empty_export(self):
        self.artifacts[1][1].write_bytes(b'tampered')
        with session_scope(self.c.app.state.repository.engine) as db:db.get(Artifact,self.artifacts[2][0]).verified=False
        self.add_audio(3,selected=False)
        p=self.preview({'mode':'range','start':1,'end':3});self.assertEqual(p['ready_count'],0);self.assertEqual(self.prepare(p).status_code,409)
        self.assertFalse((self.root/'audio-downloads'/p['id']/'audio.zip').exists())
    def test_snapshot_changed_source_selection_or_deleted_chapter_blocks_publish(self):
        for change in ['source','selection','file','delete']:
            p=self.preview({'mode':'range','start':10,'end':10})
            with session_scope(self.c.app.state.repository.engine) as db:
                chapter=db.get(Chapter,self.chapters[9]['id']);artifact=db.get(Artifact,self.artifacts[10][0])
                if change=='source':chapter.revision+=1
                elif change=='selection':data=json.loads(artifact.provenance);data['selected']=False;artifact.provenance=json.dumps(data)
                elif change=='file':self.artifacts[10][1].unlink()
                else:
                    for row in db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id)).all():db.delete(row)
                    db.flush();db.delete(chapter)
            self.assertEqual(self.prepare(p).status_code,409)
            self.assertFalse((self.root/'audio-downloads'/p['id']/'audio.zip').exists())
            if change=='file':self.artifacts[10][1].write_bytes(self.artifacts[10][2])
            if change=='selection':
                with session_scope(self.c.app.state.repository.engine) as db:
                    artifact=db.get(Artifact,self.artifacts[10][0]);data=json.loads(artifact.provenance);data['selected']=True;artifact.provenance=json.dumps(data)
    def test_limits_disk_error_cleanup_expiration_and_active_lock(self):
        with patch('api.audio_downloads.MAX_BYTES',1):self.assertEqual(self.post(self.url+'/audio-downloads/preview',{'mode':'range','start':1,'end':1}).status_code,413)
        p=self.preview({'mode':'range','start':1,'end':1});directory=self.root/'audio-downloads'/p['id']
        with patch('api.audio_downloads.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):self.assertEqual(self.prepare(p).status_code,409)
        with patch('api.audio_downloads.zipfile.ZipFile',side_effect=OSError('disk failure')):
            self.assertEqual(self.prepare(p).status_code,409)
        self.assertFalse((directory/'audio.partial.zip').exists());self.assertFalse((directory/'audio.zip').exists())
        plan=json.loads((directory/'plan.json').read_text());plan['expires_at']=0;(directory/'plan.json').write_text(json.dumps(plan))
        with locked(directory,shared=True):cleanup(directory.parent);self.assertTrue(directory.exists())
        self.assertEqual(self.prepare(p).status_code,409);cleanup(directory.parent);self.assertFalse(directory.exists())
