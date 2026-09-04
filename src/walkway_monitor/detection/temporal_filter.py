"""Bộ lọc thời gian chống thay đổi trạng thái bởi một vài frame nhiễu."""

from __future__ import annotations

from walkway_monitor.detection.models import OccupancyState


class TemporalOccupancyFilter:
    """Xác nhận CLEAR và OCCUPIED bằng số frame liên tiếp cấu hình."""

    def __init__(self, occupied_frames: int, clear_frames: int):
        """Khởi tạo bộ đếm và trạng thái UNKNOWN ban đầu."""
        if occupied_frames < 1 or clear_frames < 1:
            raise ValueError("Số frame xác nhận phải lớn hơn hoặc bằng 1.")
        self._occupied_frames = occupied_frames
        self._clear_frames = clear_frames
        self._occupied_count = 0
        self._clear_count = 0
        self._state = OccupancyState.UNKNOWN

    # ─────────────────────────────────────────────────────────────────────────

    @property
    def state(self) -> OccupancyState:
        """Trả về trạng thái ổn định hiện tại."""
        return self._state

    # ─────────────────────────────────────────────────────────────────────────

    def update(self, raw_occupied: bool, valid: bool = True) -> OccupancyState:
        """Cập nhật bộ đếm từ kết quả thô và trả về trạng thái ổn định mới."""
        if not valid:
            self.reset()
            return self._state
        if raw_occupied:
            self._occupied_count += 1
            self._clear_count = 0
            if self._occupied_count >= self._occupied_frames:
                self._state = OccupancyState.OCCUPIED
        else:
            self._clear_count += 1
            self._occupied_count = 0
            if self._clear_count >= self._clear_frames:
                self._state = OccupancyState.CLEAR
        return self._state

    # ─────────────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Xóa các bộ đếm và đưa trạng thái về UNKNOWN."""
        self._occupied_count = 0
        self._clear_count = 0
        self._state = OccupancyState.UNKNOWN
