"""Repeatable self-check service shared by CLI and verification-only HTTP routes."""
import hashlib
import json
import re
from pathlib import Path

from api.verification.providers import FakeTTSProvider, FakeTranslator, FaultPlan, InjectedFailure
from api.verification.workspace import WorkspaceError, WorkspaceManager, atomic_json, audio_info, require_tools


def self_check(manager: WorkspaceManager, name, *, fail_provider="none", fail_on_call=None,
               fail_chapter="", delay_ms=0):
    fail_on_call = fail_on_call if fail_on_call is not None else (1 if fail_provider == "translator" else 2)
    if fail_chapter not in {"", "A/1", "A/2", "A/en/1"}:
        raise WorkspaceError("Chương gây lỗi phải là A/1, A/2 hoặc A/en/1.", "INVALID_FAULT_PLAN")
    if fail_provider == "translator" and (fail_chapter not in {"", "A/en/1"} or (not fail_chapter and fail_on_call != 1)):
        raise WorkspaceError("Self-check chỉ có một lần dịch chương A/en/1.", "INVALID_FAULT_PLAN")
    FaultPlan(delay_ms=delay_ms)
    if fail_provider not in {"none", "tts", "translator"} or not 1 <= fail_on_call <= 3:
        raise WorkspaceError("Cấu hình lỗi giả lập không hợp lệ.", "INVALID_FAULT_PLAN")
    require_tools()
    with manager.lock(name) as path:
        manager.validate(path)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            relative = Path(item["path"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "fixtures":
                raise WorkspaceError("Manifest chứa đường dẫn ngoài fixture.")
            fixture = path / relative
            if not fixture.is_file() or hashlib.sha256(fixture.read_bytes()).hexdigest() != item["sha256"]:
                raise WorkspaceError("Fixture đã thay đổi; reset workspace trước khi self-check.", "FIXTURE_CHANGED", 409)
        numbers = [int(p.name[4:]) for p in (path / "runs").iterdir() if re.fullmatch(r"run-\d{4,}", p.name)]
        run_id = f"run-{max(numbers, default=0) + 1:04d}"
        result_dir = path / "runs" / run_id
        result_dir.mkdir()
        log = result_dir / "calls.jsonl"
        def plan(provider):
            return FaultPlan(fail_on_calls=(fail_on_call,) if fail_provider == provider and not fail_chapter else (),
                             fail_on_chapters=(fail_chapter,) if fail_provider == provider and fail_chapter else (),
                             delay_ms=delay_ms)
        tts = FakeTTSProvider(path / "fixtures/tone.mp3", result_dir, log, plan("tts"))
        translator = FakeTranslator(result_dir, log, plan("translator"))
        outputs, errors = [], []
        for index in (1, 2):
            text = (path / f"fixtures/books/A/{index}_vi.txt").read_text(encoding="utf-8")
            try:
                audio = tts.generate_speech(text, result_dir / f"A-{index}.mp3", chapter_id=f"A/{index}")
                outputs.append({"file": audio.name, "chapter_id": f"A/{index}", **audio_info(audio)})
            except InjectedFailure as error:
                errors.append({"stage": "tts", "chapter_id": f"A/{index}", "message": str(error), "code": "INJECTED_FAILURE"})
        translation = None
        try:
            source = (path / "fixtures/books/A/en/1_en.txt").read_text(encoding="utf-8")
            translation = translator.translate_text(source, chapter_id="A/en/1")
            (result_dir / "translation_vi.txt").write_text(translation, encoding="utf-8")
            try:
                audio = tts.generate_speech(translation, result_dir / "A-en-1.mp3", chapter_id="A/en/1")
                outputs.append({"file": audio.name, "chapter_id": "A/en/1", **audio_info(audio)})
            except InjectedFailure as error:
                errors.append({"stage": "tts", "chapter_id": "A/en/1", "message": str(error), "code": "INJECTED_FAILURE"})
        except InjectedFailure as error:
            errors.append({"stage": "translator", "chapter_id": "A/en/1", "message": str(error), "code": "INJECTED_FAILURE"})
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        passed = not errors and translation is not None and len(outputs) == 3 and all(x["valid"] for x in outputs)
        report = {"workspace": path.name, "run_id": run_id, "mode": "verification", "status": "passed" if passed else "failed",
                  "fixture_version": manifest["fixture_version"], "source_sha256": manifest["source_sha256"],
                  "tts_calls": tts.calls, "translator_calls": translator.calls, "outputs": outputs,
                  "translation": translation, "calls": calls, "errors": errors,
                  "fault_plan": {"provider": fail_provider, "call": fail_on_call, "chapter": fail_chapter, "delay_ms": delay_ms},
                  "notice": "Âm thử 440 Hz, không phải giọng đọc. Bản dịch giả lập, không có API/model thật."}
        atomic_json(result_dir / "report.json", report)
        atomic_json(path / "latest-report.json", report)
        return report
