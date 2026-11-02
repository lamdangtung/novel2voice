"""Direct text reuses staged imports, preserving exact Unicode and update safeguards."""
import json
import test_imports as fixtures
from api.storage import session_scope
from api.storage.models import Artifact
from sqlmodel import select

class TextImportTests(fixtures.ImportTests):
    test_preview_confirm_repeat_sorted_and_exact_copy=None
    test_cancel_preview_does_not_create_chapters=None
    test_limits_names_utf8_and_manual_number=None
    test_duplicate_and_changed_staging_roll_back_all=None
    test_cross_book_import_denied_and_transport_limit=None
    def preview_text(self,content,number=7,title='Tên chương 👋'):
        r=self.post(self.url+'/text-imports',{'number':number,'title':title,'content':content})
        self.assertEqual(r.status_code,201,r.text);return r.json()
    def confirm_text(self,p,action='import'):
        return self.post(self.url+'/imports/'+p['id']+'/confirm',{'items':[{'item_id':p['items'][0]['id'],'number':p['items'][0]['number'],'action':action}]})
    def test_exact_content_preview_confirm_replay_and_provenance(self):
        content='第一章。\r\nTiếng Việt 👋\n\n  Khoảng trắng cuối  '
        p=self.preview_text(content);self.assertEqual(self.chapters(),[])
        result=self.confirm_text(p);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.confirm_text(p).json()['chapter_ids'],result.json()['chapter_ids'])
        chapter=self.chapters()[0];self.assertEqual(chapter['title'],'Tên chương 👋');self.assertEqual(chapter['number'],7)
        detail=self.client.get(self.url+'/chapters/'+chapter['id']).json()
        self.assertEqual(detail['source']['text'],content)
        artifact=detail['source']['artifact_id']
        self.assertEqual(self.client.get(self.url+'/artifacts/'+artifact+'/download').content,content.encode())
        with session_scope(self.client.app.state.repository.engine) as db:
            metadata=json.loads(db.get(Artifact,artifact).provenance)
            self.assertEqual(metadata['method'],'direct_text')
        self.assertEqual(self.client.get('/api/v1/books/'+self.books[1]+'/imports/'+p['id']).status_code,404)
    def test_cancel_duplicate_and_changed_text_requires_explicit_update(self):
        canceled=self.preview_text('Bản nháp')
        self.assertEqual(self.post(self.url+'/imports/'+canceled['id']+'/cancel',{}).status_code,200)
        self.assertEqual(self.chapters(),[])
        original=self.preview_text('Bản đầu',title='');self.assertEqual(self.confirm_text(original).status_code,200)
        chapter=self.chapters()[0];self.assertEqual(chapter['title'],'Chương 7')
        same=self.preview_text('Bản đầu');self.assertEqual(same['items'][0]['status'],'identical')
        self.assertEqual(self.confirm_text(same).status_code,200);self.assertEqual(len(self.chapters()),1)
        changed=self.preview_text('Bản mới',title='Tiêu đề mới');self.assertEqual(changed['items'][0]['status'],'changed')
        self.assertEqual(self.confirm_text(changed).status_code,409)
        self.assertEqual(self.confirm_text(changed,'update').status_code,200)
        self.assertEqual(self.chapters()[0]['id'],chapter['id']);self.assertEqual(self.chapters()[0]['title'],'Tiêu đề mới')
        self.assertEqual((self.root/'books'/self.books[0]/'chapters'/chapter['id']/'source.txt').read_text(),'Bản đầu')
    def test_empty_unicode_byte_limits_numbers_titles_and_local_boundary(self):
        body={'number':1,'content':'Valid'}
        for patch in [{'content':''},{'content':' \n\t '},{'content':'a\x00b'},{'number':-1},{'number':1.5},{'number':100000000},{'title':'bad\x00title'}]:
            self.assertEqual(self.post(self.url+'/text-imports',{**body,**patch}).status_code,422,repr(patch))
        raw=json.dumps({**body,'content':'\ud800'})
        self.assertEqual(self.client.post(self.url+'/text-imports',content=raw,headers={**self.headers,'content-type':'application/json'}).status_code,422)
        oversized='界'*90000
        self.assertEqual(self.post(self.url+'/text-imports',{**body,'content':oversized}).status_code,413)
        self.assertEqual(self.client.post(self.url+'/text-imports',json=body).status_code,403)
        p=self.preview_text('x'*(256*1024),number=0,title='')
        self.assertEqual(p['items'][0]['size'],256*1024)
