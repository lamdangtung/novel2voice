"""Publishing contracts independent of transport and credentials."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class UploadSpec:
    video: Path
    title: str
    channel_id: str
    description: str = ''
    privacy: str = 'private'
    tags: tuple[str, ...] = ()
    category_id: str = '22'
    made_for_kids: bool = False
    thumbnail: Path | None = None
    default_language: str | None = None
    default_audio_language: str | None = None
    contains_synthetic_media: bool | None = None
    notify_subscribers: bool = True
    publish_at: str | None = None


@dataclass(frozen=True)
class UploadProgress:
    offset: int = 0
    video_id: str | None = None
    privacy: str | None = None


@dataclass(frozen=True)
class PublishedVideo:
    video_id: str
    url: str
    channel_id: str


class UploadLimitExceeded(RuntimeError):
    """Channel upload allowance exhausted; not a resumable-session failure."""
    pass


class RetryableUploadError(RuntimeError):
    pass


class VideoPublisher(Protocol):
    def channel_id(self) -> str: ...
    def start(self, spec: UploadSpec, size: int) -> str: ...
    def query(self, session: str, size: int) -> UploadProgress: ...
    def send(self, session: str, data: bytes, offset: int, size: int) -> UploadProgress: ...
    def set_thumbnail(self, video_id: str, thumbnail: Path) -> None: ...
    def close(self) -> None: ...
