"""T03: real offline probe, config reload, secret redaction and fault flows."""
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings
from src.doctor import check_environment, read_config, inspect_runtime


class DoctorTests(unittest.TestCase):
    def check(self, provider='edge-tts', **kwargs):
        return check_environment(provider, env=kwargs.pop('env', {}), probe=lambda _: {k: True for k in ['openai','dotenv','typer','rich','tqdm','edge_tts','piper','vieneu']}, which=lambda _: '/bin/fake', **kwargs)

    def test_offline_probe_does_not_import_provider(self):
        import sys
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network')):
            result = inspect_runtime(sys.executable)
            report = check_environment('vieneu', env={}, python=sys.executable)
        self.assertIsInstance(result, dict)
        self.assertEqual(report['provider'], 'vieneu')
        self.assertNotIn('vieneu', sys.modules)

    def test_keys_redacted_even_when_configured(self):
        secret = 'SECRET_DO_NOT_RETURN_123'
        report = self.check('openai', env={'OPENAI_API_KEY': secret, 'HF_TOKEN': secret, 'OPENAI_BASE_URL': 'https://user:'+secret+'@example.org'})
        self.assertEqual(report['status'], 'checks_passed')
        self.assertNotIn(secret, json.dumps(report))
        self.assertTrue(any(c['status']=='unverified' for c in report['checks']))
        self.assertEqual(self.check('openai')['status'], 'blocked')

    def test_missing_runtime_and_tools_are_actionable(self):
        report = check_environment('piper', env={}, probe=lambda _: None, which=lambda _: None)
        for c in report['checks']:
            if c['id'] in {'runtime','ffmpeg','ffprobe'}:
                self.assertEqual(c['status'],'missing'); self.assertTrue(c['remedy'])

    def test_cli_provider_aliases(self):
        for alias, canonical in [('local','piper'),('edge','edge-tts'),('edge_tts','edge-tts'),('vieneu-tts','vieneu')]:
            self.assertEqual(self.check(alias)['provider'],canonical)

    def test_numeric_and_remote_config_validation(self):
        report = self.check('vieneu',env={'MAX_CHUNK_CHARS':'oops', 'TTS_CONCURRENCY':'0', 'VIENEU_MODE':'remote'})
        self.assertEqual(sum(c['status']=='invalid' for c in report['checks']),3)
        report = self.check('vieneu',env={'VIENEU_MODE':'remote','VIENEU_API_BASE':'http://localhost:9000/v1','VIENEU_MODEL_NAME':'sample'})
        self.assertEqual(report['status'],'checks_passed')
        self.assertEqual(next(c for c in report['checks'] if c['id']=='model_validation')['status'],'unverified')

    def test_piper_missing_files_then_fixed_without_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); env={'PIPER_MODEL_PATH':'a.onnx','PIPER_CONFIG_PATH':'a.json'}
            self.assertEqual(self.check('piper',root=root,env=env)['status'],'blocked')
            (root/'a.onnx').write_bytes(b'fixture-not-a-real-model');(root/'a.json').write_text('{}')
            report=self.check('piper',root=root,env=env)
            self.assertEqual(report['status'],'checks_passed')
            self.assertEqual(next(c for c in report['checks'] if c['id']=='model_validation')['status'],'unverified')
            (root/'a.json').write_text('bad json')
            self.assertEqual(self.check('piper',root=root,env=env)['status'],'blocked')

    def test_config_reread_and_env_precedence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{},clear=True):
            root=Path(tmp); p=root/'.env';p.write_text('TTS_CONCURRENCY=2\n')
            self.assertEqual(read_config(root)['TTS_CONCURRENCY'],'2')
            p.write_text('TTS_CONCURRENCY=4\n');self.assertEqual(read_config(root)['TTS_CONCURRENCY'],'4')
            with patch.dict('os.environ',{'TTS_CONCURRENCY':'5'}):self.assertEqual(read_config(root)['TTS_CONCURRENCY'],'5')

    def test_api_validation_normal_mode_and_no_secret(self):
        headers={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
        with TestClient(create_app(),base_url='http://127.0.0.1:8001') as client:
            self.assertEqual(client.post('/api/v1/environment/doctor',json={'provider':'bad'},headers=headers).status_code,422)
            self.assertEqual(client.post('/api/v1/environment/doctor',json={'provider':'piper','scenario':'missing_model'},headers=headers).status_code,404)
            self.assertEqual(client.post('/api/v1/environment/doctor',json={'provider':'piper','path':'/tmp'},headers=headers).status_code,422)
            self.assertEqual(client.post('/api/v1/environment/doctor',json={'provider':'piper'}).status_code,403)
            with patch.dict('os.environ',{'OPENAI_API_KEY':'SECRET_API_VALUE'}):
                r=client.post('/api/v1/environment/doctor',json={'provider':'openai'},headers=headers)
                self.assertEqual(r.status_code,200);self.assertNotIn('SECRET_API_VALUE',r.text)
            self.assertIn('DoctorReport',client.get('/openapi.json').json()['components']['schemas'])

    def test_verification_scenarios_then_real(self):
        headers={'origin':'http://127.0.0.1:8000','x-novel2voice-client':'web'}
        with TestClient(create_app(Settings(verification_enabled=True)),base_url='http://127.0.0.1:8001') as client:
            for scenario in ['missing_model','missing_dependency','real']:
                r=client.post('/api/v1/environment/doctor',json={'provider':'piper','scenario':scenario},headers=headers)
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.json()['fixture'],None if scenario=='real' else scenario)
                if scenario!='real':self.assertEqual(r.json()['status'],'blocked')
            self.assertEqual(client.post('/api/v1/environment/doctor',json={'provider':'edge-tts','scenario':'missing_model'},headers=headers).status_code,422)
