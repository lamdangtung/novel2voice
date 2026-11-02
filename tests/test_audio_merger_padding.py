"""Regression: successful MP3 stream copy can accumulate padding over 24 chunks."""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
from src.audio_merger import AudioMerger


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Needs FFmpeg')
class PaddingTests(unittest.TestCase):
    def test_many_short_mp3s_reencode_when_copy_duration_drifts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'tone.mp3';output=Path(tmp)/'joined.mp3'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.4','-ar','24000','-c:a','libmp3lame','-b:a','64k',str(source)],check=True)
            original=source.read_bytes();merger=AudioMerger();expected=24*merger.get_duration(source)
            merger.merge_mp3_files([source]*24,output)
            self.assertTrue(merger.validate_audio(output));self.assertLess(abs(merger.get_duration(output)-expected),.15)
            self.assertEqual(source.read_bytes(),original)
