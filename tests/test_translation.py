import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from typer.testing import CliRunner
from src.main import app
from src.translator import NovelTranslator
from src.glossary import Glossary
from src.translation_providers.deepseek import DeepSeekTranslationProvider
from src.translation_providers.factory import get_translation_provider


class TranslationTests(unittest.TestCase):
    def setUp(self):
        from contextlib import nullcontext
        pacing = patch('src.translation_providers.deepseek.get_deepseek_scheduler')
        scheduler = pacing.start().return_value
        scheduler.slot.side_effect = nullcontext
        self.addCleanup(pacing.stop)
        setting = patch('src.config.GLOSSARY_AUTO_UPDATE', False)
        setting.start()
        self.addCleanup(setting.stop)

    def test_direct_deepseek_prompt_and_model(self):
        client = Mock()
        client.chat.return_value = SimpleNamespace(conversation_id="chat:1", text="```\nXin chào\n```", reasoning="private")
        glossary = Glossary()
        glossary.entries = {"John": "Giôn"}
        provider = DeepSeekTranslationProvider(model="deepseek-expert", client=client)
        translator = NovelTranslator(provider=provider, glossary=glossary)
        self.assertEqual(translator.translate_text("Hello John"), "Xin chào")
        args, kwargs = client.chat.call_args
        self.assertIn('"John" -> "Giôn"', args[0])
        self.assertIn("Hello John", args[0])
        self.assertEqual(kwargs, {"model": "expert", "thinking": False, "search": False})
        translator.close()
        client.close.assert_not_called()  # injected client belongs to the caller

    def test_chunks_share_conversation_and_are_ordered(self):
        client = Mock()
        client.chat.side_effect = [SimpleNamespace(conversation_id="chat:1", text="Một"), SimpleNamespace(conversation_id="chat:1", text="Hai")]
        translator = NovelTranslator(provider=DeepSeekTranslationProvider(client=client))
        self.assertEqual(translator.translate_text("Hello.\n\nWorld.", max_chunk_chars=6), "Một\n\nHai")
        self.assertEqual(client.chat.call_count, 2)
        first, second = client.chat.call_args_list
        self.assertEqual(first.kwargs['model'], 'default')
        self.assertEqual(second.kwargs['conversation_id'], 'chat:1')
        self.assertNotIn('model', second.kwargs)
        self.assertNotIn('Bắt buộc tuân thủ', second.args[0])
        self.assertNotIn('System:', second.args[0])

    def test_native_client_is_lazy_and_closed(self):
        with patch('src.translation_providers.deepseek._load_client_class') as load:
            provider = get_translation_provider('deepseek')
            load.assert_not_called()
            load.return_value.return_value.chat.return_value = SimpleNamespace(conversation_id="chat:1", text="Xin chào")
            provider.generate(system_prompt="Translate", user_prompt="Hello")
            load.return_value.assert_called_once_with(allow_interactive=False)
            provider.close()
            load.return_value.return_value.close.assert_called_once()

    def test_login_error_is_actionable(self):
        LoginRequired = type("LoginRequired", (RuntimeError,), {})
        with patch('src.translation_providers.deepseek._load_client_class') as load:
            load.return_value.side_effect = LoginRequired()
            with self.assertRaisesRegex(RuntimeError, 'python -m deepseek.auth'):
                DeepSeekTranslationProvider().generate(system_prompt="Translate", user_prompt="Hello")

    def test_openai_request_is_preserved(self):
        with patch('src.translation_providers.openai.OpenAI') as sdk:
            sdk.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Xin chào"))])
            provider = get_translation_provider('openai', api_key='test', model='test-model')
            self.assertEqual(provider.generate(system_prompt='S', user_prompt='U'), 'Xin chào')
            sdk.return_value.chat.completions.create.assert_called_once_with(
                model='test-model', messages=[{'role': 'system', 'content': 'S'},
                                             {'role': 'user', 'content': 'U'}], temperature=0.3)
            provider.close()

    def test_empty_reply_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'en.txt'
            output = Path(directory) / 'vi.txt'
            source.write_text('Hello')
            provider = Mock()
            provider.generate.return_value = ''
            with self.assertRaises(ValueError):
                NovelTranslator(provider=provider).translate_file(source, output)
            self.assertFalse(output.exists())

    def test_cli_file_to_translation_without_openai_or_tts(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'en.txt'
            output = Path(directory) / 'vi.txt'
            source.write_text('Hello')
            with patch('src.translation_providers.deepseek._load_client_class') as load, \
                 patch('src.pipeline.get_tts_provider', side_effect=AssertionError('TTS initialized')), \
                 patch('src.config.OPENAI_API_KEY', ''):
                load.return_value.return_value.chat.return_value = SimpleNamespace(conversation_id="chat:1", text='Xin chào')
                result = CliRunner().invoke(app, ['translate', str(source), '--translation-provider',
                                                 'deepseek', '-o', str(output)])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(output.read_text(), 'Xin chào')
                load.return_value.return_value.close.assert_called_once()

    def test_invalid_provider_and_model(self):
        with self.assertRaises(ValueError):
            get_translation_provider('unknown')
        with self.assertRaises(ValueError):
            get_translation_provider('deepseek', model='gpt-4o')

    def test_limit_rotates_conversation_and_resends_glossary(self):
        client = Mock()
        client.chat.side_effect = [SimpleNamespace(text='VI', conversation_id=f'chat:{i}')
                                   for i in range(1, 6)]
        provider = DeepSeekTranslationProvider(client=client, max_chunks_per_conversation=2)
        for _ in range(5):
            provider.generate(system_prompt='Glossary: John -> Giôn', user_prompt='Translate this')
        calls = client.chat.call_args_list
        for index in (0, 2, 4):
            self.assertIn('Glossary:', calls[index].args[0])
            self.assertIn('model', calls[index].kwargs)
            self.assertNotIn('conversation_id', calls[index].kwargs)
        for index in (1, 3):
            self.assertEqual(calls[index].args[0], 'Translate this')
            self.assertEqual(calls[index].kwargs['conversation_id'], f'chat:{index}')
            self.assertNotIn('model', calls[index].kwargs)

    def test_documents_start_fresh(self):
        client = Mock()
        client.chat.return_value = SimpleNamespace(text='VI', conversation_id='chat:1')
        translator = NovelTranslator(provider=DeepSeekTranslationProvider(client=client))
        translator.translate_text('Chapter one')
        translator.translate_text('Chapter two')
        for call in client.chat.call_args_list:
            self.assertIn('model', call.kwargs)
            self.assertNotIn('conversation_id', call.kwargs)

    def test_failure_does_not_advance_conversation(self):
        client = Mock()
        client.chat.side_effect = [SimpleNamespace(text='VI', conversation_id='chat:1'),
                                   RuntimeError('network'),
                                   SimpleNamespace(text='VI', conversation_id='chat:2')]
        provider = DeepSeekTranslationProvider(client=client)
        provider.generate(system_prompt='S', user_prompt='first')
        with self.assertRaises(RuntimeError):
            provider.generate(system_prompt='S', user_prompt='second')
        provider.generate(system_prompt='S', user_prompt='second')
        self.assertEqual(client.chat.call_args.kwargs['conversation_id'], 'chat:1')
        self.assertEqual(provider._chunk_count, 2)

    def test_missing_conversation_id_is_an_error(self):
        client = Mock()
        client.chat.return_value = SimpleNamespace(text='VI')
        with self.assertRaisesRegex(ValueError, 'conversation_id'):
            DeepSeekTranslationProvider(client=client).generate(system_prompt='S', user_prompt='U')

    def test_invalid_conversation_limit(self):
        for limit in (0, -1):
            with self.assertRaises(ValueError):
                DeepSeekTranslationProvider(max_chunks_per_conversation=limit)

    def test_factory_passes_configured_limit(self):
        with patch('src.config.DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION', 3):
            self.assertEqual(get_translation_provider('deepseek').max_chunks_per_conversation, 3)
