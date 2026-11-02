import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from api.books import BookRepository, CreateBook, BookError
from api.glossaries import read, save, parse, GlossaryUpload


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.repo=BookRepository(self.root/'data');self.addCleanup(self.repo.engine.dispose)
        self.books=[self.repo.create(CreateBook(name=x,language='en',request_id=uuid4())).id for x in ['A','B']]
        (self.root/'glossary.csv').write_text('en,vi\nDefault,Mặc định\n')
        p=patch('api.glossaries.PROJECT_ROOT',self.root);p.start();self.addCleanup(p.stop)
    def upload(self,raw,revision=0):return GlossaryUpload(name='terms.csv',content_base64=base64.b64encode(raw).decode(),revision=revision)
    def test_own_glossary_default_isolation_versions_restart(self):
        a,b=self.books
        first=save(self.repo,a,self.upload('en,vi\nNorth,Phương Bắc\n'.encode()))
        self.assertEqual(first['revision'],1);self.assertEqual(read(self.repo,b)['source'],'server')
        second=save(self.repo,a,self.upload(b'en,vi\nSouth,Nam\n',1));self.assertEqual(len(second['versions']),2)
        old=self.repo.root/'books'/a/'glossary'/(first['versions'][0]['id']+'.csv');self.assertIn('Phương Bắc',old.read_text())
        other=BookRepository(self.repo.root);self.addCleanup(other.engine.dispose);self.assertEqual(read(other,a)['entries'][0]['en'],'South')
    def test_bad_rows_do_not_replace_previous_and_revision_conflict(self):
        a=self.books[0];first=save(self.repo,a,self.upload(b'en,vi\nA,B\n'))
        for invalid in [b'wrong,header\nA,B\n',b'en,vi\nA,\n',b'en,vi\nA,B\nA,C\n',b'\xff']:
            with self.assertRaises(BookError):save(self.repo,a,self.upload(invalid,1))
            self.assertEqual(read(self.repo,a)['sha256'],first['sha256'])
        with self.assertRaises(BookError):save(self.repo,a,self.upload(b'en,vi\nC,D\n',0))
    def test_legacy_default_duplicate_uses_last_value(self):
        raw=b'en,vi\nA,First\nA,Last\n'
        self.assertEqual(parse(raw,legacy=True),[{'en':'A','vi':'Last'}])
        with self.assertRaises(BookError):parse(raw)

    def test_line_errors_and_quoted_csv(self):
        self.assertEqual(parse(b'en,vi\n"A,B","C,D"\n')[0]['en'],'A,B')
        with self.assertRaisesRegex(BookError,'Dòng 3'):parse(b'en,vi\nA,B\nC,\n')
