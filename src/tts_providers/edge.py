import asyncio
import time

from pathlib import Path
from typing import List, Optional, Tuple

from src import config
from .base import BaseTTSProvider


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
