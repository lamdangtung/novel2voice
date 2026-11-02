import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.glossary import Glossary
from src.glossary_manager import GlossaryManager, ModelGlossaryExtractor
from src.translator import NovelTranslator


def candidate(en='John', vi='Giôn'):
    return {'en': en, 'vi': vi, 'category': 'person'}


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'glossary.csv'
        self.path.write_text('en,vi\nAlice,A-li-xơ\n', encoding='utf-8')
        self.glossary = Glossary(self.path)
        self.manager = GlossaryManager(self.glossary)

    def test_thresholds_and_replay_deduplication(self):
        first = [('John met John.', 'Giôn gặp Giôn.')]
        self.assertEqual(self.manager.update(first, [candidate()]), [])
        self.assertEqual(self.manager.update(first, [candidate()]), [])
        self.assertNotIn('John', self.glossary.entries)
        self.assertEqual(self.manager.update([('John left.', 'Giôn đi.')], [candidate()]), ['John'])
        self.assertEqual(Glossary(self.path).entries['John'], 'Giôn')

    def test_normalization_and_word_boundaries(self):
        self.manager.update([('JOHN met John.', 'Giôn gặp Giôn.')], [candidate(' JOHN ')])
        self.manager.update([('Johnny left.', 'Giôn đi.')], [candidate()])
        self.assertNotIn('John', self.glossary.entries)
        self.manager.update([('john left.', 'Giôn đi.')], [candidate()])
        self.assertEqual(self.glossary.entries['JOHN'], 'Giôn')

    def test_manual_translation_preserved_and_conflict_recorded(self):
        self.manager.update([('Alice Alice Alice.', 'An An An.')], [candidate('Alice', 'An')])
        self.assertEqual(self.glossary.entries['Alice'], 'A-li-xơ')
        with sqlite3.connect(self.manager.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM conflicts').fetchone()[0], 1)

    def test_unverified_terms_and_categories_are_rejected(self):
        self.manager.update([('John met John.', 'Giôn gặp Giôn.')],
                            [candidate('Fake', 'Giả'), candidate('John', 'Không có'),
                             dict(candidate(), category='common')])
        with sqlite3.connect(self.manager.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM candidates').fetchone()[0], 0)

    def test_auto_cap_and_prompt_selection(self):
        manager = GlossaryManager(self.glossary, min_occurrences=1, min_chunks=1,
                                  max_auto_entries=1, max_prompt_entries=1)
        manager.update([('John met Bob.', 'Giôn gặp Bốp.')], [candidate(), candidate('Bob', 'Bốp')])
        self.assertEqual(len(self.glossary.entries), 2)  # one manual plus one automatic
        self.assertEqual(manager.select_entries(['Alice Alice Bob.']), {'Alice': 'A-li-xơ'})

    def test_ambiguous_candidate_is_not_promoted(self):
        self.manager.update([('John John John.', 'Giôn Giôn An.')], [candidate(), candidate(vi='An')])
        self.manager.update([('John left.', 'Giôn đi.')], [candidate()])
        self.assertNotIn('John', self.glossary.entries)

    def test_persistence_and_isolation(self):
        self.manager.update([('John John.', 'Giôn Giôn.')], [candidate()])
        manager = GlossaryManager(Glossary(self.path))
        manager.update([('John left.', 'Giôn đi.')], [candidate()])
        self.assertIn('John', manager.glossary.entries)
        other = GlossaryManager(Glossary(Path(self.temp.name) / 'other.csv'))
        other.update([('John left.', 'Giôn đi.')], [candidate()])
        self.assertNotIn('John', other.glossary.entries)

    def test_malformed_csv_is_not_replaced(self):
        self.path.write_text('en,vi\ninvalid\n')
        with self.assertRaises(ValueError):
            self.manager.update([], [])
        self.assertEqual(self.path.read_text(), 'en,vi\ninvalid\n')

    def test_extractor_json_and_client_cleanup(self):
        provider = Mock()
        provider.generate.return_value = '```json\n[{"en":"John","vi":"Giôn","category":"person"}]\n```'
        self.assertEqual(ModelGlossaryExtractor(lambda: provider).extract([('John', 'Giôn')]), [candidate()])
        provider.close.assert_called_once()
        provider.generate.return_value = 'bad JSON'
        with self.assertRaises(ValueError):
            ModelGlossaryExtractor(lambda: provider).extract([])
        self.assertEqual(provider.close.call_count, 2)

    def test_integration_updates_before_next_conversation(self):
        provider = Mock()
        provider.conversation_limit = 2
        provider.generate.side_effect = ['Giôn Giôn.', 'Giôn về.', 'Giôn đi.']
        extractor = Mock()
        extractor.extract.return_value = [candidate()]
        translator = NovelTranslator(provider=provider, glossary=self.glossary,
                                     glossary_manager=self.manager, glossary_extractor=extractor)
        result = translator.translate_text('John John.\n\nJohn home.\n\nJohn left.', max_chunk_chars=10)
        self.assertEqual(result, 'Giôn Giôn.\n\nGiôn về.\n\nGiôn đi.')
        self.assertEqual(extractor.extract.call_count, 2)
        prompts = [c.kwargs['system_prompt'] for c in provider.generate.call_args_list]
        self.assertNotIn('"John"', prompts[0])
        self.assertEqual(prompts[0], prompts[1])
        self.assertIn('"John" -> "Giôn"', prompts[2])

    def test_extraction_failure_keeps_translation(self):
        provider = Mock()
        provider.conversation_limit = 1
        provider.generate.return_value = 'Giôn.'
        extractor = Mock()
        extractor.extract.side_effect = ValueError('bad JSON')
        translator = NovelTranslator(provider=provider, glossary=self.glossary,
                                     glossary_manager=self.manager, glossary_extractor=extractor)
        self.assertEqual(translator.translate_text('John.'), 'Giôn.')
        self.assertEqual(self.path.read_text(), 'en,vi\nAlice,A-li-xơ\n')

    def test_candidate_storage_is_bounded(self):
        manager = GlossaryManager(self.glossary, max_candidates=1)
        manager.update([('John met Bob.', 'Giôn gặp Bốp.')], [candidate(), candidate('Bob', 'Bốp')])
        with sqlite3.connect(manager.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM candidates').fetchone()[0], 1)

    def test_failed_csv_write_rolls_back_promotion(self):
        from unittest.mock import patch
        self.manager.update([('John John.', 'Giôn Giôn.')], [candidate()])
        before = self.path.read_bytes()
        with patch.object(self.manager, '_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager.update([('John left.', 'Giôn đi.')], [candidate()])
        self.assertEqual(self.path.read_bytes(), before)
        with sqlite3.connect(self.manager.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM promoted').fetchone()[0], 0)

    def test_extraction_failure_retains_source_evidence(self):
        provider = Mock()
        provider.conversation_limit = 1
        provider.generate.return_value = 'Giôn.'
        extractor = Mock()
        extractor.extract.side_effect = ValueError('bad JSON')
        translator = NovelTranslator(provider=provider, glossary=self.glossary,
                                     glossary_manager=self.manager, glossary_extractor=extractor)
        translator.translate_text('John.')
        with sqlite3.connect(self.manager.db_path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0], 1)
