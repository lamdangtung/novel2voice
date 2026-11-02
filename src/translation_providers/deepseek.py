"""In-process adapter for the vendored infra/Deepseek-API client.

The private package alias avoids changing sys.path or shadowing installed packages.
Only selecting DeepSeek loads its optional browser/PoW dependencies.
"""
import importlib.util
import sys
from pathlib import Path
from threading import Lock
from .deepseek_scheduler import RequestScheduler, get_deepseek_scheduler

_LOAD_LOCK = Lock()
_PACKAGE = "_novel2voice_deepseek"


def _load_client_class():
    with _LOAD_LOCK:
        if _PACKAGE not in sys.modules:
            root = Path(__file__).resolve().parents[2] / "infra" / "Deepseek-API" / "deepseek"
            if not (root / "__init__.py").is_file():
                raise RuntimeError(f"Không tìm thấy DeepSeek client tại {root}.")
            spec = importlib.util.spec_from_file_location(
                _PACKAGE, root / "__init__.py", submodule_search_locations=[str(root)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[_PACKAGE] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                for name in list(sys.modules):
                    if name == _PACKAGE or name.startswith(_PACKAGE + "."):
                        del sys.modules[name]
                raise
        return sys.modules[_PACKAGE].DeepSeekClient


class DeepSeekTranslationProvider:
    def __init__(self, *, model="deepseek-chat", max_chunks_per_conversation=5, client=None, scheduler: RequestScheduler | None = None):
        models = {"deepseek-chat": "default", "deepseek-expert": "expert"}
        if model not in models:
            raise ValueError(f"Model DeepSeek không hợp lệ: {model}. Chọn {', '.join(models)}.")
        if max_chunks_per_conversation < 1:
            raise ValueError("DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION phải >= 1.")
        self.scheduler = scheduler if scheduler is not None else get_deepseek_scheduler()
        self.max_chunks_per_conversation = max_chunks_per_conversation
        self._conversation_id = None
        self._chunk_count = 0
        self._system_prompt = None
        self.model = models[model]
        self._client = client
        self._owns_client = client is None
        self._lock = Lock()

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        # Serialize the whole request: the native client owns mutable session/PoW state.
        with self._lock, self.scheduler.slot():
            if self._client is None:
                try:
                    client_class = _load_client_class()
                except ImportError as error:
                    raise RuntimeError(
                        "Thiếu dependency DeepSeek. Cài requirements-deepseek.txt "
                        "và chạy playwright install chromium.") from error
                try:
                    self._client = client_class(allow_interactive=False)
                except Exception as error:
                    if type(error).__name__ == "LoginRequired":
                        raise RuntimeError(
                            "DeepSeek cần đăng nhập. Chạy trong infra/Deepseek-API: "
                            "python -m deepseek.auth") from error
                    raise
            if (self._chunk_count >= self.max_chunks_per_conversation
                    or system_prompt != self._system_prompt):
                self._reset()
            # Only a new conversation receives instructions and glossary.
            if self._conversation_id is None:
                prompt = f"System: {system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"
                options = {"model": self.model}
            else:
                prompt = user_prompt
                options = {"conversation_id": self._conversation_id}
            try:
                reply = self._client.chat(prompt, **options, thinking=False, search=False)
                if not isinstance(reply.text, str) or not reply.text.strip():
                    raise ValueError("DeepSeek trả về bản dịch rỗng.")
                conversation_id = getattr(reply, "conversation_id", None)
                if not isinstance(conversation_id, str) or not conversation_id.strip():
                    raise ValueError("DeepSeek không trả về conversation_id hợp lệ.")
            except Exception as error:
                if type(error).__name__ == "LoginRequired":
                    raise RuntimeError(
                        "DeepSeek cần đăng nhập. Chạy trong infra/Deepseek-API: "
                        "python -m deepseek.auth") from error
                raise
            self._conversation_id = conversation_id
            self._chunk_count += 1
            self._system_prompt = system_prompt
            return reply.text

    def _reset(self):
        self._conversation_id = None
        self._chunk_count = 0
        self._system_prompt = None

    @property
    def conversation_limit(self) -> int:
        return self.max_chunks_per_conversation

    def reset_conversation(self) -> None:
        with self._lock:
            self._reset()

    def close(self) -> None:
        with self._lock:
            self._reset()
            if self._client is not None and self._owns_client:
                self._client.close()
                self._client = None
