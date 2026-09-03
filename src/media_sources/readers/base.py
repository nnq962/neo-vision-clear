from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..models import SourceMeta, SourceType

# ─────────────────────────────────────────────────────────────────────────────


class BaseReader(ABC):
    """Abstract base cho reader đơn nguồn (một source) với vòng đời open/read/close.

    Mỗi reader xử lý ĐÚNG một nguồn media. Batch nhiều nguồn do orchestrator trong
    `batch.py` đảm nhiệm (gói N reader lại). Reader connect lazy — `__init__` chỉ lưu
    state, kết nối thật xảy ra ở `open()` (hoặc tự gọi qua `ensure_open()`).

    Subclass khai báo:
      - `source_type`: loại nguồn (SourceType) để gắn vào SourceMeta.
      - `is_stream`: True nếu là stream liên tục (rtsp/webcam) → batch dùng chiến lược
        latest-frame; False nếu đọc tuần tự (image/video) → batch dùng lockstep.
    """

    source_type: SourceType
    is_stream: bool = False

    def __init__(self, source):
        self._source = source
        self._opened = False
        self._frame_index = 0

    # ─── thuộc tính ────────────────────────────────────────────────────────────

    @property
    def source(self):
        """Nguồn gốc truyền vào reader."""
        return self._source

    @property
    def opened(self) -> bool:
        """Reader đã mở kết nối hay chưa."""
        return self._opened

    # ─── vòng đời ──────────────────────────────────────────────────────────────

    @abstractmethod
    def open(self) -> "BaseReader":
        """Mở nguồn, nạp metadata. Trả về self để hỗ trợ `reader.open()` fluent."""
        ...

    @abstractmethod
    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Đọc một frame. Trả về (frame, meta) hoặc None khi nguồn kết thúc/mất tín hiệu."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Giải phóng tài nguyên và đánh dấu reader đã đóng."""
        ...

    def ensure_open(self) -> None:
        """Mở nguồn nếu chưa mở (idempotent)."""
        if not self._opened:
            self.open()

    def request_stop(self) -> None:
        """Tín hiệu cho read() đang block (vd reconnect) thoát ra sớm — KHÔNG release tài nguyên.

        Mặc định no-op; reader có vòng reconnect/chờ dài (RTSP) override để set stop-event.
        Dùng bởi batch orchestrator để dừng nhanh mà tránh race release-trong-khi-read().
        """

    # ─── iterator / context manager ──────────────────────────────────────────

    def __iter__(self):
        return self

    def __next__(self) -> tuple[np.ndarray, SourceMeta]:
        self.ensure_open()
        result = self.read()
        if result is None:
            raise StopIteration
        return result

    def __enter__(self) -> "BaseReader":
        self.ensure_open()
        return self

    def __exit__(self, *args) -> None:
        self.close()
