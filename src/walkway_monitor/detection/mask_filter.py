"""Lọc mask thay đổi theo thời gian để loại các pixel nhấp nháy ngắn hạn."""

from __future__ import annotations

from collections import deque

import numpy as np


class TemporalMaskFilter:
    """Giữ pixel chỉ khi nó xuất hiện đủ số lần trong cửa sổ frame gần nhất."""

    def __init__(self, window_size: int, required_frames: int):
        """Khởi tạo cửa sổ voting với số frame yêu cầu hợp lệ."""
        if window_size < 1:
            raise ValueError("window_size phải lớn hơn hoặc bằng 1.")
        if not 1 <= required_frames <= window_size:
            raise ValueError("required_frames phải nằm trong [1, window_size].")
        self._window_size = window_size
        self._required_frames = required_frames
        self._history: deque[np.ndarray] = deque(maxlen=window_size)

    # ─────────────────────────────────────────────────────────────────────────

    def update(self, mask: np.ndarray) -> np.ndarray:
        """Cập nhật voting và trả mask uint8 ổn định theo thời gian."""
        if mask.ndim != 2:
            raise ValueError("Mask phải là mảng hai chiều.")
        binary = (mask > 0).astype(np.uint8)
        self._history.append(binary)
        if len(self._history) < self._required_frames:
            return np.zeros_like(binary, dtype=np.uint8)
        votes = np.sum(np.stack(tuple(self._history), axis=0), axis=0)
        return (votes >= self._required_frames).astype(np.uint8) * 255

    # ─────────────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Xóa toàn bộ lịch sử mask đã tích lũy."""
        self._history.clear()
