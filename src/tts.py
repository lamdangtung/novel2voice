import asyncio
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Tuple
from openai import OpenAI
from src import config
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

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


class BaseTTSProvider(ABC):
    """Lớp cơ sở cho các dịch vụ chuyển đổi văn bản thành giọng nói."""

    @abstractmethod
    def generate_speech(self, text: str, output_path: Path) -> Path:
        pass

    @abstractmethod
    def generate_batch(
        self,
        tasks: List[Tuple[str, Path]],
        max_concurrency: int = 3,
        show_progress: bool = True
    ) -> List[Path]:
        """Tạo nhiều đoạn audio đồng thời / đa luồng."""
        pass


class EdgeTTSProvider(BaseTTSProvider):
    """
    Sử dụng Microsoft Edge TTS - hoàn toàn miễn phí, chất lượng giọng Việt rất cao.
    Các giọng tiếng Việt chuẩn:
    - vi-VN-HoaiMyNeural (Nữ - truyền cảm, đọc truyện rất hay)
    - vi-VN-NamMinhNeural (Nam - trầm ấm, dẫn truyện tốt)
    """

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None,
        max_retries: int = 4,
    ):
        self.voice = voice or config.TTS_VOICE
        self.rate = rate or config.TTS_RATE
        self.volume = volume or config.TTS_VOLUME
        self.pitch = pitch or config.TTS_PITCH
        self.max_retries = max_retries

    async def _async_generate(self, text: str, output_path: Path):
        import edge_tts
        import re

        # Chuẩn hóa khoảng trắng và ngắt dòng để tránh lỗi SSML trên server Edge-TTS
        cleaned_text = re.sub(r"\s+", " ", text).strip()
        if not cleaned_text:
            return

        kwargs = {}
        if self.rate and self.rate != "+0%":
            kwargs["rate"] = self.rate
        if self.volume and self.volume != "+0%":
            kwargs["volume"] = self.volume
        if self.pitch and self.pitch != "+0Hz":
            kwargs["pitch"] = self.pitch

        last_err = None
        for attempt in range(self.max_retries):
            try:
                communicate = edge_tts.Communicate(
                    text=cleaned_text,
                    voice=self.voice,
                    **kwargs
                )
                await communicate.save(str(output_path))
                return
            except Exception as e:
                last_err = e
                # Backoff khi mạng hoặc server bận
                wait_time = (attempt + 1) * 1.5
                await asyncio.sleep(wait_time)

        raise RuntimeError(f"Tạo TTS thất bại sau {self.max_retries} lần thử: {last_err}")

    def generate_speech(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            loop.run_until_complete(self._async_generate(text, output_path))
        else:
            asyncio.run(self._async_generate(text, output_path))

        time.sleep(0.1)
        return output_path

    async def _async_generate_batch(
        self,
        tasks: List[Tuple[str, Path]],
        max_concurrency: int = 3,
        show_progress: bool = True
    ) -> List[Path]:
        semaphore = asyncio.Semaphore(max_concurrency)
        output_paths = [path for _, path in tasks]

        for _, path in tasks:
            path.parent.mkdir(parents=True, exist_ok=True)

        from tqdm import tqdm
        pbar = tqdm(total=len(tasks), desc="Đang đọc TTS (song song)", unit="đoạn") if show_progress else None

        async def worker(text: str, out_path: Path):
            async with semaphore:
                await self._async_generate(text, out_path)
                if pbar:
                    pbar.update(1)
                # Nghỉ nhẹ giữa các request để giữ kết nối ổn định
                await asyncio.sleep(0.1)
                return out_path

        try:
            coros = [worker(text, path) for text, path in tasks]
            await asyncio.gather(*coros)
            return output_paths
        finally:
            if pbar:
                pbar.close()

    def generate_batch(
        self,
        tasks: List[Tuple[str, Path]],
        max_concurrency: int = 3,
        show_progress: bool = True
    ) -> List[Path]:
        if not tasks:
            return []

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(
                self._async_generate_batch(tasks, max_concurrency, show_progress)
            )
        else:
            return asyncio.run(
                self._async_generate_batch(tasks, max_concurrency, show_progress)
            )


class OpenAITTSProvider(BaseTTSProvider):
    """
    Sử dụng OpenAI TTS API (tts-1 hoặc tts-1-hd).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "tts-1",
        voice: str = "alloy",
    ):
        self.api_key = api_key or config.OPENAI_API_KEY
        self.base_url = base_url or config.OPENAI_BASE_URL
        self.model = model
        self.voice = voice

        if not self.api_key:
            raise ValueError("Cần OPENAI_API_KEY để sử dụng OpenAI TTS.")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_speech(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        response = self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
        )
        response.stream_to_file(str(output_path))
        return output_path

    def generate_batch(
        self,
        tasks: List[Tuple[str, Path]],
        max_concurrency: int = 3,
        show_progress: bool = True
    ) -> List[Path]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm

        output_paths = [path for _, path in tasks]
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            future_to_path = {
                executor.submit(self.generate_speech, text, path): path
                for text, path in tasks
            }
            if show_progress:
                pbar = tqdm(total=len(tasks), desc="Đang đọc OpenAI TTS (song song)", unit="đoạn")
                for future in as_completed(future_to_path):
                    future.result()
                    pbar.update(1)
                pbar.close()
            else:
                for future in as_completed(future_to_path):
                    future.result()

        return output_paths

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

def get_tts_provider(
    provider_name: Optional[str] = None,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    piper_model_path: Optional[str] = None,
    piper_config_path: Optional[str] = None,
    piper_num_workers: Optional[int] = None,
) -> BaseTTSProvider:
    """Factory hàm khởi tạo TTS provider theo cấu hình."""
    provider_name = (provider_name or config.TTS_PROVIDER).lower()

    if provider_name == "openai":
        return OpenAITTSProvider(
            api_key=api_key,
            base_url=base_url,
            voice=voice or "alloy"
        )
    elif provider_name in ("edge-tts", "edge_tts", "edge"):
        return EdgeTTSProvider(
            voice=voice or config.TTS_VOICE,
            rate=rate or config.TTS_RATE
        )
    elif provider_name in ("local", "piper"):
        return LocalTTSProvider(
            model_path=piper_model_path or config.PIPER_MODEL_PATH,
            config_path=piper_config_path or config.PIPER_CONFIG_PATH,
            num_workers=piper_num_workers or config.PIPER_NUM_WORKERS,
        )
    else:
        raise ValueError(f"Không hỗ trợ TTS provider: {provider_name}. Hãy chọn 'edge-tts' hoặc 'openai'.")
