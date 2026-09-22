import re
from pathlib import Path
from typing import List


def natural_sort_key(path: Path):
    """
    Tạo khóa sắp xếp tự nhiên theo số học (Natural Sort / Human Sort).
    Ví dụ: chapter_1 -> chapter_2 -> chapter_10 -> chapter_100
    thay vì thứ tự từ điển: chapter_1 -> chapter_10 -> chapter_100 -> chapter_2
    """
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", path.name)
    ]


def natural_sort_paths(paths: List[Path]) -> List[Path]:
    """Sắp xếp danh sách đường dẫn theo thứ tự tự nhiên."""
    return sorted(paths, key=natural_sort_key)

