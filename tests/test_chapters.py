"""T09/T10 paging, selection isolation and exact artifact retrieval."""
import base64
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings


class ChapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.c=TestClient(create_app(Settings(data_dir=self.root)),base_url='http://127.0.0.1:8001');self.c.__enter__();self.addCleanup(self.c.__exit__,None,None,None)
        self.h={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
        self.book=self.post('/api/v1/books',{'name':'A','language':'vi','request_id':str(uuid4())}).json()['id'];self.url='/api/v1/books/'+self.book
        self.raw='Nội dung Việt\r\nDòng 2 👋'.encode()
        for start in [1,21,41]:
            files=[{'name':f'{n}.txt','content_base64':base64.b64encode(self.raw).decode()} for n in range(start,min(start+20,46))]
            preview=self.post(self.url+'/imports',{'files':files}).json()
            self.post(self.url+'/imports/'+preview['id']+'/confirm',{'items':[{'item_id':i['id'],'number':i['number']} for i in preview['items']]})
    def post(self,url,body):return self.c.post(url,json=body,headers=self.h)

    def test_natural_order_pages_filters_and_range(self):
        first=self.c.get(self.url+'/chapters').json();second=self.c.get(self.url+'/chapters?offset=20').json()
        self.assertEqual(first['total'],45);self.assertEqual([x['number'] for x in first['items']],list(range(1,21)))
        self.assertEqual(second['items'][0]['number'],21)
        found=self.c.get(self.url+'/chapters?q=10').json();self.assertEqual([x['number'] for x in found['items']],[10])
        self.assertEqual(self.c.get(self.url+'/chapters?status=audio_ready').json()['total'],0)
        self.assertEqual(self.c.get(self.url+'/chapters?status=source_ready').json()['total'],45)
        selection=self.c.get(self.url+'/chapter-selection?start=1&end=10').json();self.assertEqual([x['number'] for x in selection['items']],list(range(1,11)))
        self.assertEqual(self.c.get(self.url+'/chapter-selection?start=10&end=1').status_code,422)

    def test_detail_and_download_exact_bytes_and_isolation(self):
        chapter=self.c.get(self.url+'/chapters').json()['items'][0]
        detail=self.c.get(self.url+'/chapters/'+chapter['id']).json()
        self.assertEqual(detail['source']['text'],self.raw.decode());self.assertIsNone(detail['translation'])
        artifact=detail['source']['artifact_id'];download=self.c.get(self.url+'/artifacts/'+artifact+'/download')
        self.assertEqual(download.content,self.raw);self.assertIn('attachment',download.headers['content-disposition'])
        other=self.post('/api/v1/books',{'name':'B','language':'vi','request_id':str(uuid4())}).json()['id']
        self.assertEqual(self.c.get('/api/v1/books/'+other+'/chapters/'+chapter['id']).status_code,404)
        self.assertEqual(self.c.get('/api/v1/books/'+other+'/artifacts/'+artifact+'/download').status_code,404)
        self.assertEqual(self.c.get(self.url+'/chapters/'+str(uuid4())).status_code,404)
        (self.root/'books'/self.book/'chapters'/chapter['id']/'source.txt').write_bytes(b'tampered')
        self.assertEqual(self.c.get(self.url+'/artifacts/'+artifact+'/download').status_code,409)
