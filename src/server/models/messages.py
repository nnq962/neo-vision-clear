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


class CorridorInfoRequest(SnapshotRequest):
    """Yêu cầu lấy thông tin mới nhất của hành lang đang quan sát."""

    type: Literal["get_corridor_info"]


class BottleneckPayload(BaseModel):
    """Vị trí và các khoảng trống theo X tại nút thắt."""

    y_meters: float
    free_x_ranges_meters: list[tuple[float, float]]


class CorridorInfoData(BaseModel):
    """Các phép đo hành lang được gửi cho robot."""

    maximum_passable_width_meters: float
    walkway_width_meters: float
    bottleneck: BottleneckPayload
    frame_index: int
    captured_at: float

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_snapshot(cls, snapshot: CorridorSnapshot) -> "CorridorInfoData":
        """Chuyển snapshot miền nghiệp vụ thành schema response API."""
        # Dùng payload thuần Python của snapshot để tránh rò rỉ kiểu numpy.
        return cls.model_validate(snapshot.to_dict())


class SnapshotResponse(BaseModel):
    """Các trường trạng thái chung của phản hồi snapshot WebSocket."""

    request_id: str
    status: Literal["ok", "warming_up", "stale", "error"]
    age_ms: int | None = None
    error: str | None = None


class CorridorInfoResponse(SnapshotResponse):
    """Phản hồi phép đo cùng trạng thái độ mới của snapshot."""

    type: Literal["corridor_info"] = "corridor_info"
    data: CorridorInfoData | None = None


class OverviewInfoRequest(SnapshotRequest):
    """Yêu cầu snapshot visualization mới nhất dành cho frontend."""

    type: Literal["get_overview_info"]


class DifferenceZonePayload(BaseModel):
    """Polygon sai khác chuẩn hóa cùng tỷ lệ diện tích trên toàn frame."""

    polygon: list[NormalizedPoint] = Field(min_length=3, max_length=32)
    area_ratio: float = Field(ge=0.0, le=1.0)


class OverviewInfoData(CorridorInfoData):
    """Dữ liệu số đo mở rộng thêm zone phục vụ overlay video."""

    changed_zones: list[DifferenceZonePayload]

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_snapshot(
        cls,
        snapshot: CorridorSnapshot,
        zones: tuple[DifferenceZone, ...],
    ) -> "OverviewInfoData":
        """Ghép snapshot robot với polygon visualization thuần JSON."""
        # Bước 1: tái sử dụng ánh xạ số đo và chỉ thêm payload zone đã giới hạn.
        payload = CorridorInfoData.from_snapshot(snapshot).model_dump()
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
