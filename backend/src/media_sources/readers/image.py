from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class ImageReader(BaseReader):
    """Đọc MỘT ảnh từ file path hoặc numpy.ndarray. read() trả 1 lần rồi None."""

    source_type = SourceType.IMAGE
    is_stream = False

    def __init__(self, source):
        super().__init__(source)
        self._frame: np.ndarray | None = None
        self._meta: SourceMeta | None = None

    def open(self) -> "ImageReader":
        src = self._source
        if isinstance(src, np.ndarray):
            frame = ensure_bgr(src)
            name = "array"
        else:
            frame = cv2.imread(str(src))
            if frame is None:
                LOGGER.error("Không đọc được ảnh: %s", src)
                raise FileNotFoundError(f"Không đọc được ảnh: {src}")
            frame = ensure_bgr(frame)
            name = Path(str(src)).name

        h, w = frame.shape[:2]
        LOGGER.info("Nạp ảnh: %s | IMAGE | %dx%d | is_stream=False", name, w, h)
        self._frame = frame
        self._meta = SourceMeta(
            name=name,
            source_type=SourceType.IMAGE,
            frame_index=0,
            resolution=(w, h),
            timestamp=time.time(),
        )
        self._opened = True
        self._frame_index = 0
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        self.ensure_open()
        if self._frame is None or self._frame_index > 0:
            return None
        self._frame_index += 1
        return self._frame, self._meta

    def close(self) -> None:
        self._frame = None
        self._meta = None
        self._opened = False
