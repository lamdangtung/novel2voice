"""T29 integrated local request boundary, media and filesystem regression suite."""
import unittest
import test_chapters as fixtures

class BoundaryTests(fixtures.ChapterTests):
    test_natural_order_pages_filters_and_range=None
    test_detail_and_download_exact_bytes_and_isolation=None
    def test_untrusted_requests_oversized_stream_and_owned_artifacts(self):
        url='/api/v1/books'
        self.assertEqual(self.c.get(url,headers={'host':'attacker.example:8001'}).status_code,400)
        self.assertEqual(self.c.get(url,headers={'origin':'http://attacker.example'}).status_code,403)
        for headers in [{},{'origin':self.h['origin']},{'x-novel2voice-client':'web'},{**self.h,'origin':'null'}]:
            self.assertEqual(self.c.post(url,json={},headers=headers).status_code,403)
        self.assertEqual(self.c.post(url,content='{}',headers={**self.h,'content-type':'text/plain'}).status_code,415)
        self.assertEqual(self.c.post(url,content=b'x'*(8*1024*1024+1),headers={**self.h,'content-type':'application/json'}).status_code,413)
        row=self.c.get(self.url+'/chapters').json()['items'][0]
        artifact=self.c.get(self.url+'/chapters/'+row['id']).json()['source']['artifact_id']
        path=self.root/'books'/self.book/'chapters'/row['id']/'source.txt'
        secret=self.root.parent/('n2v-secret-'+self.book);secret.write_text('PRIVATE_SENTINEL')
        self.addCleanup(secret.unlink)
        path.unlink();path.symlink_to(secret)
        response=self.c.get(self.url+'/artifacts/'+artifact+'/download')
        self.assertEqual(response.status_code,409);self.assertNotIn('PRIVATE_SENTINEL',response.text)
        self.assertEqual(secret.read_text(),'PRIVATE_SENTINEL')
        self.assertEqual(self.c.get('/api/v1/books/%2e%2e/artifacts/'+artifact+'/download').status_code,422)
