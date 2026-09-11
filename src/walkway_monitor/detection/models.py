"""Các kiểu dữ liệu đầu ra của quá trình phân tích lối đi."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RouteCapacity:
    """Kết quả đo khả năng đi xuyên suốt trên mặt phẳng BEV."""

    maximum_passable_width_meters: float
    walkway_width_meters: float
    bottleneck_y_meters: float
    bottleneck_free_x_ranges_meters: tuple[tuple[float, float], ...]
    bottleneck_world_span: tuple[float, float]
    bottleneck_row: int


@dataclass(frozen=True)
class CorridorSnapshot:
    """Dữ liệu nghiệp vụ gọn nhẹ có thể dùng để xuất cho robot."""

    maximum_passable_width_meters: float
    walkway_width_meters: float
    bottleneck_y_meters: float
    bottleneck_free_x_ranges_meters: tuple[tuple[float, float], ...]
    frame_index: int
    captured_at: float

    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """Chuyển snapshot thành cấu trúc thuần Python sẵn sàng mã hóa JSON."""
        # Giữ tên field ổn định và đổi tuple thành list để payload JSON rõ ràng.
        return {
            "maximum_passable_width_meters": self.maximum_passable_width_meters,
            "walkway_width_meters": self.walkway_width_meters,
            "bottleneck": {
                "y_meters": self.bottleneck_y_meters,
                "free_x_ranges_meters": [
                    [start, end]
                    for start, end in self.bottleneck_free_x_ranges_meters
                ],
            },
            "frame_index": self.frame_index,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class AnalysisDiagnostics:
    """Thông tin kỹ thuật chỉ phục vụ quan sát và tinh chỉnh nội bộ."""

    alignment_scale: float
    alignment_shift: float
    alignment_inlier_ratio: float
    alignment_enabled: bool


@dataclass(frozen=True)
class DetectionOutput:
    """Snapshot nghiệp vụ và các ảnh trung gian cần cho giao diện debug."""

    snapshot: CorridorSnapshot
    route_capacity: RouteCapacity
    diagnostics: AnalysisDiagnostics
    raw_depth: np.ndarray
    aligned_depth: np.ndarray
    check_area_mask: np.ndarray
    changed_mask: np.ndarray
