import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from typer.testing import CliRunner
from src.main import app
from src.pipeline import NovelPipeline
from src.video.base import VideoSpec
from src.video.ffmpeg import FFmpegVideoRenderer


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class RendererTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.background = self.root / 'background.jpg'
        Image.new('RGB', (640, 360), (30, 50, 80)).save(self.background)
        self.audio = []
        for index, rate in enumerate((24000, 44100), 1):
            path = self.root / f'chapter_{index}.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            f'sine=frequency={400 * index}:duration=0.5:sample_rate={rate}', str(path)], check=True)
            self.audio.append(path)
        self.renderer = FFmpegVideoRenderer(state_dir=self.root / 'state')
        self.spec = VideoSpec(tuple(self.audio), self.background, self.root / 'out.mp4',
                              'Truyện thử — Chương 1 và 2', 320, 180, 10)

    def test_render_real_media_and_resume(self):
        output = self.renderer.render(self.spec)
        self.assertTrue(output.is_file())
        metadata = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(len(metadata['chapters']), 2)
        self.assertGreater(metadata['chapters'][1]['start_seconds'], 0)
        self.assertGreater(metadata['duration_seconds'], 0.9)
        with Image.open(output.with_suffix('.jpg')) as image:
            self.assertEqual(image.size, (320, 180))
        original = output.stat().st_mtime_ns
        with patch.object(self.renderer, '_run', side_effect=AssertionError('unexpected render')):
            self.renderer.render(self.spec)
        self.assertEqual(output.stat().st_mtime_ns, original)
        # A damaged output is rebuilt even when the checkpoint says completed.
        output.write_bytes(b'corrupt')
        self.renderer.render(self.spec)
        self.assertGreater(output.stat().st_size, 1000)

    def test_changed_title_and_thumbnail_invalidate_cache(self):
        self.renderer.render(self.spec)
        changed = replace(self.spec, title='Tiêu đề mới')
        with patch.object(self.renderer, '_run', wraps=self.renderer._run) as run:
            self.renderer.render(changed)
            run.assert_called_once()
        changed.output.with_suffix('.jpg').unlink()
        with patch.object(self.renderer, '_run', wraps=self.renderer._run) as run:
            self.renderer.render(changed)
            run.assert_called_once()

    def test_failure_and_interruption_preserve_old_video(self):
        self.renderer.render(self.spec)
        before = self.spec.output.read_bytes()
        for error, status in ((RuntimeError('encoding failed'), 'failed'), (KeyboardInterrupt(), 'interrupted')):
            with patch.object(self.renderer, '_run', side_effect=error):
                with self.assertRaises(type(error)):
                    self.renderer.render(self.spec, resume=False)
            self.assertEqual(self.spec.output.read_bytes(), before)
            self.assertEqual(list(self.root.glob('.render-*')), [])
            with sqlite3.connect(self.root / 'state' / 'videos.sqlite3') as db:
                self.assertEqual(db.execute('SELECT status FROM video_jobs').fetchone()[0], status)

    def test_validation_and_input_collision(self):
        for spec in (replace(self.spec, width=321), replace(self.spec, chapter_audio=()),
                     replace(self.spec, output=self.root / 'out.avi'),
                     replace(self.spec, background=self.root / 'missing.jpg'),
                     replace(self.spec, output=self.root / 'background.mp4')):
            with self.assertRaises(ValueError):
                self.renderer.render(spec)
        self.assertTrue(self.background.is_file())

    def test_pipeline_groups_and_preserves_chapters(self):
        before = [p.read_bytes() for p in self.audio]
        with patch('src.config.VIDEO_WIDTH', 320), patch('src.config.VIDEO_HEIGHT', 180), \
             patch('src.config.VIDEO_FPS', 10):
            outputs = NovelPipeline().render_videos(self.audio, self.background,
                output_dir=self.root / 'videos', chapters_per_video=2, renderer=self.renderer)
        self.assertEqual(len(outputs), 1)
        self.assertEqual([p.read_bytes() for p in self.audio], before)

    def test_render_cli_and_process_integration(self):
        with patch('src.config.VIDEO_WIDTH', 320), patch('src.config.VIDEO_HEIGHT', 180), \
             patch('src.config.VIDEO_FPS', 10), patch('src.config.OUTPUT_DIR', self.root):
            result = CliRunner().invoke(app, ['render-video', str(self.audio[0]),
                '--background', str(self.background), '--output-dir', str(self.root / 'cli')])
            self.assertEqual(result.exit_code, 0, result.output)
        source = self.root / 'source.txt'
        source.write_text('A test chapter')
        with patch('src.main.NovelTranslator'), patch('src.main.get_tts_provider'), \
             patch('src.main.NovelPipeline') as pipeline:
            pipeline.return_value.process_file.return_value = (source, self.audio[0])
            result = CliRunner().invoke(app, ['process', str(source), '--background', str(self.background)])
            self.assertEqual(result.exit_code, 0, result.output)
            pipeline.return_value.render_videos.assert_called_once()
