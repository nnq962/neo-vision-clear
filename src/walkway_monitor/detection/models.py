"""Các kiểu dữ liệu kết quả của pipeline detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class OccupancyState(Enum):
    """Trạng thái ổn định của lối đi tại một thời điểm."""

    UNKNOWN = "unknown"
    CLEAR = "clear"
    OCCUPIED = "occupied"


@dataclass(frozen=True)
class ComponentStats:
    """Thống kê connected component thay đổi lớn nhất trong ROI."""

    area: int
    bounding_box: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class DetectionResult:
    """Kết quả phát hiện và các chỉ số debug của một frame."""

    state: OccupancyState
    raw_occupied: bool
    largest_component_area: int
    bounding_box: tuple[int, int, int, int] | None
    largest_area_ratio: float
    changed_area_ratio: float
    outside_change_ratio: float
    alignment_scale: float
    alignment_shift: float
    frame_index: int
    timestamp: float
    reason: str | None = None


@dataclass(frozen=True)
class DetectionOutput:
    """Kết quả detection cùng các mask dùng cho hiển thị và tuning."""

    result: DetectionResult
    aligned_depth: np.ndarray
    changed_mask: np.ndarray
    normalized_difference: np.ndarray
    threshold_map: np.ndarray
