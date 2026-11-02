import logging
import os
import time

from pathlib import Path
from typing import List, Optional, Tuple

from src import config
from .base import BaseTTSProvider

logger = logging.getLogger(__name__)


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
        """Publish a complete encoded file atomically; interrupted writes stay temporary."""
        import subprocess
        import tempfile

        output_path.parent.mkdir(parents=True, exist_ok=True)
        ext = output_path.suffix.lower()
        if ext not in (".wav", ".mp3"):
            raise ValueError(f"VieNeuTTSProvider chỉ hỗ trợ .wav hoặc .mp3, nhận: {ext}")
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=output_path.parent, delete=False) as stream:
            wav_path = Path(stream.name)
        encoded = output_path.with_name(f".{output_path.stem}.writing.mp3")
        try:
            self._tts.save(audio, str(wav_path))
            if wav_path.stat().st_size < 1000:
                raise RuntimeError(f"WAV rỗng sau synth: {output_path.name}")
            if ext == ".wav":
                wav_path.replace(output_path)
            else:
                result = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
                     "-codec:a", "libmp3lame", "-b:a", "128k", str(encoded)],
                    capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"ffmpeg lỗi cho {output_path.name}: {result.stderr}")
                encoded.replace(output_path)
        finally:
            wav_path.unlink(missing_ok=True)
            encoded.unlink(missing_ok=True)

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

        audios = list(audios)
        if len(audios) != len(tasks):
            raise RuntimeError(f"VieNeu trả về {len(audios)} audio cho {len(tasks)} đoạn.")
        n_audios = len(audios)
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
