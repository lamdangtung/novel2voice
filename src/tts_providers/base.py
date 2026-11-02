from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple


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
