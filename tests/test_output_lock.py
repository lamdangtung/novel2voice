"""OS-level destination reservation is shared by independent CLI/web processes."""
import subprocess,sys,tempfile,unittest
from pathlib import Path
from src.tts_jobs import output_lock

class OutputLockTests(unittest.TestCase):
    def test_other_process_conflict_release_and_other_book(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'book-a'/'1.mp3'
            command=[sys.executable,'-c','from pathlib import Path; from src.tts_jobs import output_lock; import sys\nwith output_lock(Path(sys.argv[1])): pass',str(output)]
            with output_lock(output):
                blocked=subprocess.run(command,capture_output=True,text=True)
                self.assertNotEqual(blocked.returncode,0);self.assertIn('đang ghi output',blocked.stderr)
                with output_lock(Path(tmp)/'book-b'/'1.mp3'):pass
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
