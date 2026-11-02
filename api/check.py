"""Run offline API regression suite without installing model SDKs in api/.venv."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent.parent
SDK_TESTS={'test_tts_jobs.py','test_audio_merger_padding.py','test_output_lock.py'}
def main():
    suite=unittest.TestSuite(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=p.name) for p in sorted((ROOT/'tests').glob('test_*.py')) if p.name not in SDK_TESTS)
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
