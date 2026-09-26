"""Các kiểu dữ liệu đầu ra của quá trình phân tích lối đi."""

from __future__ import annotations

from dataclasses import dataclass, field

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
class ClearanceZone:
    """Mức chiếm dụng tổng hợp của một đoạn dọc trên raster BEV."""

    index: int
    name: str
    start_ratio: float
    end_ratio: float
    free_ratio: float
    occupancy_ratio: float
    walkway_width_meters: float
    occupied_width_meters: float
    free_width_meters: float
    blocked: bool
    camera_polygon: tuple[tuple[float, float], ...] = ()

    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """Chuyển phép đo một đoạn thành payload thuần Python."""
        return {
            "index": self.index,
            "name": self.name,
            "start_ratio": self.start_ratio,
            "end_ratio": self.end_ratio,
            "free_ratio": self.free_ratio,
            "occupancy_ratio": self.occupancy_ratio,
            "walkway_width_meters": self.walkway_width_meters,
            "occupied_width_meters": self.occupied_width_meters,
            "free_width_meters": self.free_width_meters,
            "blocked": self.blocked,
            "camera_polygon": [list(point) for point in self.camera_polygon],
        }


@dataclass(frozen=True)
class ZoneClearance:
    """Kết quả đánh giá toàn hành lang theo các đoạn BEV liên tiếp."""

    zones: tuple[ClearanceZone, ...] = ()
    maximum_occupancy_ratio: float = 0.0
    maximum_allowed_occupancy_ratio: float = 0.4
    blocked_zone_indices: tuple[int, ...] = ()
    can_pass: bool = True

    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """Chuyển kết quả theo đoạn thành cấu trúc sẵn sàng mã hóa JSON."""
        return {
            "zones": [zone.to_dict() for zone in self.zones],
            "maximum_occupancy_ratio": self.maximum_occupancy_ratio,
            "maximum_allowed_occupancy_ratio": (
                self.maximum_allowed_occupancy_ratio
            ),
            "blocked_zone_indices": list(self.blocked_zone_indices),
            "can_pass": self.can_pass,
        }


@dataclass(frozen=True)
class CorridorSnapshot:
    """Dữ liệu nghiệp vụ gọn nhẹ có thể dùng để xuất cho robot."""

    maximum_passable_width_meters: float
    walkway_width_meters: float
    bottleneck_y_meters: float
    bottleneck_free_x_ranges_meters: tuple[tuple[float, float], ...]
    frame_index: int
    captured_at: float
    zone_clearance: ZoneClearance = field(default_factory=ZoneClearance)

    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """Chuyển snapshot thành cấu trúc thuần Python sẵn sàng mã hóa JSON."""
        # Giữ tên field ổn định và đổi tuple thành list để payload JSON rõ ràng.
        payload = {
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
        payload.update(self.zone_clearance.to_dict())
        return payload


@dataclass(frozen=True)
class AnalysisDiagnostics:
    """Thông tin kỹ thuật chỉ phục vụ quan sát và tinh chỉnh nội bộ."""

    alignment_scale: float
    alignment_shift: float
    alignment_inlier_ratio: float
    alignment_enabled: bool


@dataclass(frozen=True)
class AnalysisTimings:
    """Thời gian các nhóm xử lý chính của analyzer tính theo giây."""

    total_seconds: float
    alignment_seconds: float
    mask_seconds: float
    bev_seconds: float


@dataclass(frozen=True)
class DetectionOutput:
    """Snapshot nghiệp vụ và các ảnh trung gian cần cho giao diện debug."""

    snapshot: CorridorSnapshot
    route_capacity: RouteCapacity
    zone_clearance: ZoneClearance
    diagnostics: AnalysisDiagnostics
    timings: AnalysisTimings
    raw_depth: np.ndarray
    aligned_depth: np.ndarray
    check_area_mask: np.ndarray
    changed_mask: np.ndarray
