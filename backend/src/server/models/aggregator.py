"""Schema message một chiều từ Jetson tới Aggregator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.models.camera import CameraConfig
from walkway_monitor.detection.models import CorridorSnapshot


class ZoneOccupancyMeasurement(BaseModel):
    """Mức chiếm dụng và bề rộng tương đương của một zone BEV."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1, le=100)
    occupancy_ratio: float = Field(ge=0.0, le=1.0)
    walkway_width_cm: float = Field(ge=0.0)
    occupied_width_cm: float = Field(ge=0.0)
    free_width_cm: float = Field(ge=0.0)
    blocked: bool


# ─────────────────────────────────────────────────────────────────────────────


class CameraMeasurementMessage(BaseModel):
    """Kết quả mới nhất của một camera gửi qua WebSocket."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    camera_id: str = Field(min_length=1, max_length=100)
    camera_name: str = Field(min_length=1, max_length=100)
    state: Literal["pass", "blocked", "warming_up", "error"]
    zone_count: int | None = Field(default=None, ge=1, le=100)
    zones: list[ZoneOccupancyMeasurement] = Field(default_factory=list)
    blocked_zones: list[int] = Field(default_factory=list)
    maximum_occupancy_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    occupancy_threshold_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = Field(default=None, min_length=1, max_length=100)
    observed_at: datetime

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_snapshot(
        cls,
        camera: CameraConfig,
        snapshot: CorridorSnapshot,
    ) -> "CameraMeasurementMessage":
        """Chuyển snapshot nội bộ thành payload gọn dành cho Aggregator."""
        # Bước 1: quyết định camera giữ đúng logic zone hiện tại của backend.
        state = "pass" if snapshot.zone_clearance.can_pass else "blocked"
        reason = "occupancy_threshold_exceeded" if state == "blocked" else None

        # Bước 2: timestamp epoch của detector được chuẩn hóa thành ISO-8601 UTC.
        return cls(
            camera_id=camera.id,
            camera_name=camera.name,
            state=state,
            zone_count=len(snapshot.zone_clearance.zones),
            zones=[
                ZoneOccupancyMeasurement(
                    index=zone.index,
                    occupancy_ratio=round(zone.occupancy_ratio, 4),
                    walkway_width_cm=round(zone.walkway_width_meters * 100, 2),
                    occupied_width_cm=round(zone.occupied_width_meters * 100, 2),
                    free_width_cm=round(zone.free_width_meters * 100, 2),
                    blocked=zone.blocked,
                )
                for zone in snapshot.zone_clearance.zones
            ],
            blocked_zones=list(snapshot.zone_clearance.blocked_zone_indices),
            maximum_occupancy_ratio=(
                snapshot.zone_clearance.maximum_occupancy_ratio
            ),
            occupancy_threshold_ratio=(
                snapshot.zone_clearance.maximum_allowed_occupancy_ratio
            ),
            reason=reason,
            observed_at=datetime.fromtimestamp(
                snapshot.captured_at,
                tz=timezone.utc,
            ),
        )
