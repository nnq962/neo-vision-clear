from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class VideoReader(BaseReader):
    """Đọc frame tuần tự từ MỘT video file. Lặp đến hết file rồi trả None.

    Decode song song nhiều video (nếu chạy theo batch) do SyncBatchReader đảm nhiệm —
    reader này chỉ lo một file, đọc lockstep từng frame, KHÔNG drop.
    """

    source_type = SourceType.VIDEO
    is_stream = False

    def __init__(self, source):
        super().__init__(str(source))
        self._cap: cv2.VideoCapture | None = None
        self._fps = 0.0
        self._total_frames = 0
        self._name = Path(str(source)).name

    def _capture_target(self) -> str:
        """URL/path thực sự để mở VideoCapture. YoutubeReader override trả stream URL đã resolve."""
        return self._source

    def open(self) -> "VideoReader":
        LOGGER.info("Mở video: %s", self._source)
        cap = cv2.VideoCapture(self._capture_target())
        if not cap.isOpened():
            cap.release()
            LOGGER.error("Không mở được video: %s", self._source)
            raise FileNotFoundError(f"Không mở được video: {self._source}")

        self._cap = cap
        self._fps = cap.get(cv2.CAP_PROP_FPS)
        self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if self._fps <= 0:
            LOGGER.warning("FPS không đọc được từ video: %s", self._source)
        if self._total_frames <= 0:
            LOGGER.warning("Số frame không đọc được từ video: %s", self._source)
        LOGGER.info("  → VIDEO | %dx%d | %.1f fps | %d frames | is_stream=False",
                    w, h, self._fps, self._total_frames)
        self._opened = True
        self._frame_index = 0
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        self.ensure_open()
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            LOGGER.info("Video kết thúc: %s", self._source)
            return None

        frame = ensure_bgr(frame)
        meta = self._build_meta(frame)
        self._frame_index += 1
        return frame, meta

    def _build_meta(self, frame: np.ndarray) -> SourceMeta:
        h, w = frame.shape[:2]
        return SourceMeta(
            name=self._name,
            source_type=SourceType.VIDEO,
            frame_index=self._frame_index,
            resolution=(w, h),
            fps=self._fps,
            total_frames=self._total_frames,
            timestamp=time.time(),
        )

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False
