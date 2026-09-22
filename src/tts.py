import asyncio
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Tuple
from openai import OpenAI
from src import config


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


def get_tts_provider(
    provider_name: Optional[str] = None,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
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
    else:
        raise ValueError(f"Không hỗ trợ TTS provider: {provider_name}. Hãy chọn 'edge-tts' hoặc 'openai'.")
