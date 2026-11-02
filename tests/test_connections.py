"""T26 key presence only, URL credentials/query redaction and no key writes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api.books import BookRepository,BookError
from api.connections import read,endpoint
from api.configuration import save,SaveConfig


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.repo=BookRepository(Path(self.tmp.name).resolve());self.addCleanup(self.repo.engine.dispose)
    def test_key_presence_and_redacted_endpoint_without_secret(self):
        secret='test-secret-not-real-123';env={'OPENAI_API_KEY':secret,'HF_TOKEN':'test-hf-secret','OPENAI_BASE_URL':'https://user:password@example.test/v1?token='+secret+'#secret'}
        with patch('api.connections.read_config',return_value=env):result=read(self.repo)
        self.assertTrue(result['translation']['key_configured']);self.assertEqual(result['translation']['endpoint']['display'],'https://example.test/v1')
        self.assertNotIn(secret,str(result));self.assertNotIn('password',str(result));self.assertNotIn('test-hf-secret',str(result))
        with patch('api.connections.read_config',return_value={}):self.assertFalse(read(self.repo)['translation']['key_configured'])
    def test_ordinary_save_cannot_write_key_or_mask(self):
        for key in ['OPENAI_API_KEY','HF_TOKEN','api_key']:
            with self.assertRaises(BookError):save(self.repo,SaveConfig(revision=0,values={key:'***'}))
        with patch.dict('os.environ',{'OPENAI_API_KEY':'unchanged-test-key'}):
            save(self.repo,SaveConfig(revision=0,values={'cleanup':False}))
            import os
            self.assertEqual(os.environ['OPENAI_API_KEY'],'unchanged-test-key')
    def test_invalid_url_never_echoed(self):
        self.assertIsNone(endpoint('not a URL with secret')['display'])
        self.assertIsNone(endpoint('https://example.test:wrong/secret')['display'])
