from dataclasses import dataclass
from enum import Enum, auto


class SourceType(Enum):
    IMAGE = auto()
    VIDEO = auto()
    WEBCAM = auto()
    RTSP = auto()
    YOUTUBE = auto()


@dataclass
class SourceMeta:
    name: str
    source_type: SourceType
    frame_index: int
    resolution: tuple[int, int]     # (width, height)
    fps: float | None = None
    total_frames: int | None = None # chỉ có với VIDEO
    is_stream: bool = False
    timestamp: float = 0.0
