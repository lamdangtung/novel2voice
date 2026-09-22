import csv
from pathlib import Path
from typing import Dict, List, Optional


class Glossary:
    """
    Quản lý bảng thuật ngữ / tên riêng (glossary.csv) để đồng bộ hóa bản dịch.
    """

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path
        self.entries: Dict[str, str] = {}
        if self.file_path and self.file_path.is_file():
            self.load()

    def load(self) -> Dict[str, str]:
        self.entries.clear()
        if not self.file_path or not self.file_path.exists():
            return self.entries

        try:
            with open(self.file_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or len(row) < 2:
                        continue
                    en_term = row[0].strip()
                    vi_term = row[1].strip()
                    # Bỏ qua dòng tiêu đề nếu có
                    if en_term.lower() == "en" and vi_term.lower() == "vi":
                        continue
                    if en_term and vi_term:
                        self.entries[en_term] = vi_term
        except Exception as e:
            print(f"[Warning] Không thể đọc glossary từ {self.file_path}: {e}")

        return self.entries

    def to_prompt_instruction(self) -> str:
        """
        Tạo đoạn hướng dẫn thuật ngữ để đưa vào system prompt của LLM.
        """
        if not self.entries:
            return ""

        lines = ["Bắt buộc tuân thủ bảng dịch tên riêng và thuật ngữ sau đây:"]
        for en, vi in self.entries.items():
            lines.append(f"- \"{en}\" -> \"{vi}\"")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return len(self.entries) == 0

