"""Optional progress events shared by CLI, remote control and pipeline stages."""
import logging
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    current: float
    total: float
    unit: str = ''


ProgressCallback = Callable[[ProgressEvent], None]


def emit(callback, stage, current, total, unit=''):
    if callback is not None:
        try:
            callback(ProgressEvent(stage, current, total, unit))
        except Exception:
            logging.getLogger(__name__).warning('Không ghi được tiến độ; pipeline vẫn tiếp tục.')
