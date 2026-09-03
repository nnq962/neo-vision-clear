from __future__ import annotations

import time

import cv2
import numpy as np

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class WebcamReader(BaseReader):
    """Đọc frame liên tục từ MỘT webcam (device id)."""

    source_type = SourceType.WEBCAM
    is_stream = True

    def __init__(self, source: int):
        super().__init__(source)
        self._cap: cv2.VideoCapture | None = None
        self._fps = 0.0

    def open(self) -> "WebcamReader":
        device_id = self._source
        LOGGER.info("Mở webcam: device %d", device_id)
        # KHÔNG truyền open/read timeout: backend webcam (AVFOUNDATION/V4L2/DSHOW)
        # có thể từ chối param và fail mở camera. Timeout chỉ dùng cho RTSP/FFMPEG.
        cap = cv2.VideoCapture(device_id)
        if not cap.isOpened():
            cap.release()
            LOGGER.error("Không mở được webcam %d.", device_id)
            raise RuntimeError(f"Không mở được webcam {device_id}.")

        self._cap = cap
        self._fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_str = f"{self._fps:.1f} fps" if self._fps > 0 else "fps=unknown"
        LOGGER.info("  → WEBCAM | %dx%d | %s | is_stream=True", w, h, fps_str)
        self._opened = True
        self._frame_index = 0
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        self.ensure_open()
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            LOGGER.warning("Webcam %d mất tín hiệu.", self._source)
            return None

        frame = ensure_bgr(frame)
        h, w = frame.shape[:2]
        meta = SourceMeta(
            name=f"webcam_{self._source}",
            source_type=SourceType.WEBCAM,
            frame_index=self._frame_index,
            resolution=(w, h),
            fps=self._fps,
            is_stream=True,
            timestamp=time.time(),
        )
        self._frame_index += 1
        return frame, meta

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False
