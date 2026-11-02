import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner
from src.main import app
from src.pipeline import NovelPipeline
from src.video.planner import plan_videos


class VideoPlannerTests(unittest.TestCase):
    def test_default_is_one_chapter_and_natural_order(self):
        paths = [Path(f'chapter_{i}.mp3') for i in (10, 2, 1)]
        episodes = plan_videos(paths)
        self.assertEqual([e.chapter_audio[0].name for e in episodes],
                         ['chapter_1.mp3', 'chapter_2.mp3', 'chapter_10.mp3'])
        self.assertEqual([e.number for e in episodes], [1, 2, 3])

    def test_grouping_keeps_partial_final_video(self):
        episodes = plan_videos([Path(f'{i}.mp3') for i in range(1, 6)], chapters_per_video=2)
        self.assertEqual([len(e.chapter_audio) for e in episodes], [2, 2, 1])
        self.assertEqual(episodes[1].chapter_audio, (Path('3.mp3'), Path('4.mp3')))

    def test_config_and_override(self):
        with patch('src.config.VIDEO_CHAPTERS_PER_VIDEO', 2):
            pipeline = NovelPipeline()
            paths = [Path('1.mp3'), Path('2.mp3')]
            self.assertEqual(len(pipeline.plan_videos(paths)), 1)
            self.assertEqual(len(pipeline.plan_videos(paths, chapters_per_video=1)), 2)

    def test_invalid_counts_and_duplicate_chapters(self):
        for count in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                plan_videos([], chapters_per_video=count)
        with self.assertRaises(ValueError):
            plan_videos([Path('1.mp3'), Path('./1.mp3')])
        self.assertEqual(plan_videos([]), [])

    def test_cli_does_not_modify_chapter_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{i}.mp3' for i in range(1, 4)]
            for path in paths:
                path.write_bytes(b'chapter-audio-placeholder')
            result = CliRunner().invoke(app, ['plan-videos', *map(str, paths), '--chapters-per-video', '2'])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(all(path.read_bytes() == b'chapter-audio-placeholder' for path in paths))
            self.assertEqual(len(list(Path(directory).iterdir())), 3)
