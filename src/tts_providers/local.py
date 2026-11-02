import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

from pathlib import Path
from typing import List, Optional, Tuple

from src import config
from .base import BaseTTSProvider


_PIPER_WORKER_STATE: dict = {}


def _piper_worker_init(model_path: str, config_path: Optional[str]):
    """Khởi tạo model 1 lần cho mỗi process con."""
    from piper.voice import PiperVoice
    _PIPER_WORKER_STATE["voice"] = PiperVoice.load(
        model_path, config_path=config_path
    )


def _piper_worker_task(args):
    """Sinh 1 đoạn audio trong process con. Tự nhận diện .wav / .mp3."""
    import wave
    import subprocess
    import tempfile

    text, out_path_str = args
    voice = _PIPER_WORKER_STATE["voice"]
    out_path = Path(out_path_str)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not text or not text.strip():
        raise ValueError(f"Text rỗng cho output: {out_path}")

    ext = out_path.suffix.lower()

    # --- Ghi WAV tạm ---
    if ext == ".wav":
        wav_path = out_path
        cleanup_wav = False
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav_path = Path(tmp.name)
        tmp.close()
        cleanup_wav = True

    # --- Synth (API Piper >= 1.8.0: trả về Iterable[AudioChunk]) ---
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)   # 16-bit PCM
        wav_file.setframerate(voice.config.sample_rate)

        for chunk in voice.synthesize(text):
            # AudioChunk có attribute audio_int16_bytes
            wav_file.writeframes(chunk.audio_int16_bytes)

    # --- Kiểm tra WAV có dữ liệu thật ---
    wav_size = wav_path.stat().st_size if wav_path.exists() else 0
    if wav_size < 1000:
        raise RuntimeError(
            f"WAV rỗng sau synth: {wav_path} (size={wav_size} bytes, "
            f"text_len={len(text)})"
        )

    # --- Convert sang MP3 nếu cần ---
    if ext == ".mp3":
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-b:a", "128k",
             str(out_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg lỗi cho {out_path.name}: {result.stderr}")
    elif ext not in (".wav", ".mp3"):
        raise ValueError(f"LocalTTSProvider chỉ hỗ trợ .wav hoặc .mp3, nhận: {ext}")

    if cleanup_wav:
        try:
            wav_path.unlink()
        except OSError:
            pass

    return out_path_str


class LocalTTSProvider(BaseTTSProvider):
    """
    Local TTS sử dụng Piper - chạy offline, cực nhanh trên Mac Mini M4.

    - generate_speech: dùng cho 1 đoạn lẻ (chạy trong process hiện tại).
    - generate_batch:  dùng ProcessPoolExecutor → song song thật trên nhiều core.

    Ví dụ:
        provider = LocalTTSProvider(
            model_path="models/piper/vi_VN-vais1000-medium.onnx",
            config_path="models/piper/vi_VN-vais1000-medium.onnx.json",
            num_workers=4,
        )
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        config_path: Optional[str] = None,
        num_workers: Optional[int] = None,
    ):
        self.model_path = model_path or config.PIPER_MODEL_PATH
        self.config_path = config_path or getattr(config, "PIPER_CONFIG_PATH", None)
        self.num_workers = num_workers or getattr(config, "PIPER_NUM_WORKERS", 4)

        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"Không tìm thấy model Piper: {self.model_path}\n"
                f"Chạy: ./scripts/setup_piper.sh để tải model."
            )

        # Lazy-load cho generate_speech
        self._voice = None
        self._lock = None

    # ---------- Single ----------
    def _ensure_voice(self):
        if self._voice is None:
            import threading
            from piper.voice import PiperVoice
            self._voice = PiperVoice.load(
                self.model_path, config_path=self.config_path
            )
            self._lock = threading.Lock()

    def generate_speech(self, text: str, output_path: Path) -> Path:
        import wave
        import subprocess
        import tempfile
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_voice()
        if not text or not text.strip():
            raise ValueError(f"Text rỗng cho output: {output_path}")
        
        ext = output_path.suffix.lower()
        if ext == ".wav":
            wav_path = output_path
            cleanup_wav = False
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            wav_path = Path(tmp.name)
            tmp.close()
            cleanup_wav = True
        with self._lock:
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self._voice.config.sample_rate)
                for chunk in self._voice.synthesize(text):
                    wav_file.writeframes(chunk.audio_int16_bytes)
        wav_size = wav_path.stat().st_size if wav_path.exists() else 0
        if wav_size < 1000:
            raise RuntimeError(f"WAV rỗng: {wav_path} ({wav_size} bytes)")
        if ext == ".mp3":
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                "-i", str(wav_path),
                "-codec:a", "libmp3lame", "-b:a", "128k",
                str(output_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg lỗi: {result.stderr}")
        elif ext not in (".wav", ".mp3"):
            raise ValueError(f"LocalTTSProvider chỉ hỗ trợ .wav hoặc .mp3, nhận: {ext}")
        if cleanup_wav:
            try:
                wav_path.unlink()
            except OSError:
                pass

        return output_path

    # ---------- Batch (multiprocessing) ----------
    def generate_batch(
        self,
        tasks: List[Tuple[str, Path]],
        max_concurrency: int = 3,
        show_progress: bool = True
    ) -> List[Path]:
        if not tasks:
            return []

        # Với Piper local: max_concurrency chính là số worker
        workers = max_concurrency or self.num_workers
        output_paths = [path for _, path in tasks]
        work_args = [(text, str(path)) for text, path in tasks]

        for _, path in tasks:
            path.parent.mkdir(parents=True, exist_ok=True)

        from tqdm import tqdm
        pbar = (
            tqdm(total=len(tasks), desc=f"Đang đọc Piper TTS ({workers} workers)", unit="đoạn")
            if show_progress else None
        )

        # 'spawn' an toàn hơn 'fork' trên macOS
        ctx = mp.get_context("spawn")

        try:
            with ProcessPoolExecutor(
                max_workers=workers,
                mp_context=ctx,
                initializer=_piper_worker_init,
                initargs=(self.model_path, self.config_path),
            ) as executor:
                futures = [executor.submit(_piper_worker_task, arg) for arg in work_args]
                for fut in as_completed(futures):
                    fut.result()  # raise nếu có lỗi
                    if pbar:
                        pbar.update(1)
        finally:
            if pbar:
                pbar.close()

        return output_paths
