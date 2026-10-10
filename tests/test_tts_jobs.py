import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.audio_merger import AudioMerger
from src.pipeline import NovelPipeline
from src.text_chunker import TextChunker
from src.tts import VieNeuTTSProvider
from src.tts_jobs import JobStore, TTSJobRunner


class FakeProvider:
    voice = 'test'

    def __init__(self, fixture):
        self.fixture = fixture
        self.calls = []
        self.failure = None

    def generate_batch(self, tasks, **kwargs):
        self.calls.append([text for text, _ in tasks])
        for index, (_, path) in enumerate(tasks):
            if self.failure and index == 1:
                raise self.failure
            shutil.copy2(self.fixture, path)
        return [path for _, path in tasks]


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
class JobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audio_temp = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.audio_temp.name) / 'fixture.mp3'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:duration=0.25', str(cls.fixture)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.audio_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / '1_vi.txt'
        self.source.write_text('Một.\n\nHai.\n\nBa.', encoding='utf-8')
        self.output = self.root / '1.mp3'
        self.provider = FakeProvider(self.fixture)
        self.runner = TTSJobRunner(self.provider, AudioMerger(), TextChunker(5),
                                   self.root / 'state', concurrency=2, retries=0)

    def test_resume_after_batch_failure(self):
        self.provider.failure = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            self.runner.run(self.source, self.output)
        self.assertEqual(self.runner.store.rows()[0]['status'], 'failed')
        self.assertEqual(len(list(self.runner.cache.glob('*.mp3'))), 1)
        self.provider.failure = None
        self.runner.run(self.source, self.output)
        self.assertEqual(self.provider.calls, [['Một.', 'Hai.'], ['Hai.', 'Ba.']])
        self.assertTrue(AudioMerger().validate_audio(self.output))
        self.assertEqual(self.runner.store.rows()[0]['status'], 'completed')
        self.assertEqual(list(self.runner.cache.glob('*.mp3')), [])
        self.runner.run(self.source, self.output)
        self.assertEqual(len(self.provider.calls), 2)

    def test_interruption_preserves_valid_chunk(self):
        self.provider.failure = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.runner.run(self.source, self.output)
        self.assertEqual(self.runner.store.rows()[0]['status'], 'interrupted')
        self.provider.failure = None
        self.runner.run(self.source, self.output)
        self.assertNotIn('Một.', self.provider.calls[-1])

    def test_only_changed_chunk_regenerated(self):
        self.runner.run(self.source, self.output, cleanup=False)
        self.provider.calls.clear()
        self.source.write_text('Một.\n\nBốn.\n\nBa.', encoding='utf-8')
        self.runner.run(self.source, self.output, cleanup=False)
        self.assertEqual(self.provider.calls, [['Bốn.']])

    def test_voice_change_invalidates_cache(self):
        self.runner.run(self.source, self.output, cleanup=False)
        self.provider.calls.clear()
        self.provider.voice = 'other'
        runner = TTSJobRunner(self.provider, AudioMerger(), TextChunker(5),
                              self.root / 'state', concurrency=2, retries=0)
        runner.run(self.source, self.output)
        self.assertEqual(sum(map(len, self.provider.calls)), 3)

    def test_corrupt_final_is_rebuilt(self):
        self.runner.run(self.source, self.output, cleanup=False)
        self.provider.calls.clear()
        self.output.write_bytes(b'broken')
        self.runner.run(self.source, self.output)
        self.assertTrue(self.runner.valid(self.output))
        self.assertEqual(self.provider.calls, [])

    def test_merge_failure_keeps_old_output_and_cache(self):
        shutil.copy2(self.fixture, self.output)
        old_bytes = self.output.read_bytes()
        with patch.object(self.runner.merger, 'merge_mp3_files', side_effect=RuntimeError('merge')):
            with self.assertRaises(RuntimeError):
                self.runner.run(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), old_bytes)
        self.assertEqual(len(list(self.runner.cache.glob('*.mp3'))), 3)

    def test_force_regenerates_all(self):
        self.runner.run(self.source, self.output, cleanup=False)
        self.provider.calls.clear()
        self.runner.run(self.source, self.output, resume=False)
        self.assertEqual(sum(map(len, self.provider.calls)), 3)

    def test_retry_only_failed_chunk(self):
        def generate(tasks, **kwargs):
            self.provider.calls.append([t for t, _ in tasks])
            shutil.copy2(self.fixture, tasks[0][1])
            if len(self.provider.calls) == 1:
                raise RuntimeError('temporary')
        self.provider.generate_batch = generate
        self.runner.retries = 1
        with patch('src.tts_jobs.time.sleep'):
            self.runner.run(self.source, self.output)
        self.assertEqual(self.provider.calls, [['Một.', 'Hai.'], ['Hai.'], ['Ba.']])

    def test_batch_continues_and_refuses_incomplete_combine(self):
        empty = self.root / '2_vi.txt'
        empty.write_text('')
        third = self.root / '3_vi.txt'
        third.write_text('Ba.')
        pipeline = NovelPipeline(tts_provider=self.provider, chunker=TextChunker(5))
        combined = self.root / 'combined.mp3'
        with patch('src.pipeline.config.OUTPUT_DIR', self.root):
            with self.assertRaises(RuntimeError):
                pipeline.tts_batch([third, empty, self.source], combine=True,
                                   output_audio=combined, state_dir=self.root / 'state', retries=0)
        self.assertFalse(combined.exists())
        self.assertTrue((self.root / '3.mp3').exists())
        self.assertTrue((self.root / 'state' / 'last_batch_report.json').exists())
        self.assertEqual(len(pipeline.last_batch_report['failed']), 1)

    def test_combine_preserves_chapter_outputs(self):
        second = self.root / '2_vi.txt'
        second.write_text('Hai.')
        pipeline = NovelPipeline(tts_provider=self.provider, chunker=TextChunker(5))
        with patch('src.pipeline.config.OUTPUT_DIR', self.root):
            outputs = pipeline.tts_batch([second, self.source], combine=True,
                         output_audio=self.root / 'combined.mp3', state_dir=self.root / 'state')
        self.assertTrue(AudioMerger().validate_audio(outputs[0]))
        self.assertTrue(self.output.exists())
        self.assertTrue((self.root / '2.mp3').exists())

    def test_valid_but_modified_cached_audio_is_regenerated(self):
        self.runner.run(self.source, self.output, cleanup=False)
        self.provider.calls.clear()
        path = next(self.runner.cache.glob('*.mp3'))
        path.write_bytes(path.read_bytes() + b'changed metadata')
        self.assertTrue(self.runner.valid(path))
        self.output.unlink()
        self.runner.run(self.source, self.output)
        self.assertEqual(sum(map(len, self.provider.calls)), 1)

    def test_interrupted_batch_reports_remaining_chapters(self):
        second = self.root / '2_vi.txt'
        second.write_text('Hai.')
        self.provider.failure = KeyboardInterrupt()
        pipeline = NovelPipeline(tts_provider=self.provider, chunker=TextChunker(5), concurrency=2)
        with patch('src.pipeline.config.OUTPUT_DIR', self.root):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.tts_batch([self.source, second], state_dir=self.root / 'state')
        self.assertEqual(pipeline.last_batch_report['interrupted'], [str(self.source)])
        self.assertEqual(pipeline.last_batch_report['unprocessed'], [str(second)])

    def test_vieneu_save_publishes_only_complete_audio(self):
        import wave
        from unittest.mock import Mock
        provider = VieNeuTTSProvider()
        provider._tts = Mock()
        def save(audio, filename):
            with wave.open(filename, 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(24000)
                stream.writeframes(b'\x00\x00' * 6000)
        provider._tts.save.side_effect = save
        provider._save_with_format(None, self.output)
        self.assertTrue(self.runner.valid(self.output))
        before = self.output.read_bytes()
        with patch('subprocess.run', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                provider._save_with_format(None, self.output)
        self.assertEqual(before, self.output.read_bytes())
        self.assertFalse(list(self.root.glob('*.wav')))
        self.assertFalse(list(self.root.glob('.*.writing.mp3')))

    def test_completed_combine_is_reused(self):
        self.runner.run(self.source, self.output)
        target = self.root / 'combined.mp3'
        self.runner.combine([self.output], target)
        with patch.object(self.runner.merger, 'merge_mp3_files', side_effect=AssertionError('should skip')):
            self.runner.combine([self.output], target)

    def test_same_state_directory_is_locked(self):
        with self.runner.store.lock():
            with self.assertRaises(RuntimeError):
                with JobStore(self.root / 'state').lock():
                    pass


class UnitTests(unittest.TestCase):
    def test_long_token_is_bounded(self):
        self.assertEqual([len(c) for c in TextChunker(10).chunk_text('a' * 25)], [10, 10, 5])
        with self.assertRaises(ValueError):
            TextChunker(0)

    def test_vieneu_rejects_missing_outputs(self):
        from unittest.mock import Mock
        provider = VieNeuTTSProvider()
        provider._tts = Mock()
        provider._tts.infer_batch.return_value = []
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, '0 audio cho 1'):
                provider.generate_batch([('Xin chào', Path(directory) / 'a.mp3')], show_progress=False)


class CLITests(unittest.TestCase):
    def test_options_validate_before_work(self):
        from typer.testing import CliRunner
        from src.main import app
        runner = CliRunner()
        self.assertEqual(runner.invoke(app, ['tts', 'input/', '-j', '0']).exit_code, 2)
        self.assertEqual(runner.invoke(app, ['tts', 'input/', '--retries', '-1']).exit_code, 2)

    def test_empty_file_records_failure_and_cli_exits_nonzero(self):
        from typer.testing import CliRunner
        from src.main import app
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'empty.txt'
            source.write_text('')
            result = CliRunner().invoke(app, ['tts', str(source), '--state-dir', str(root / 'state'),
                                             '-o', str(root / 'test.mp3')])
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(JobStore(root / 'state').rows()[0]['status'], 'failed')

    def test_status_does_not_create_database(self):
        from typer.testing import CliRunner
        from src.main import app
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state'
            result = CliRunner().invoke(app, ['status', '--state-dir', str(state)])
            self.assertEqual(result.exit_code, 0)
            self.assertFalse(state.exists())


if __name__ == '__main__':
    unittest.main()
