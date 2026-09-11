"""Schema request và response của giao thức WebSocket."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from walkway_monitor.detection.models import CorridorSnapshot


class CorridorInfoRequest(BaseModel):
    """Yêu cầu lấy thông tin mới nhất của hành lang đang quan sát."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["get_corridor_info"]
    request_id: str = Field(min_length=1, max_length=64)


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


class CorridorInfoResponse(BaseModel):
    """Phản hồi phép đo cùng trạng thái độ mới của snapshot."""

    type: Literal["corridor_info"] = "corridor_info"
    request_id: str
    status: Literal["ok", "warming_up", "stale", "error"]
    age_ms: int | None = None
    data: CorridorInfoData | None = None
    error: str | None = None


class ProtocolErrorResponse(BaseModel):
    """Phản hồi khi message đầu vào không đúng schema giao thức."""

    type: Literal["error"] = "error"
    request_id: str | None = None
    code: Literal["invalid_message"] = "invalid_message"
    error: str
