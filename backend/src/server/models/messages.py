"""Schema request và response của giao thức WebSocket."""

from __future__ import annotations

from typing import Literal, Tuple

from typing_extensions import Annotated

from pydantic import BaseModel, ConfigDict, Field

from walkway_monitor.detection.models import CorridorSnapshot
from walkway_monitor.detection.zones import DifferenceZone


NormalizedCoordinate = Annotated[float, Field(ge=0.0, le=1.0)]
NormalizedPoint = Tuple[NormalizedCoordinate, NormalizedCoordinate]


class SnapshotRequest(BaseModel):
    """Các trường chung của yêu cầu đọc snapshot qua WebSocket."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=64)


class BottleneckPayload(BaseModel):
    """Vị trí và các khoảng trống theo X tại nút thắt."""

    y_meters: float
    free_x_ranges_meters: list[tuple[float, float]]


class ClearanceZonePayload(BaseModel):
    """Phép đo chiếm dụng tổng hợp của một đoạn hành lang trên BEV."""

    index: int = Field(ge=1)
    name: str
    start_ratio: float = Field(ge=0.0, le=1.0)
    end_ratio: float = Field(ge=0.0, le=1.0)
    free_ratio: float = Field(ge=0.0, le=1.0)
    occupancy_ratio: float = Field(ge=0.0, le=1.0)
    walkway_width_meters: float = Field(ge=0.0)
    occupied_width_meters: float = Field(ge=0.0)
    free_width_meters: float = Field(ge=0.0)
    blocked: bool


class OverviewClearanceZonePayload(ClearanceZonePayload):
    """Phép đo một đoạn kèm polygon đã chiếu về ảnh camera."""

    camera_polygon: list[NormalizedPoint] = Field(max_length=8)


class CorridorInfoData(BaseModel):
    """Các phép đo hành lang được gửi cho robot."""

    maximum_passable_width_meters: float
    walkway_width_meters: float
    bottleneck: BottleneckPayload
    zones: list[ClearanceZonePayload]
    maximum_occupancy_ratio: float = Field(ge=0.0, le=1.0)
    maximum_allowed_occupancy_ratio: float = Field(ge=0.0, le=1.0)
    blocked_zone_indices: list[int]
    can_pass: bool
    frame_index: int
    captured_at: float

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_snapshot(cls, snapshot: CorridorSnapshot) -> "CorridorInfoData":
        """Chuyển snapshot miền nghiệp vụ thành schema response API."""
        # Dùng payload thuần Python của snapshot để tránh rò rỉ kiểu numpy.
        return cls.model_validate(snapshot.to_dict())


class OverviewInfoRequest(SnapshotRequest):
    """Yêu cầu snapshot visualization mới nhất dành cho frontend."""

    type: Literal["get_overview_info"]


class DifferenceZonePayload(BaseModel):
    """Polygon sai khác chuẩn hóa cùng tỷ lệ diện tích trên toàn frame."""

    polygon: list[NormalizedPoint] = Field(min_length=3, max_length=32)
    area_ratio: float = Field(ge=0.0, le=1.0)


class OverviewInfoData(CorridorInfoData):
    """Dữ liệu số đo mở rộng thêm zone phục vụ overlay video."""

    zones: list[OverviewClearanceZonePayload]
    changed_zones: list[DifferenceZonePayload]

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_snapshot(
        cls,
        snapshot: CorridorSnapshot,
        zones: tuple[DifferenceZone, ...],
    ) -> "OverviewInfoData":
        """Ghép snapshot robot với polygon visualization thuần JSON."""
        # Bước 1: dùng payload gốc để giữ camera_polygon chỉ dành cho overview;
        # schema corridor vẫn bỏ field visualization này khỏi API robot.
        payload = snapshot.to_dict()
        payload["changed_zones"] = [
            {
                "polygon": list(zone.polygon),
                "area_ratio": zone.area_ratio,
            }
            for zone in zones
        ]
        return cls.model_validate(payload)


class OverviewCameraInfo(BaseModel):
    """Snapshot và trạng thái mới nhất của một baseline trong batch."""

    baseline_id: str
    status: Literal["ok", "warming_up", "stale", "error"]
    age_ms: int | None = None
    error: str | None = None
    data: OverviewInfoData | None = None


class OverviewInfoResponse(BaseModel):
    """Phản hồi WebSocket dashboard chứa kết quả mọi camera runtime."""

    type: Literal["overview_info"] = "overview_info"
    request_id: str
    items: list[OverviewCameraInfo]


class ProtocolErrorResponse(BaseModel):
    """Phản hồi khi message đầu vào không đúng schema giao thức."""

    type: Literal["error"] = "error"
    request_id: str | None = None
    code: Literal["invalid_message"] = "invalid_message"
    error: str
