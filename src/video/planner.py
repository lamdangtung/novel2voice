"""Plan video episodes without merging or modifying chapter artifacts."""
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.utils import natural_sort_paths


@dataclass(frozen=True)
class VideoEpisode:
    number: int
    chapter_audio: tuple[Path, ...]


def plan_videos(chapter_audio: Sequence[Path], *, chapters_per_video: int = 1) -> list[VideoEpisode]:
    if isinstance(chapters_per_video, bool) or not isinstance(chapters_per_video, int) or chapters_per_video < 1:
        raise ValueError('chapters_per_video phải là số nguyên >= 1.')
    paths = [Path(path) for path in chapter_audio]
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError('Danh sách audio chứa chương trùng.')
    paths = natural_sort_paths(paths)
    return [VideoEpisode(index // chapters_per_video + 1, tuple(paths[index:index + chapters_per_video]))
            for index in range(0, len(paths), chapters_per_video)]
