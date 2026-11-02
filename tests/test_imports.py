"""T06 no chapters before confirm, copy exact bytes, validation and replay."""
import base64
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.client=TestClient(create_app(Settings(data_dir=self.root)),base_url='http://127.0.0.1:8001');self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.headers={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
        self.books=[self.post('/api/v1/books',{'name':n,'language':'vi','request_id':str(uuid4())}).json()['id'] for n in ['A','B']]
        self.url='/api/v1/books/'+self.books[0]

    def post(self,url,body):return self.client.post(url,json=body,headers=self.headers)
    def file(self,name,content):return {'name':name,'content_base64':base64.b64encode(content).decode()}
    def preview(self,files):
        r=self.post(self.url+'/imports',{'files':files});self.assertEqual(r.status_code,201,r.text);return r.json()
    def chapters(self):return self.client.get(self.url+'/chapters').json()['items']

    def test_preview_confirm_repeat_sorted_and_exact_copy(self):
        raw='Chương Việt\r\nNội dung 👋'.encode('utf-8')
        session=self.preview([self.file('10_vi.txt',raw),self.file('1_vi.txt',b'One'),self.file('2_vi.txt',b'Two'),self.file('empty.txt',b''),self.file('bad.txt',b'\xff')])
        self.assertEqual(self.chapters(),[])
        choices=[{'item_id':x['id'],'number':x['number']} for x in session['items'] if x['status']=='ready']
        url=self.url+'/imports/'+session['id']+'/confirm'
        result=self.post(url,{'items':choices});self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.post(url,{'items':choices}).json()['chapter_ids'],result.json()['chapter_ids'])
        self.assertEqual([x['number'] for x in self.chapters()],[1,2,10])
        chapter=self.chapters()[-1];self.assertEqual((self.root/'books'/self.books[0]/'chapters'/chapter['id']/'source.txt').read_bytes(),raw)
        self.assertEqual(self.client.get('/api/v1/books/'+self.books[1]+'/chapters').json()['items'],[])

    def test_cancel_preview_does_not_create_chapters(self):
        session=self.preview([self.file('1.txt',b'One')]);url=self.url+'/imports/'+session['id']
        self.assertEqual(self.post(url+'/cancel',{}).json()['status'],'cancelled')
        self.assertEqual(self.chapters(),[]);self.assertFalse((self.root/'imports'/session['id']).exists())
        self.assertEqual(self.post(url+'/confirm',{'items':[{'item_id':session['items'][0]['id'],'number':1}]}).status_code,409)

    def test_limits_names_utf8_and_manual_number(self):
        for name in ['../x.txt','a/b.txt','a\\b.txt','x.mp3']:
            self.assertEqual(self.post(self.url+'/imports',{'files':[self.file(name,b'hi')]}).status_code,422)
        self.assertEqual(self.post(self.url+'/imports',{'files':[self.file('1.txt',b'x'*(256*1024+1))]}).status_code,413)
        session=self.preview([self.file('intro.txt',b'Intro')]);self.assertEqual(session['items'][0]['status'],'needs_number')
        self.assertEqual(self.post(self.url+'/imports/'+session['id']+'/confirm',{'items':[{'item_id':session['items'][0]['id'],'number':0}]}).status_code,200)

    def test_duplicate_and_changed_staging_roll_back_all(self):
        session=self.preview([self.file('1.txt',b'one'),self.file('2.txt',b'two')]);items=[{'item_id':x['id'],'number':x['number']} for x in session['items']]
        url=self.url+'/imports/'+session['id']+'/confirm'
        self.assertEqual(self.post(url,{'items':[items[0],{**items[1],'number':1}]}).status_code,409)
        (self.root/'imports'/session['id']/(items[1]['item_id']+'.txt')).write_bytes(b'changed')
        self.assertEqual(self.post(url,{'items':items}).status_code,409)
        self.assertEqual(self.chapters(),[])
        self.assertEqual(list((self.root/'books'/self.books[0]/'chapters').glob('*/source.txt')),[])

    def test_cross_book_import_denied_and_transport_limit(self):
        session=self.preview([self.file('1.txt',b'One')])
        r=self.client.get('/api/v1/books/'+self.books[1]+'/imports/'+session['id']);self.assertEqual(r.status_code,404)
        r=self.client.post(self.url+'/imports',content=b'x'*(8*1024*1024+1),headers={**self.headers,'content-type':'application/json'})
        self.assertEqual(r.status_code,413)
