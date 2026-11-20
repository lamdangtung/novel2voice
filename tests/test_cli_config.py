import json
import tempfile
import unittest
from pathlib import Path

from src.cli_config import config_value, load_run_config


class RunConfigTests(unittest.TestCase):
    def test_example_process_config(self):
        path = Path("configs/process.example.json")
        values = load_run_config(path, "process")

        self.assertEqual(values["input_path"], "input/my_story/chapter_1.txt")
        self.assertEqual(values["translation_provider"], "deepseek")
        self.assertFalse(values["upload_youtube"])

    def test_loads_json_and_validates_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            path.write_text(json.dumps({"command": "tts", "combine": True}), encoding="utf-8")

            self.assertEqual(load_run_config(path, "tts"), {"combine": True})
            with self.assertRaisesRegex(ValueError, "không phải 'process'"):
                load_run_config(path, "process")

    def test_cli_value_including_false_overrides_config(self):
        values = {"cleanup_temp": True}
        self.assertFalse(config_value(False, values, "cleanup_temp", True))
        self.assertTrue(config_value(None, values, "cleanup_temp", False))


if __name__ == "__main__":
    unittest.main()
