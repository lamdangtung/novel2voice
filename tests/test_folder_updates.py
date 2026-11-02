"""T07/T08 roots, recursive scan, source freshness and version preservation."""
import base64
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings


class FolderUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.source=self.root/'source';self.source.mkdir()
        self.patcher=patch('api.import_sources.roots',return_value={'input':self.source});self.patcher.start();self.addCleanup(self.patcher.stop)
        self.c=TestClient(create_app(Settings(data_dir=self.root/'data')),base_url='http://127.0.0.1:8001');self.c.__enter__();self.addCleanup(self.c.__exit__,None,None,None)
        self.h={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
        self.book=self.post('/api/v1/books',{'name':'A','language':'vi','request_id':str(uuid4())}).json()['id'];self.url='/api/v1/books/'+self.book
    def post(self,url,body):return self.c.post(url,json=body,headers=self.h)
    def folder(self,recursive=False):
        return self.post(self.url+'/folder-imports',{'source':'input','directory':'','recursive':recursive})
    def confirm(self,session,action='import'):
        return self.post(self.url+'/imports/'+session['id']+'/confirm',{'items':[{'item_id':x['id'],'number':x['number'],'action':action} for x in session['items'] if x['status']!='invalid']})
    def upload(self,content):
        r=self.post(self.url+'/imports',{'files':[{'name':'1.txt','content_base64':base64.b64encode(content).decode()}]});self.assertEqual(r.status_code,201,r.text);return r.json()

    def test_recursion_changes_preview_then_confirm_preserves_sources(self):
        (self.source/'1.txt').write_bytes(b'one');(self.source/'ep').mkdir();(self.source/'ep/2.txt').write_bytes(b'two')
        flat=self.folder().json();nested=self.folder(True).json();self.assertEqual(len(flat['items']),1);self.assertEqual(len(nested['items']),2)
        r=self.confirm(nested);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual((self.source/'ep/2.txt').read_bytes(),b'two')
        self.assertEqual([x['number'] for x in self.c.get(self.url+'/chapters').json()['items']],[1,2])

    def test_outside_and_symlink_rejected_before_file_read(self):
        (self.source/'1.txt').write_bytes(b'one');outside=self.root/'outside';outside.mkdir();(outside/'2.txt').write_bytes(b'private')
        (self.source/'escape').symlink_to(outside)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('must not read TXT')):
            self.assertEqual(self.folder(True).status_code,403)
            self.assertEqual(self.post(self.url+'/folder-imports',{'source':'input','directory':'../outside','recursive':True}).status_code,403)
        self.assertEqual(self.post(self.url+'/folder-imports',{'source':'unknown'}).status_code,403)

    def test_source_changes_after_preview_requires_new_preview(self):
        source=self.source/'1.txt';source.write_bytes(b'one');session=self.folder().json();source.write_bytes(b'changed')
        self.assertEqual(self.confirm(session).status_code,409)
        self.assertEqual(self.c.get(self.url+'/chapters').json()['items'],[])

    def test_identical_skip_update_explicit_old_bytes_and_ids_preserved(self):
        first=self.upload(b'original');result=self.confirm(first);self.assertEqual(result.status_code,200,result.text);identifier=result.json()['chapter_ids'][0]
        original=self.root/'data/books'/self.book/'chapters'/identifier/'source.txt'
        identical=self.upload(b'original');self.assertEqual(identical['items'][0]['status'],'identical')
        self.assertEqual(self.confirm(identical).json()['outcomes'][0]['action'],'skipped')
        changed=self.upload(b'updated');self.assertEqual(changed['items'][0]['status'],'changed')
        self.assertEqual(self.confirm(changed).status_code,409)
        update=self.confirm(changed,'update');self.assertEqual(update.status_code,200,update.text)
        self.assertEqual(update.json()['chapter_ids'],[identifier]);self.assertEqual(original.read_bytes(),b'original')
        files=list(original.parent.glob('*.txt'));self.assertEqual(len(files),2);self.assertIn(b'updated',[p.read_bytes() for p in files])
        chapter=self.c.get(self.url+'/chapters').json()['items'][0];self.assertEqual(chapter['revision'],2)
        self.assertTrue(update.json()['outcomes'][0]['dependent_artifacts_need_refresh'])

    def test_parallel_previews_cannot_overwrite_unseen_revision(self):
        self.confirm(self.upload(b'original'));a=self.upload(b'update-a');b=self.upload(b'update-b')
        self.assertEqual(self.confirm(a,'update').status_code,200)
        self.assertEqual(self.confirm(b,'update').status_code,409)
