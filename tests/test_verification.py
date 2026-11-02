"""T02 integration tests: real files/FFmpeg, isolated temporary workspaces, no model/API."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.main import create_app
from api.settings import Settings
from api.verification.workspace import audio_info
from api.verification import FakeTTSProvider, FaultPlan, InjectedFailure, WorkspaceError, WorkspaceManager, self_check


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.manager = WorkspaceManager(self.base / "workspaces")

    def create(self, name="demo"):
        return self.manager.create(name)

    def test_fixed_fixture_cases_and_two_books(self):
        result = self.create()
        self.assertEqual([book["id"] for book in result["manifest"]["books"]], ["A", "B"])
        files = result["manifest"]["files"]
        self.assertEqual(len(files), 18)
        cases = {item["case"] for item in files}
        self.assertTrue({"empty", "invalid_utf8", "changed_content", "duplicate_number", "ambiguous_audio_mapping", "corrupt_audio"} <= cases)
        workspace = Path(result["path"])
        self.assertTrue((workspace / "fixtures/books/A/ep2/10_vi.txt").exists())
        self.assertTrue((workspace / "fixtures/books/B/ep2/10_vi.txt").exists())
        self.assertTrue(audio_info(workspace / "fixtures/books/A/audio/1.mp3")["valid"])
        self.assertFalse(audio_info(workspace / "fixtures/edge-cases/corrupt-audio/2.mp3")["valid"])
        with self.assertRaises(UnicodeDecodeError):
            (workspace / "fixtures/edge-cases/invalid-encoding/4_vi.txt").read_text(encoding="utf-8")

    def test_repeated_create_keeps_results(self):
        self.create()
        first = self_check(self.manager, "demo")
        second = self.create()
        self.assertEqual(second["latest_report"], first)

    def test_reset_and_replay_same_logical_result(self):
        self.create()
        first = self_check(self.manager, "demo")
        self.assertEqual((first["status"], first["tts_calls"], first["translator_calls"]), ("passed", 3, 1))
        self.assertTrue(all(item["valid"] and item["duration_seconds"] > 0 for item in first["outputs"]))
        self.manager.reset("demo", "RESET demo")
        self.assertIsNone(self.manager.describe("demo")["latest_report"])
        second = self_check(self.manager, "demo")
        self.assertEqual(first, second)
        self.assertEqual(second["run_id"], "run-0001")

    def test_reset_rejects_production_or_arbitrary_paths(self):
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("do not delete")
        for destination in ("input", "output", "models", "../outside", str(outside), str(Path.cwd() / "output")):
            with self.subTest(destination=destination), self.assertRaises(WorkspaceError):
                self.manager.reset(destination, "RESET outside")
        self.assertEqual(sentinel.read_text(), "do not delete")
        self.assertFalse(self.manager.root.exists())

    def test_reset_requires_confirmation_and_owned_marker(self):
        self.create()
        with self.assertRaises(WorkspaceError) as error:
            self.manager.reset("demo", "yes")
        self.assertEqual(error.exception.code, "CONFIRMATION_REQUIRED")
        marker = self.manager.root / "demo/.novel2voice-verification.json"
        marker.write_text('{}')
        with self.assertRaises(WorkspaceError):
            self.manager.reset("demo", "RESET demo")
        self.assertTrue(marker.exists())

    def test_symlink_and_hardlink_are_rejected_without_touching_target(self):
        self.create()
        sentinel = self.base / "keep.txt"
        sentinel.write_text("do not change")
        link = self.manager.root / "demo/foreign.txt"
        link.symlink_to(sentinel)
        with self.assertRaises(WorkspaceError):
            self.manager.reset("demo", "RESET demo")
        link.unlink()
        os.link(sentinel, link)
        with self.assertRaises(WorkspaceError):
            self.manager.reset("demo", "RESET demo")
        self.assertEqual(sentinel.read_text(), "do not change")

    def test_symlink_workspace_root_is_rejected(self):
        real = self.base / "real"
        real.mkdir()
        link = self.base / "redirect"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(WorkspaceError):
            WorkspaceManager(link / "workspaces").create("demo")
        self.assertEqual(list(real.iterdir()), [])

    def test_failure_by_chapter_preserves_completed_outputs_and_logs(self):
        self.create()
        report = self_check(self.manager, "demo", fail_provider="tts", fail_chapter="A/2")
        self.assertEqual(report["status"], "failed")
        self.assertEqual([item["chapter_id"] for item in report["outputs"]], ["A/1", "A/en/1"])
        self.assertEqual(report["tts_calls"], 3)
        self.assertEqual([c["chapter_id"] for c in report["calls"] if c["status"] == "failed"], ["A/2"])
        rerun = self_check(self.manager, "demo")
        self.assertEqual(rerun["status"], "passed")
        self.assertEqual(rerun["run_id"], "run-0002")

    def test_translator_failure_is_explicit(self):
        self.create()
        report = self_check(self.manager, "demo", fail_provider="translator")
        self.assertEqual(report["status"], "failed")
        self.assertIsNone(report["translation"])
        self.assertEqual((report["tts_calls"], report["translator_calls"]), (2, 1))
        self.assertEqual(report["errors"][0]["stage"], "translator")

    def test_batch_failure_on_second_chunk(self):
        value = self.create()
        workspace = Path(value["path"])
        output = workspace / "runs/batch-test"
        provider = FakeTTSProvider(workspace / "fixtures/tone.mp3", output, output / "calls.jsonl",
                                   FaultPlan(fail_on_calls=(2,)), chapter_id="A/1")
        with self.assertRaises(InjectedFailure):
            provider.generate_batch([("Một", output / "1.mp3"), ("Hai", output / "2.mp3"), ("Ba", output / "3.mp3")])
        self.assertTrue((output / "1.mp3").is_file())
        self.assertFalse((output / "2.mp3").exists())
        calls = [json.loads(line) for line in (output / "calls.jsonl").read_text().splitlines()]
        self.assertEqual(calls[-1]["chunk_index"], 2)
        self.assertEqual(calls[-1]["status"], "failed")

    def test_delay_and_no_network_dependency(self):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
                patch("api.verification.providers.time.sleep") as delay:
            self.create()
            report = self_check(self.manager, "demo", delay_ms=250)
        self.assertEqual(report["status"], "passed")
        self.assertEqual([call.args[0] for call in delay.call_args_list], [.25] * 4)

    def test_reset_one_workspace_keeps_other(self):
        self.create("alpha")
        self.create("beta")
        report = self_check(self.manager, "beta")
        self.manager.reset("alpha", "RESET alpha")
        self.assertEqual(self.manager.describe("beta")["latest_report"], report)

    def test_modified_fixture_requires_reset(self):
        self.create()
        path = self.manager.root / "demo/fixtures/books/A/1_vi.txt"
        path.write_text("changed")
        with self.assertRaises(WorkspaceError) as error:
            self_check(self.manager, "demo")
        self.assertEqual(error.exception.code, "FIXTURE_CHANGED")
        self.assertEqual(list((self.manager.root / "demo/runs").iterdir()), [])
        self.manager.reset("demo", "RESET demo")
        self.assertEqual(self_check(self.manager, "demo")["status"], "passed")

    def test_workspace_lock_prevents_reset_during_work(self):
        self.create()
        with self.manager.lock("demo"):
            with self.assertRaises(WorkspaceError) as error:
                self.manager.reset("demo", "RESET demo")
        self.assertEqual(error.exception.code, "WORKSPACE_BUSY")

    def test_fake_output_cannot_escape_its_run(self):
        value = self.create()
        path = Path(value["path"])
        provider = FakeTTSProvider(path / "fixtures/tone.mp3", path / "runs/check", path / "runs/check/calls.jsonl")
        outside = self.base / "outside.mp3"
        with self.assertRaises(ValueError):
            provider.generate_speech("Test", outside)
        self.assertFalse(outside.exists())

    def test_default_mode_does_not_expose_verification_routes(self):
        with TestClient(create_app(), base_url="http://127.0.0.1:8001") as client:
            self.assertFalse(client.get("/api/v1/health").json()["verification_mode"])
            self.assertEqual(client.get("/api/v1/verification/workspaces").status_code, 404)
            self.assertNotIn("/api/v1/verification/workspaces", client.get("/openapi.json").json()["paths"])
        self.assertFalse(self.manager.root.exists())

    def test_http_create_check_audio_range_reset_and_reload(self):
        with patch("api.verification.routes.WorkspaceManager", return_value=self.manager):
            app = create_app(Settings(verification_enabled=True))
        headers = {"origin": "http://127.0.0.1:8000", "x-novel2voice-client": "web"}
        url = "/api/v1/verification/workspaces"
        with TestClient(app, base_url="http://127.0.0.1:8001") as client:
            self.assertEqual(client.get(url).json()["workspaces"], [])
            self.assertFalse(self.manager.root.exists())
            self.assertEqual(client.post(url, json={"name": "demo"}).status_code, 403)
            self.assertEqual(client.post(url, json={"name": "../output"}, headers=headers).status_code, 422)
            self.assertEqual(client.post(url, json={"name": "demo"}, headers=headers).status_code, 201)
            report = client.post(url + "/demo/self-check", json={}, headers=headers).json()
            self.assertEqual(report["status"], "passed")
            audio = client.get(url + "/demo/runs/run-0001/audio/A-1.mp3", headers={"Range": "bytes=0-99"})
            self.assertEqual(audio.status_code, 206)
            self.assertEqual(len(audio.content), 100)
            download = client.get(url + "/demo/runs/run-0001/report")
            self.assertEqual(download.json(), report)
            self.assertIn("attachment", download.headers["content-disposition"])
            self.assertEqual(client.post(url + "/demo/reset", json={"confirmation": "wrong"}, headers=headers).status_code, 400)
            self.assertEqual(client.get(url).json()["workspaces"][0]["latest_report"], report)
            self.assertEqual(client.post(url + "/demo/reset", json={"confirmation": "RESET demo"}, headers=headers).status_code, 200)
            self.assertIsNone(client.get(url).json()["workspaces"][0]["latest_report"])
        # A new API instance can see the same persisted workspace, without recreating fixtures.
        with TestClient(app, base_url="http://127.0.0.1:8001") as client:
            self.assertEqual(client.get(url).json()["workspaces"][0]["name"], "demo")


if __name__ == "__main__":
    unittest.main()
