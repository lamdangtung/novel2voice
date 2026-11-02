"""Offline test doubles. Never registered as production providers."""
import hashlib
import json
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FaultPlan:
    fail_on_calls: tuple[int, ...] = ()
    fail_on_chapters: tuple[str, ...] = ()
    delay_ms: int = 0

    def __post_init__(self):
        if not 0 <= self.delay_ms <= 1000:
            raise ValueError("delay_ms phải trong khoảng 0–1000.")
        if any(call < 1 for call in self.fail_on_calls):
            raise ValueError("Số lần gọi gây lỗi phải >= 1.")


class InjectedFailure(RuntimeError):
    pass


def safe_output(root: Path, path: Path):
    root, path = root.absolute(), path.absolute()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Output kiểm thử phải nằm trong vùng kết quả đã cấp.")
    for part in (path, *path.parents):
        if part.is_symlink() or (part.is_file() and part.stat().st_nlink > 1):
            raise ValueError("Không ghi output qua symlink hoặc hardlink.")
        if part == root:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class _Recorder:
    def __init__(self, output_root, log_path, plan=None, chapter_id=""):
        self.output_root = Path(output_root)
        self.log_path = Path(log_path)
        self.plan = plan or FaultPlan()
        self.chapter_id = chapter_id
        self.calls = 0
        self._lock = threading.Lock()

    def record(self, event):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def begin(self, provider, text, chapter_id, chunk_index):
        with self._lock:
            self.calls += 1
            call = self.calls
        event = {"provider": provider, "call": call, "chapter_id": chapter_id,
                 "chunk_index": chunk_index, "input_sha256": hashlib.sha256(text.encode()).hexdigest()}
        self.record({**event, "status": "started"})
        time.sleep(self.plan.delay_ms / 1000)
        if call in self.plan.fail_on_calls or chapter_id in self.plan.fail_on_chapters:
            self.record({**event, "status": "failed", "error": "INJECTED_FAILURE"})
            raise InjectedFailure(f"Lỗi chủ động {provider}, lần gọi {call}, chương {chapter_id}, đoạn {chunk_index}.")
        return event


class FakeTTSProvider(_Recorder):
    voice = "verification-tone"
    model = "offline-fixture"

    def __init__(self, fixture, output_root, log_path, plan=None, chapter_id=""):
        super().__init__(output_root, log_path, plan, chapter_id)
        self.fixture = Path(fixture)
        self.model = "offline-fixture:" + hashlib.sha256(self.fixture.read_bytes()).hexdigest()

    def generate_speech(self, text, output_path, *, chapter_id=None, chunk_index=1):
        if not text.strip():
            raise ValueError("Text kiểm thử rỗng.")
        event = self.begin("fake-tts", text, chapter_id or self.chapter_id, chunk_index)
        destination = safe_output(self.output_root, Path(output_path))
        shutil.copyfile(self.fixture, destination)
        self.record({**event, "status": "completed", "output": destination.relative_to(self.output_root).as_posix()})
        return destination

    def generate_batch(self, tasks, max_concurrency=3, show_progress=True):
        # Intentionally sequential and predictable; compatible with the TTS runner protocol.
        if max_concurrency < 1:
            raise ValueError("max_concurrency phải >= 1.")
        return [self.generate_speech(text, output, chunk_index=index)
                for index, (text, output) in enumerate(tasks, 1)]


class FakeTranslator(_Recorder):
    model = "verification-translator"

    def __init__(self, output_root, log_path, plan=None, chapter_id="", *, glossary=None, model=None, prompt_hash=None, glossary_hash=None):
        super().__init__(output_root, log_path, plan, chapter_id)
        self.glossary=glossary
        self.model=model or "verification-translator"
        self.prompt_hash=prompt_hash
        self.glossary_hash=glossary_hash

    def translate_text(self, text, max_chunk_chars=4000, *, chapter_id=None, chunk_index=1):
        if not text.strip():
            raise ValueError("Text kiểm thử rỗng.")
        if self.glossary is not None:
            self.record({"provider":"fake-translator","status":"request_context","chunk_index":chunk_index,
                         "model":self.model,"prompt_hash":self.prompt_hash,"glossary_hash":self.glossary_hash})
        event = self.begin("fake-translator", text, chapter_id or self.chapter_id, chunk_index)
        result = ("[BẢN DỊCH KIỂM THỬ — KHÔNG PHẢI KẾT QUẢ AI]\n\n"
                  "Bình minh lên sau ngọn đồi. Hai người bạn bắt đầu cuộc hành trình.\n"
                  f"Dấu vết nguồn: {event['input_sha256'][:12]}\n")
        if self.glossary is not None and self.glossary.entries:
            result += "Thuật ngữ kiểm thử: " + "; ".join(en[:100]+" → "+vi[:100] for en,vi in list(self.glossary.entries.items())[:2]) + "\n"
        self.record({**event, "status": "completed"})
        return result

    def translate_chunk(self, text_chunk):
        return self.translate_text(text_chunk)

    def translate_file(self, input_file, output_file=None):
        if output_file is None:
            raise ValueError("FakeTranslator cần output_file trong workspace kiểm thử.")
        output = safe_output(self.output_root, Path(output_file))
        output.write_text(self.translate_text(Path(input_file).read_text(encoding="utf-8")), encoding="utf-8")
        return output
