"""T11 inherited configuration, validation, optimistic save and persistence."""
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch
from api.books import BookRepository, CreateBook, BookError
from api.configuration import read, save, SaveConfig


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.repo=BookRepository(self.root);self.addCleanup(self.repo.engine.dispose)
        self.a=self.repo.create(CreateBook(name='A',language='vi',request_id=uuid4())).id
        self.b=self.repo.create(CreateBook(name='B',language='vi',request_id=uuid4())).id
        self.mock=patch('api.configuration.read_config',return_value={'TTS_PROVIDER':'vieneu'});self.mock.start();self.addCleanup(self.mock.stop)

    def test_inheritance_own_voice_and_defaults_changes_persist(self):
        save(self.repo,SaveConfig(revision=0,values={'voice':'default-1','concurrency':2}))
        save(self.repo,SaveConfig(revision=0,values={'voice':'own-a'}),self.a)
        self.assertEqual(read(self.repo,self.a)['effective']['voice'],'own-a')
        self.assertEqual(read(self.repo,self.b)['effective']['voice'],'default-1')
        save(self.repo,SaveConfig(revision=1,values={'voice':'default-2','concurrency':4}))
        self.assertEqual(read(self.repo,self.a)['effective']['voice'],'own-a')
        self.assertEqual(read(self.repo,self.a)['effective']['concurrency'],4)
        self.assertEqual(read(self.repo,self.b)['effective']['voice'],'default-2')
        other=BookRepository(self.root);self.addCleanup(other.engine.dispose)
        self.assertEqual(read(other,self.a)['sources']['voice'],'book')
        save(other,SaveConfig(revision=1,values={}),self.a)
        self.assertEqual(read(other,self.a)['effective']['voice'],'default-2')

    def test_invalid_retry_concurrency_unknown_key_and_conflict(self):
        for values in [{'concurrency':0},{'retries':-1},{'provider':'unknown'},{'OPENAI_API_KEY':'secret'},{'provider':'piper','voice':'unsupported'}]:
            with self.assertRaises(BookError):save(self.repo,SaveConfig(revision=0,values=values))
        save(self.repo,SaveConfig(revision=0,values={'cleanup':False}))
        with self.assertRaises(BookError):save(self.repo,SaveConfig(revision=0,values={'cleanup':True}))
        self.assertFalse(read(self.repo)['effective']['cleanup'])
