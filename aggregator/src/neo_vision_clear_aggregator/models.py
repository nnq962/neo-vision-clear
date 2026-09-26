"""Schema ingest, trạng thái và quyết định hành lang của Aggregator."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


CameraState = Literal["pass", "blocked", "warming_up", "error"]


class CameraMeasurement(BaseModel):
    """Payload chính thức do một Jetson gửi cho một camera."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal[1]
    camera_id: str = Field(min_length=1, max_length=100)
    camera_name: str = Field(min_length=1, max_length=100)
    state: CameraState
    zone_count: Optional[int] = Field(default=None, ge=1, le=100)
    blocked_zones: List[int] = Field(default_factory=list)
    minimum_free_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_passable_width_cm: Optional[float] = Field(default=None, ge=0.0)
    reason: Optional[str] = Field(default=None, min_length=1, max_length=100)
    observed_at: datetime

    @model_validator(mode="after")
    def validate_state_fields(self) -> "CameraMeasurement":
        """Kiểm tra các field đo tương thích với trạng thái camera."""
        # Bước 1: kết quả pass/blocked phải có số đo dùng để Aggregator quyết định.
        if self.state in ("pass", "blocked"):
            if self.zone_count is None or self.max_passable_width_cm is None:
                raise ValueError(
                    "state pass/blocked cần zone_count và max_passable_width_cm."
                )
        if self.zone_count is not None and any(
            zone < 1 or zone > self.zone_count for zone in self.blocked_zones
        ):
            raise ValueError("blocked_zones phải nằm trong [1, zone_count].")
        if len(self.blocked_zones) != len(set(self.blocked_zones)):
            raise ValueError("blocked_zones không được chứa giá trị trùng.")
        return self


class HealthResponse(BaseModel):
    """Trạng thái process cùng số nguồn và camera đã cấu hình."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    service: str = "neo-vision-clear-aggregator"
    connected_sources: int = Field(ge=0)
    known_sources: int = Field(ge=0)
    configured_cameras: int = Field(ge=0)
    received_messages: int = Field(ge=0)


class SourceStatus(BaseModel):
    """Metadata kết nối của một Jetson source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    connected: bool
    connection_count: int = Field(ge=0)
    message_count: int = Field(ge=0)
    connected_at: Optional[float] = None
    last_received_at: Optional[float] = None
    age_ms: Optional[int] = Field(default=None, ge=0)
    stale: bool


class LatestPayloadResponse(BaseModel):
    """Payload hợp lệ mới nhất của một Jetson dùng để chẩn đoán."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    received_at: float
    payload: CameraMeasurement


class CameraStatus(BaseModel):
    """Trạng thái mới nhất của camera sau khi join với cấu hình vị trí."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str
    camera_name: Optional[str] = None
    source_id: str
    order: int
    location_name: str
    state: Optional[CameraState] = None
    age_ms: Optional[int] = Field(default=None, ge=0)
    stale: bool
    blocked_zones: List[int] = Field(default_factory=list)
    minimum_free_ratio: Optional[float] = None
    max_passable_width_cm: Optional[float] = None
    observed_at: Optional[datetime] = None


class BlockedArea(BaseModel):
    """Một vùng camera khiến toàn hành lang không thể đi qua."""

    model_config = ConfigDict(extra="forbid")

    order: int
    location_name: str
    camera_id: str
    camera_name: str
    blocked_zones: List[int]
    zone_count: int
    minimum_free_ratio: Optional[float] = None
    max_passable_width_cm: float
    reason: str
    source: str
    observed_at: datetime


class UnavailableCamera(BaseModel):
    """Camera chưa có dữ liệu tin cậy để kết luận hành lang thông."""

    model_config = ConfigDict(extra="forbid")

    order: int
    location_name: str
    camera_id: str
    camera_name: Optional[str] = None
    reason: str
    source: str


class CorridorDecision(BaseModel):
    """Kết luận tổng hợp được gửi từ Aggregator tới WS server."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    corridor_id: str
    corridor_name: str
    state: Literal["pass", "blocked", "unknown"]
    can_pass: Optional[bool]
    required_width_cm: float
    blocked_areas: List[BlockedArea] = Field(default_factory=list)
    unavailable_cameras: List[UnavailableCamera] = Field(default_factory=list)
    decided_at: datetime


class OutboundStatus(BaseModel):
    """Trạng thái kết nối và message gần nhất gửi tới server đích."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    websocket_url: Optional[str] = None
    connected: bool
    queued_messages: int = Field(ge=0)
    sent_messages: int = Field(ge=0)
    last_sent_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    last_payload: Optional[CorridorDecision] = None


class DashboardResponse(BaseModel):
    """Ảnh chụp trạng thái đầy đủ cho frontend bằng một request."""

    model_config = ConfigDict(extra="forbid")

    health: HealthResponse
    sources: List[SourceStatus]
    cameras: List[CameraStatus]
    decision: CorridorDecision
    latest_received: List[LatestPayloadResponse]
    outbound: OutboundStatus
