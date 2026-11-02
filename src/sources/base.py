"""Website-independent source contract."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Chapter:
    source: str
    book_id: str
    chapter_id: str
    title: str
    text: str
    url: str
    language: str
    next_url: str | None = None


class NovelSource(Protocol):
    def supports(self, url: str) -> bool:
        ...

    def fetch_chapter(self, url: str) -> Chapter:
        ...

    def close(self) -> None:
        ...
