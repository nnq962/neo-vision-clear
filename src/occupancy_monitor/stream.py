"""Mở nguồn video và đọc frame ổn định."""

from __future__ import annotations

import time

import numpy as np
from media_sources import BaseReader, create_media_source


def open_stream(source: str) -> BaseReader:
    """Tạo và mở reader phù hợp thông qua package media-sources."""
    parsed_source: str | int = int(source) if source.isdigit() else source
    reader = create_media_source(
        parsed_source,
        use_gstreamer=True,
        reconnect=True,
        reconnect_forever=True,
    )
    if not isinstance(reader, BaseReader):
        raise RuntimeError("Ứng dụng chỉ hỗ trợ một nguồn camera tại một thời điểm.")
    reader.open()
    return reader


# ─────────────────────────────────────────────────────────────────────────────
def read_frame(reader: BaseReader, retries: int = 30) -> np.ndarray:
    """Đọc một frame hợp lệ và thử lại ngắn hạn khi nguồn bị gián đoạn."""
    for _ in range(retries):
        result = reader.read()
        if result is not None:
            frame, _metadata = result
            return frame
        time.sleep(0.1)
    raise RuntimeError("Không đọc được frame từ camera.")
