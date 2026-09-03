from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

import numpy as np

from .batch import StreamBatchReader, SyncBatchReader, _BaseBatch
from .detector import _classify_one, detect_source_type
from .models import SourceType
from .readers.base import BaseReader
from .readers.image import ImageReader
from .readers.rtsp import RtspReader
from .readers.video import VideoReader
from .readers.webcam import WebcamReader
from .readers.youtube import YoutubeReader
from .utils import LOGGER

# ─────────────────────────────────────────────────────────────────────────────

_READER_MAP: dict[SourceType, type[BaseReader]] = {
    SourceType.IMAGE: ImageReader,
    SourceType.VIDEO: VideoReader,
    SourceType.WEBCAM: WebcamReader,
    SourceType.RTSP: RtspReader,
    SourceType.YOUTUBE: YoutubeReader,
}


def create_media_source(sources, **kwargs) -> BaseReader | _BaseBatch:
    """Tạo reader phù hợp theo loại nguồn (KHÔNG kết nối — lazy, mở khi open()/vào context).

    - Nguồn đơn (str/int/ndarray) → BaseReader con (dùng open/read/close độc lập).
    - List nguồn → batch đồng nhất (detect_source_type validate), gói trong:
        • StreamBatchReader nếu reader là stream (rtsp/webcam) — latest-frame realtime.
        • SyncBatchReader nếu tuần tự (image/video/youtube) — lockstep, không drop frame.

    kwargs dư thừa với constructor của reader sẽ bị lọc bỏ (log DEBUG) — xem _reader_kwargs.
    """
    if _is_sequence(sources):
        items = list(sources)
        if not items:
            raise ValueError("Danh sách sources không được rỗng.")
        source_type = detect_source_type(items)
        reader_cls = _READER_MAP[source_type]
        reader_kwargs = _reader_kwargs(reader_cls, kwargs)
        readers = [reader_cls(item, **reader_kwargs) for item in items]
        batch_cls = StreamBatchReader if reader_cls.is_stream else SyncBatchReader
        return batch_cls(readers)

    source_type = _classify_one(sources)
    reader_cls = _READER_MAP[source_type]
    return reader_cls(sources, **_reader_kwargs(reader_cls, kwargs))


# ─────────────────────────────────────────────────────────────────────────────


def _is_sequence(value: Any) -> bool:
    """True nếu là list nhiều nguồn — loại trừ str/bytes/ndarray (đều là nguồn đơn)."""
    return isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, np.ndarray))


def _reader_kwargs(reader_cls: type[BaseReader], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Chỉ giữ các kwargs mà constructor của reader chấp nhận; phần dư log DEBUG."""
    parameters = inspect.signature(reader_cls.__init__).parameters
    accepted = {
        name
        for name, parameter in parameters.items()
        if name not in {"self", "source"}
        and parameter.kind in {parameter.KEYWORD_ONLY, parameter.POSITIONAL_OR_KEYWORD}
    }
    selected = {name: value for name, value in kwargs.items() if name in accepted}
    ignored = sorted(set(kwargs) - set(selected))
    if ignored:
        LOGGER.debug("Bỏ qua kwargs không áp dụng cho %s: %s", reader_cls.__name__, ignored)
    return selected
