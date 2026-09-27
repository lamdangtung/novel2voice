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
import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

from src import config

logger = logging.getLogger(__name__)

_PIPER_WORKER_STATE: dict = {}


def _fmt_secs(seconds: float) -> str:
    """Format thời gian cho dễ đọc."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m {s:.1f}s"


def _fmt_size(path: Path) -> str:
    """Format kích thước file cho dễ đọc."""
    try:
        size = float(path.stat().st_size)
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def _fmt_size_bytes(size: float) -> str:
    """Format kích thước theo bytes (int/float) cho dễ đọc."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

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

class VieNeuTTSProvider(BaseTTSProvider):
    """
    Local TTS sử dụng VieNeu-TTS - on-device Vietnamese TTS với chất lượng cao.

    Hỗ trợ:
    - v3 Turbo (mặc định, 48kHz, torch-free trên CPU qua ONNX)
    - Standard mode (GGUF/PyTorch)
    - Remote mode (kết nối server)
    - Instant voice cloning (qua ref_audio)
    - Batch generation tối ưu (infer_batch)

    Ví dụ:
        provider = VieNeuTTSProvider(
            mode="v3turbo",
            voice="Minh Quân",
            backbone_device="cpu",
        )
        provider.generate_speech("Xin chào", Path("out.wav"))
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        voice: Optional[str] = None,
        backbone_repo: Optional[str] = None,
        backbone_device: Optional[str] = None,
        precision: Optional[str] = None,
        codec_repo: Optional[str] = None,
        codec_device: Optional[str] = None,
        hf_token: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
        # Voice cloning
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
    ):
        self.mode = mode or getattr(config, "VIENEU_MODE", "v3turbo")
        self.voice = voice or getattr(config, "VIENEU_VOICE", None)
        self.backbone_repo = backbone_repo or getattr(config, "VIENEU_BACKBONE_REPO", None)
        self.backbone_device = backbone_device or getattr(config, "VIENEU_BACKBONE_DEVICE", "cpu")
        self.precision = precision or getattr(config, "VIENEU_PRECISION", None)
        self.codec_repo = codec_repo or getattr(config, "VIENEU_CODEC_REPO", None)
        self.codec_device = codec_device or getattr(config, "VIENEU_CODEC_DEVICE", "cpu")
        self.hf_token = hf_token or getattr(config, "HF_TOKEN", None)
        self.api_base = api_base or getattr(config, "VIENEU_API_BASE", None)
        self.model_name = model_name or getattr(config, "VIENEU_MODEL_NAME", None)

        # Voice cloning
        self.ref_audio = ref_audio
        self.ref_text = ref_text

        self._tts = None  # Lazy load

        logger.info(
            "Khởi tạo VieNeuTTSProvider | mode=%s | voice=%s | backbone_device=%s | "
            "codec_device=%s | precision=%s | remote=%s",
            self.mode,
            self.voice or "<default>",
            self.backbone_device,
            self.codec_device,
            self.precision or "auto",
            self.mode == "remote",
        )
        if self.ref_audio:
            logger.info("  • Voice cloning: ref_audio=%s | ref_text=%s",
                        self.ref_audio, "có" if self.ref_text else "không")
        if not self.hf_token:
            logger.debug("  • Không có HF_TOKEN — sẽ dùng chế độ unauthenticated.")

    # ------------------------------------------------------------
    # Lazy load
    # ------------------------------------------------------------
    def _ensure_tts(self):
        """Khởi tạo VieNeu-TTS instance lần đầu (lazy load)."""
        if self._tts is not None:
            return

        # Giảm nhiễu log từ HuggingFace Hub khi không có token
        if not self.hf_token:
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

        logger.info("Đang nạp VieNeu-TTS (mode=%s)...", self.mode)
        t0 = time.perf_counter()

        try:
            from vieneu import Vieneu
        except ImportError as e:
            logger.error("Không import được `vieneu`. Cài đặt: pip install vieneu")
            raise ImportError(
                "Chưa cài VieNeu-TTS. Chạy: pip install vieneu"
            ) from e

        kwargs = {"mode": self.mode}

        if self.mode == "remote":
            if not self.api_base or not self.model_name:
                msg = (
                    "Remote mode cần api_base và model_name. "
                    "Set VIENEU_API_BASE và VIENEU_MODEL_NAME trong config."
                )
                logger.error(msg)
                raise ValueError(msg)
            kwargs["api_base"] = self.api_base
            kwargs["model_name"] = self.model_name
            logger.info("  • Remote endpoint: %s | model=%s",
                        self.api_base, self.model_name)
        else:
            # Standard / fast / v3turbo mode
            if self.backbone_repo:
                kwargs["backbone_repo"] = self.backbone_repo
                logger.info("  • Backbone repo: %s", self.backbone_repo)
            if self.backbone_device:
                kwargs["backbone_device"] = self.backbone_device
                logger.info("  • Backbone device: %s", self.backbone_device)
            if self.precision:
                kwargs["precision"] = self.precision
                logger.info("  • Precision: %s", self.precision)
            if self.codec_repo:
                kwargs["codec_repo"] = self.codec_repo
                logger.info("  • Codec repo: %s", self.codec_repo)
            if self.codec_device:
                kwargs["codec_device"] = self.codec_device
                logger.info("  • Codec device: %s", self.codec_device)
            if self.hf_token:
                kwargs["hf_token"] = self.hf_token
                logger.info("  • HF_TOKEN: đã cung cấp")

        try:
            self._tts = Vieneu(**kwargs)
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Nạp VieNeu-TTS thất bại sau %s: %s", _fmt_secs(elapsed), e
            )
            raise

        elapsed = time.perf_counter() - t0
        logger.info("Đã nạp VieNeu-TTS thành công trong %s", _fmt_secs(elapsed))

    def _build_infer_kwargs(self) -> dict:
        """Xây dựng kwargs cho infer/infer_batch tùy theo cấu hình."""
        kwargs = {}
        if self.ref_audio:
            kwargs["ref_audio"] = self.ref_audio
            if self.ref_text:
                kwargs["ref_text"] = self.ref_text
        elif self.voice:
            kwargs["voice"] = self.voice
        return kwargs

    # ------------------------------------------------------------
    # Save / convert
    # ------------------------------------------------------------
    def _save_with_format(self, audio, output_path: Path):
        """Lưu audio ra .wav hoặc .mp3."""
        import subprocess
        import tempfile

        output_path.parent.mkdir(parents=True, exist_ok=True)
        ext = output_path.suffix.lower()

        if ext == ".wav":
            t0 = time.perf_counter()
            self._tts.save(audio, str(output_path))
            logger.debug(
                "  ↳ Lưu WAV: %s (%s) trong %s",
                output_path.name, _fmt_size(output_path), _fmt_secs(time.perf_counter() - t0),
            )
        elif ext == ".mp3":
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            wav_path = Path(tmp.name)
            tmp.close()
            try:
                t0 = time.perf_counter()
                self._tts.save(audio, str(wav_path))
                wav_size = wav_path.stat().st_size if wav_path.exists() else 0
                logger.debug(
                    "  ↳ Lưu WAV tạm: %s trong %s",
                    _fmt_size(wav_path), _fmt_secs(time.perf_counter() - t0),
                )
                if wav_size < 1000:
                    logger.warning(
                        "WAV tạm quá nhỏ (%d bytes) — có thể synth thất bại", wav_size
                    )

                t1 = time.perf_counter()
                result = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error",
                     "-i", str(wav_path),
                     "-codec:a", "libmp3lame", "-b:a", "128k",
                     str(output_path)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    logger.error(
                        "ffmpeg convert MP3 thất bại cho %s: %s",
                        output_path.name, result.stderr.strip(),
                    )
                    raise RuntimeError(f"ffmpeg lỗi cho {output_path.name}: {result.stderr}")
                logger.debug(
                    "  ↳ Convert MP3: %s (%s) trong %s",
                    output_path.name, _fmt_size(output_path),
                    _fmt_secs(time.perf_counter() - t1),
                )
            finally:
                try:
                    wav_path.unlink()
                except OSError:
                    pass
        else:
            raise ValueError(f"VieNeuTTSProvider chỉ hỗ trợ .wav hoặc .mp3, nhận: {ext}")

    # ------------------------------------------------------------
    # Single
    # ------------------------------------------------------------
    def generate_speech(self, text: str, output_path: Path) -> Path:
        if not text or not text.strip():
            raise ValueError(f"Text rỗng cho output: {output_path}")

        self._ensure_tts()
        infer_kwargs = self._build_infer_kwargs()

        voice_label = (
            f"clone:{Path(self.ref_audio).name}" if self.ref_audio
            else (self.voice or "<default>")
        )
        logger.info(
            "Synth 1 đoạn | voice=%s | text_len=%d ký tự | → %s",
            voice_label, len(text), output_path.name,
        )

        t0 = time.perf_counter()
        try:
            audio = self._tts.infer(text=text, **infer_kwargs)
        except Exception as e:
            logger.exception(
                "infer() thất bại sau %s cho %s: %s",
                _fmt_secs(time.perf_counter() - t0), output_path.name, e,
            )
            raise
        synth_time = time.perf_counter() - t0

        t1 = time.perf_counter()
        self._save_with_format(audio, output_path)
        save_time = time.perf_counter() - t1

        # Kiểm tra file có dữ liệu thật
        if not output_path.exists() or output_path.stat().st_size < 1000:
            size = output_path.stat().st_size if output_path.exists() else 0
            logger.error(
                "File audio rỗng sau synth: %s (size=%d bytes)", output_path, size
            )
            raise RuntimeError(
                f"File audio rỗng sau synth: {output_path} (size={size} bytes)"
            )

        logger.info(
            "✔ Xong %s | size=%s | infer=%s | save=%s | tổng=%s",
            output_path.name, _fmt_size(output_path),
            _fmt_secs(synth_time), _fmt_secs(save_time),
            _fmt_secs(synth_time + save_time),
        )
        return output_path

    # ------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------
    def generate_batch(
        self,
        tasks: List[Tuple[str, Path]],
        max_concurrency: int = 3,
        show_progress: bool = True,
    ) -> List[Path]:
        if not tasks:
            logger.debug("generate_batch: không có task nào.")
            return []

        n = len(tasks)
        total_chars = sum(len(t) for t, _ in tasks)
        logger.info(
            "Batch VieNeu TTS | mode=%s | %d đoạn | %d ký tự | batch_size=%d",
            self.mode, n, total_chars, max_concurrency,
        )

        t_init = time.perf_counter()
        self._ensure_tts()
        init_time = time.perf_counter() - t_init

        texts = [text for text, _ in tasks]
        output_paths = [path for _, path in tasks]

        for _, path in tasks:
            path.parent.mkdir(parents=True, exist_ok=True)

        from tqdm import tqdm

        infer_kwargs = self._build_infer_kwargs()

        # infer_batch xử lý batch nội bộ (tối ưu cho GPU/CPU)
        batch_kwargs = dict(infer_kwargs)
        t_infer = time.perf_counter()
        try:
            try:
                audios = self._tts.infer_batch(
                    texts, batch_size=max_concurrency, **batch_kwargs
                )
                logger.debug("infer_batch: có hỗ trợ tham số batch_size=%d", max_concurrency)
            except TypeError:
                # Fallback: không truyền batch_size
                logger.debug("infer_batch: không hỗ trợ batch_size, dùng mặc định SDK")
                audios = self._tts.infer_batch(texts, **batch_kwargs)
        except Exception as e:
            logger.exception(
                "infer_batch() thất bại sau %s: %s",
                _fmt_secs(time.perf_counter() - t_infer), e,
            )
            raise
        infer_time = time.perf_counter() - t_infer

        n_audios = len(audios) if hasattr(audios, "__len__") else None
        logger.info(
            "infer_batch xong: %s đoạn trong %s (%.2f đoạn/s)",
            n_audios if n_audios is not None else "?",
            _fmt_secs(infer_time),
            (n_audios / infer_time) if (n_audios and infer_time > 0) else 0.0,
        )

        pbar = (
            tqdm(total=n, desc=f"Đang đọc VieNeu TTS ({self.mode})", unit="đoạn")
            if show_progress else None
        )

        t_save = time.perf_counter()
        total_size = 0
        try:
            for i, (audio, out_path) in enumerate(zip(audios, output_paths), 1):
                try:
                    self._save_with_format(audio, out_path)
                    if out_path.exists():
                        total_size += out_path.stat().st_size
                except Exception as e:
                    logger.error(
                        "Lỗi khi lưu đoạn %d/%d → %s: %s", i, n, out_path.name, e
                    )
                    raise
                if pbar:
                    pbar.update(1)
        finally:
            if pbar:
                pbar.close()
        save_time = time.perf_counter() - t_save

        logger.info(
            "✔ Batch hoàn tất | %d/%d đoạn | init=%s | infer=%s | save=%s | tổng size=%s",
            n, n, _fmt_secs(init_time), _fmt_secs(infer_time),
            _fmt_secs(save_time), _fmt_size_bytes(total_size),
        )
        return output_paths

    # ------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------
    def close(self):
        """Giải phóng tài nguyên."""
        if self._tts is not None:
            logger.info("Đóng VieNeu-TTS...")
            try:
                self._tts.close()
                logger.debug("Đã đóng VieNeu-TTS.")
            except Exception as e:
                logger.warning("Lỗi khi đóng VieNeu-TTS: %s", e)
            self._tts = None


def get_tts_provider(
    provider_name: Optional[str] = None,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    piper_model_path: Optional[str] = None,
    piper_config_path: Optional[str] = None,
    piper_num_workers: Optional[int] = None,
    vieneu_mode: Optional[str] = None,
    vieneu_backbone_repo: Optional[str] = None,
    vieneu_backbone_device: Optional[str] = None,
    vieneu_precision: Optional[str] = None,
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
    elif provider_name in ("vieneu", "vieneu-tts"):
        return VieNeuTTSProvider(
            mode=vieneu_mode,
            voice=voice,
            backbone_repo=vieneu_backbone_repo,
            backbone_device=vieneu_backbone_device,
            precision=vieneu_precision,
        )
    else:
        raise ValueError(
            f"Không hỗ trợ TTS provider: {provider_name}. "
            f"Hãy chọn 'edge-tts', 'openai', 'local', hoặc 'vieneu'."
        )
