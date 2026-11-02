from openai import OpenAI

from pathlib import Path
from typing import List, Optional, Tuple

from src import config
from .base import BaseTTSProvider


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
