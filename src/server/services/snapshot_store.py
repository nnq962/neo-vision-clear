"""Kho snapshot thread-safe nằm giữa worker camera và FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Literal

from walkway_monitor.detection.models import CorridorSnapshot


@dataclass(frozen=True)
class SnapshotRead:
    """Kết quả đọc snapshot cùng trạng thái vận hành hiện tại."""

    status: Literal["ok", "warming_up", "stale", "error"]
    snapshot: CorridorSnapshot | None
    age_ms: int | None
    error: str | None


class SnapshotStore:
    """Lưu atomically snapshot mới nhất để nhiều request có thể cùng đọc."""

    # ─────────────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        """Khởi tạo store ở trạng thái chờ frame đầu tiên."""
        self._snapshot: CorridorSnapshot | None = None
        self._published_at: float | None = None
        self._error: str | None = None
        self._lock = threading.Lock()

    # ─────────────────────────────────────────────────────────────────────────

    def publish(self, snapshot: CorridorSnapshot) -> None:
        """Thay thế snapshot hiện tại và xóa lỗi worker cũ."""
        # Dùng monotonic cho phép đo tuổi dữ liệu, không phụ thuộc chỉnh đồng hồ.
        with self._lock:
            self._snapshot = snapshot
            self._published_at = time.monotonic()
            self._error = None

    # ─────────────────────────────────────────────────────────────────────────

    def set_error(self, error: str) -> None:
        """Ghi lỗi vận hành mới nhất của worker camera."""
        with self._lock:
            self._error = error.strip() or "Lỗi worker không xác định."

    # ─────────────────────────────────────────────────────────────────────────

    def read(self, maximum_age_seconds: float) -> SnapshotRead:
        """Đọc snapshot và phân loại ok, stale, warming_up hoặc error."""
        if maximum_age_seconds <= 0:
            raise ValueError("maximum_age_seconds phải là số dương.")

        # Bước 1: sao chép state dưới lock rồi tính tuổi ở ngoài critical section.
        with self._lock:
            snapshot = self._snapshot
            published_at = self._published_at
            error = self._error
        if snapshot is None:
            status = "error" if error is not None else "warming_up"
            return SnapshotRead(status, None, None, error)

        # Bước 2: lỗi worker ưu tiên hơn tuổi dữ liệu; vẫn trả snapshot cuối để
        # phía nhận có dữ liệu chẩn đoán nhưng không được xem status là ok.
        age_seconds = max(time.monotonic() - float(published_at), 0.0)
        age_ms = int(round(age_seconds * 1000))
        if error is not None:
            return SnapshotRead("error", snapshot, age_ms, error)
        status = "stale" if age_seconds > maximum_age_seconds else "ok"
        return SnapshotRead(status, snapshot, age_ms, None)
