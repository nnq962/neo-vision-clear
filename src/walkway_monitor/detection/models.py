"""Các kiểu dữ liệu kết quả của pipeline detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class OccupancyState(Enum):
    """Trạng thái tức thời của lối đi tại một frame."""

    CLEAR = "clear"
    OCCUPIED = "occupied"


@dataclass(frozen=True)
class ComponentStats:
    """Thống kê connected component thay đổi lớn nhất trong ROI."""

    area: int
    bounding_box: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class WalkwayClearanceStats:
    """Thống kê bề rộng còn trống tại nút thắt của ROI."""

    minimum_free_width_ratio: float
    obstacle_width_ratio: float
    bottleneck_row: int | None
    bottleneck_span: tuple[int, int] | None


@dataclass(frozen=True)
class DetectionResult:
    """Kết quả phát hiện và các chỉ số debug của một frame."""

    state: OccupancyState
    width_blocked: bool
    largest_component_area: int
    bounding_box: tuple[int, int, int, int] | None
    largest_area_ratio: float
    changed_area_ratio: float
    minimum_free_width_ratio: float
    obstacle_width_ratio: float
    bottleneck_row: int | None
    bottleneck_span: tuple[int, int] | None
    alignment_scale: float
    alignment_shift: float
    alignment_inlier_ratio: float
    alignment_enabled: bool
    frame_index: int
    timestamp: float


@dataclass(frozen=True)
class DetectionOutput:
    """Kết quả detection cùng các mask dùng cho hiển thị và tuning."""

    result: DetectionResult
    raw_depth: np.ndarray
    aligned_depth: np.ndarray
    check_area_mask: np.ndarray
    changed_mask: np.ndarray
    normalized_difference: np.ndarray
    threshold_map: np.ndarray
