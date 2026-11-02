"""T13/T14 real ffprobe import and Range/download contracts, no model/network."""
import base64
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Needs local FFmpeg/ffprobe')
class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory();cls.tone=Path(cls.fixture.name)/'tone.mp3'
        subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','libmp3lame',str(cls.tone)],check=True)
        cls.raw=cls.tone.read_bytes()
    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.c=TestClient(create_app(Settings(data_dir=self.root)),base_url='http://127.0.0.1:8001');self.c.__enter__();self.addCleanup(self.c.__exit__,None,None,None)
        self.h={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
        self.book=self.post('/api/v1/books',{'name':'Audio A','language':'vi','request_id':str(uuid4())}).json()['id'];self.url='/api/v1/books/'+self.book
        preview=self.post(self.url+'/imports',{'files':[{'name':'1.txt','content_base64':base64.b64encode(b'One').decode()}]}).json()
        result=self.post(self.url+'/imports/'+preview['id']+'/confirm',{'items':[{'item_id':preview['items'][0]['id'],'number':1}]}).json();self.chapter=result['chapter_ids'][0]
    def post(self,url,body):return self.c.post(url,json=body,headers=self.h)
    def preview(self):
        r=self.post(self.url+'/audio-imports',{'files':[{'name':'chapter_1.mp3','content_base64':base64.b64encode(self.raw).decode()},{'name':'1.mp3','content_base64':base64.b64encode(self.raw).decode()},{'name':'bad.mp3','content_base64':base64.b64encode(b'broken').decode()}]});self.assertEqual(r.status_code,201,r.text);return r.json()
    def confirmed(self):
        preview=self.preview();body={'items':[{'item_id':preview['items'][0]['id'],'chapter_id':self.chapter}]};url=self.url+'/audio-imports/'+preview['id']+'/confirm'
        result=self.post(url,body);self.assertEqual(result.status_code,200,result.text)
        return result.json()['outcomes'][0]['artifact_id'],url,body

    def test_valid_invalid_ambiguous_preview_and_confirm_idempotent(self):
        preview=self.preview();a,b,c=preview['items'];self.assertTrue(a['valid']);self.assertEqual(a['suggested_chapter_id'],self.chapter);self.assertIsNone(b['suggested_chapter_id']);self.assertFalse(c['valid'])
        self.assertEqual(self.post(self.url+'/audio-imports/'+preview['id']+'/confirm',{'items':[{'item_id':c['id'],'chapter_id':self.chapter}]}).status_code,409)
        artifact,url,body=self.confirmed();self.assertEqual(self.post(url,body).json()['outcomes'][0]['artifact_id'],artifact)
        artifact2,_,_=self.confirmed();self.assertEqual(artifact2,artifact)
        self.assertEqual(len(self.c.get(self.url+'/chapters/'+self.chapter+'/audio').json()['items']),1)

    def test_range_download_checksum_stale_and_wrong_book(self):
        artifact,_,_=self.confirmed();url=self.url+'/audio/'+artifact
        response=self.c.get(url,headers={'range':'bytes=10-99'});self.assertEqual(response.status_code,206);self.assertEqual(response.content,self.raw[10:100]);self.assertEqual(response.headers['accept-ranges'],'bytes')
        self.assertEqual(self.c.get(url,headers={'range':'bytes=999999-'}).status_code,416)
        self.assertEqual(self.c.get(url+'?download=true').content,self.raw)
        other=self.post('/api/v1/books',{'name':'B','language':'vi','request_id':str(uuid4())}).json()['id'];self.assertEqual(self.c.get('/api/v1/books/'+other+'/audio/'+artifact).status_code,404)
        preview=self.post(self.url+'/imports',{'files':[{'name':'1.txt','content_base64':base64.b64encode(b'Changed').decode()}]}).json()
        self.assertEqual(self.post(self.url+'/imports/'+preview['id']+'/confirm',{'items':[{'item_id':preview['items'][0]['id'],'number':1,'action':'update'}]}).status_code,200)
        audio=self.c.get(self.url+'/chapters/'+self.chapter+'/audio').json()['items'][0];self.assertTrue(audio['stale']);self.assertTrue(audio['selected'])
        self.assertEqual(self.c.get(url).content,self.raw)

    def test_missing_or_tampered_audio_not_served(self):
        artifact,_,_=self.confirmed();path=next((self.root/'books'/self.book/'chapters'/self.chapter/'audio').glob('*.mp3'))
        path.write_bytes(b'tamper');self.assertEqual(self.c.get(self.url+'/audio/'+artifact).status_code,409)
        path.unlink();self.assertEqual(self.c.get(self.url+'/audio/'+artifact).status_code,404)
