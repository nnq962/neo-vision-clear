"""Schema message một chiều từ Jetson tới Aggregator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.models.camera import CameraConfig
from walkway_monitor.detection.models import CorridorSnapshot


class CameraMeasurementMessage(BaseModel):
    """Kết quả mới nhất của một camera gửi qua WebSocket."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    camera_id: str = Field(min_length=1, max_length=100)
    camera_name: str = Field(min_length=1, max_length=100)
    state: Literal["pass", "blocked", "warming_up", "error"]
    zone_count: int | None = Field(default=None, ge=1, le=100)
    blocked_zones: list[int] = Field(default_factory=list)
    minimum_free_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    max_passable_width_cm: float | None = Field(default=None, ge=0.0)
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
        reason = None
        if state == "blocked":
            reason = (
                "route_disconnected"
                if snapshot.maximum_passable_width_meters <= 0
                else "insufficient_clearance"
            )

        # Bước 2: timestamp epoch của detector được chuẩn hóa thành ISO-8601 UTC.
        return cls(
            camera_id=camera.id,
            camera_name=camera.name,
            state=state,
            zone_count=len(snapshot.zone_clearance.zones),
            blocked_zones=list(snapshot.zone_clearance.blocked_zone_indices),
            minimum_free_ratio=snapshot.zone_clearance.minimum_free_ratio,
            max_passable_width_cm=round(
                snapshot.maximum_passable_width_meters * 100,
                2,
            ),
            reason=reason,
            observed_at=datetime.fromtimestamp(
                snapshot.captured_at,
                tz=timezone.utc,
            ),
        )
