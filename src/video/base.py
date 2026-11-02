"""Contracts for video rendering and reusable artwork."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class VideoSpec:
    chapter_audio: tuple[Path, ...]
    background: Path
    output: Path
    title: str = ''
    width: int = 1920
    height: int = 1080
    fps: int = 30
    font_path: Path | None = None
    thumbnail_text: str | None = None


class ThumbnailGenerator(Protocol):
    def generate(self, spec: VideoSpec, output: Path) -> None:
        ...


class VideoRenderer(Protocol):
    def render(self, spec: VideoSpec, *, resume: bool = True) -> Path:
        ...
