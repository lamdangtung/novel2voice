"""Own disposable workspaces under one dedicated root, never arbitrary production paths."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / ".verification" / "workspaces"
FIXTURE_SOURCE = PROJECT_ROOT / "tests" / "fixtures" / "t02" / "manifest.json"
NAME = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")


class WorkspaceError(ValueError):
    def __init__(self, message, code="UNSAFE_WORKSPACE", status=400):
        super().__init__(message)
        self.code, self.status = code, status


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def audio_info(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                             "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
                            capture_output=True, text=True, timeout=15)
    try:
        value = json.loads(result.stdout)
        duration = float(value["format"]["duration"])
        valid = result.returncode == 0 and value["streams"][0]["codec_type"] == "audio" and 0 < duration < float("inf")
        return {"valid": valid, "duration_seconds": duration if valid else None}
    except (ValueError, KeyError, IndexError):
        return {"valid": False, "duration_seconds": None}


def require_tools():
    if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")):
        raise WorkspaceError("Cần ffmpeg và ffprobe để sinh và kiểm tra audio mẫu.", "MISSING_AUDIO_TOOLS", 409)


def check_links(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise WorkspaceError("Từ chối workspace hoặc thư mục cha là symlink.")
    if path.exists():
        for entry in path.rglob("*"):
            if entry.is_symlink() or (entry.is_file() and entry.stat().st_nlink > 1):
                raise WorkspaceError("Từ chối workspace chứa symlink hoặc hardlink.")


class WorkspaceManager:
    def __init__(self, root=None):
        self.root = Path(os.path.abspath(root or DEFAULT_ROOT))
        for protected in (PROJECT_ROOT / name for name in ("input", "output", "models", ".git", ".venv", "api/.venv")):
            if self.root.is_relative_to(protected) or protected.is_relative_to(self.root):
                raise WorkspaceError("Vùng kiểm thử không được chồng lên dữ liệu project.")

    def target(self, value):
        value = str(value)
        if value in {"input", "output", "models"}:
            raise WorkspaceError("Không dùng tên hoặc đường dẫn kho thật làm workspace kiểm thử.")
        if NAME.fullmatch(value):
            path = self.root / value
        else:
            path = Path(os.path.abspath(value))
        if path.parent != self.root or not NAME.fullmatch(path.name):
            raise WorkspaceError("Chỉ cho phép workspace con trực tiếp trong " + str(self.root))
        check_links(self.root)
        check_links(path)
        return path

    @contextmanager
    def lock(self, value):
        path = self.target(value)
        locks = self.root / ".locks"
        locks.mkdir(parents=True, exist_ok=True)
        check_links(locks)
        with (locks / f"{path.name}.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WorkspaceError("Workspace đang được xử lý. Thử lại sau khi hoàn tất.", "WORKSPACE_BUSY", 409)
            try:
                yield path
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def validate(self, path):
        path = self.target(path)
        marker = path / ".novel2voice-verification.json"
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise WorkspaceError("Workspace chưa được tạo hoặc không có marker sở hữu hợp lệ.", "WORKSPACE_NOT_FOUND", 404)
        if value != {"owner": "novel2voice-verification", "schema": 1, "name": path.name, "path": str(path)}:
            raise WorkspaceError("Marker không khớp workspace; không cho phép ghi/reset.")
        return path

    def populate(self, path, canonical_path):
        spec_bytes = FIXTURE_SOURCE.read_bytes()
        spec = json.loads(spec_bytes)
        path.mkdir()
        atomic_json(path / ".novel2voice-verification.json", {
            "owner": "novel2voice-verification", "schema": 1,
            "name": canonical_path.name, "path": str(canonical_path)})
        files = []
        for item in spec["text_files"]:
            relative = Path(item["path"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "fixtures":
                raise WorkspaceError("Nguồn fixture có đường dẫn không hợp lệ.")
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bytes.fromhex(item["hex"]) if "hex" in item else item["text"].encode("utf-8"))
            files.append({"path": item["path"], "case": item["case"]})
        tone = path / "fixtures/tone.mp3"
        result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                                 "sine=frequency=440:sample_rate=24000:duration=0.4", "-map_metadata", "-1",
                                 "-codec:a", "libmp3lame", "-b:a", "64k", str(tone)],
                                capture_output=True, text=True, timeout=20)
        if result.returncode or not audio_info(tone)["valid"]:
            raise WorkspaceError("Không sinh được audio mẫu hợp lệ.", "AUDIO_FIXTURE_FAILED", 409)
        files.append({"path": "fixtures/tone.mp3", "case": "tone_not_speech"})
        for item in spec["audio_files"]:
            relative = Path(item["path"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "fixtures":
                raise WorkspaceError("Nguồn fixture có đường dẫn không hợp lệ.")
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if item["valid"]:
                shutil.copyfile(tone, target)
            else:
                target.write_bytes(b"deliberately corrupt mp3 fixture")
            files.append({"path": item["path"], "case": item["case"], "expected_valid_audio": item["valid"]})
        for entry in files:
            entry["sha256"] = hashlib.sha256((path / entry["path"]).read_bytes()).hexdigest()
        (path / "runs").mkdir()
        atomic_json(path / "manifest.json", {"fixture_version": spec["version"],
                    "source_sha256": hashlib.sha256(spec_bytes).hexdigest(), "books": spec["books"], "files": files})

    def create(self, name):
        require_tools()
        with self.lock(name) as path:
            if path.exists():
                self.validate(path)
                return self.describe(path)
            stage = self.root / f".stage-{uuid.uuid4().hex}"
            try:
                self.populate(stage, path)
                stage.rename(path)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            return self.describe(path)

    def reset(self, name, confirmation):
        # Validate destination before even creating a lock or checking confirmation.
        target = self.target(name)
        if confirmation != f"RESET {target.name}":
            raise WorkspaceError(f"Cần xác nhận chính xác: RESET {target.name}", "CONFIRMATION_REQUIRED")
        require_tools()
        with self.lock(name) as path:
            self.validate(path)
            stage = self.root / f".stage-{uuid.uuid4().hex}"
            backup = self.root / f".previous-{uuid.uuid4().hex}"
            try:
                self.populate(stage, path)
                path.rename(backup)
                try:
                    stage.rename(path)
                except BaseException:
                    backup.rename(path)
                    raise
                shutil.rmtree(backup)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            return self.describe(path)

    def describe(self, name):
        path = self.validate(Path(name) if isinstance(name, Path) else name)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        latest = path / "latest-report.json"
        return {"name": path.name, "path": str(path), "mode": "verification", "manifest": manifest,
                "latest_report": json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else None}

    def list(self):
        self.target("probe")  # Validate root without creating it.
        if not self.root.exists():
            return []
        items = []
        for path in sorted(self.root.iterdir()):
            if NAME.fullmatch(path.name) and path.is_dir():
                try:
                    items.append(self.describe(path))
                except WorkspaceError:
                    continue
        return items
