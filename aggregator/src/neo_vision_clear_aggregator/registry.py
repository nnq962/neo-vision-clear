"""Kho in-memory join kết quả camera và tổng hợp quyết định hành lang."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Dict, List, Optional

from neo_vision_clear_aggregator.config import (
    AggregatorConfig,
    CameraLocationConfig,
)
from neo_vision_clear_aggregator.models import (
    BlockedArea,
    CameraMeasurement,
    CameraStatus,
    CorridorDecision,
    HealthResponse,
    LatestPayloadResponse,
    SourceStatus,
    UnavailableCamera,
)


class UnknownCameraError(ValueError):
    """Báo camera chưa có trong cấu hình Aggregator."""


class SourceMismatchError(ValueError):
    """Báo camera được gửi từ Jetson khác với cấu hình."""


@dataclass
class _SourceState:
    """State kết nối nội bộ của một Jetson source."""

    connection_count: int = 0
    message_count: int = 0
    connected_at: Optional[float] = None
    last_received_at: Optional[float] = None
    latest_payload: Optional[CameraMeasurement] = None


@dataclass
class _CameraReading:
    """Kết quả hợp lệ cuối cùng của một camera."""

    source_id: str
    received_at: float
    payload: CameraMeasurement


class SourceRegistry:
    """Theo dõi source, camera và quyết định hành lang theo latest-wins."""

    def __init__(self, config: AggregatorConfig, stale_seconds: float) -> None:
        """Khởi tạo registry với ánh xạ camera cố định từ config."""
        if stale_seconds <= 0:
            raise ValueError("stale_seconds phải là số dương.")
        self._config = config
        self._camera_map = config.camera_map()
        self._stale_seconds = stale_seconds
        self._sources: Dict[str, _SourceState] = {}
        self._readings: Dict[str, _CameraReading] = {}
        self._received_messages = 0
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────────────────────────────────────────

    async def connect(self, source_id: str) -> None:
        """Đánh dấu một kết nối WebSocket mới của Jetson."""
        now = time.time()
        async with self._lock:
            state = self._sources.setdefault(source_id, _SourceState())
            state.connection_count += 1
            if state.connection_count == 1:
                state.connected_at = now

    # ─────────────────────────────────────────────────────────────────────────

    async def disconnect(self, source_id: str) -> None:
        """Giảm số kết nối đang mở nhưng giữ snapshot cuối để chẩn đoán."""
        async with self._lock:
            state = self._sources.get(source_id)
            if state is not None:
                state.connection_count = max(state.connection_count - 1, 0)

    # ─────────────────────────────────────────────────────────────────────────

    async def update_config(self, config: AggregatorConfig) -> None:
        """Áp dụng ánh xạ mới và chỉ giữ reading của camera còn tồn tại."""
        async with self._lock:
            # Bước 1: thay config và map trong cùng lock với luồng ingest.
            self._config = config
            self._camera_map = config.camera_map()
            self._readings = {
                camera_id: reading
                for camera_id, reading in self._readings.items()
                if camera_id in self._camera_map
            }

    # ─────────────────────────────────────────────────────────────────────────

    async def ingest(
        self,
        source_id: str,
        payload: CameraMeasurement,
    ) -> CorridorDecision:
        """Validate quan hệ source-camera, lưu latest và trả quyết định mới."""
        location = self._camera_map.get(payload.camera_id)
        if location is None:
            raise UnknownCameraError(
                f"Camera '{payload.camera_id}' chưa có trong config."
            )
        if location.source_id != source_id:
            raise SourceMismatchError(
                f"Camera '{payload.camera_id}' phải đến từ '{location.source_id}'."
            )

        now = time.time()
        async with self._lock:
            # Bước 1: source và camera cùng được cập nhật trong một critical section.
            state = self._sources.setdefault(source_id, _SourceState())
            state.message_count += 1
            state.last_received_at = now
            state.latest_payload = payload.model_copy(deep=True)
            self._readings[payload.camera_id] = _CameraReading(
                source_id=source_id,
                received_at=now,
                payload=payload.model_copy(deep=True),
            )
            self._received_messages += 1
            return self._build_decision(now)

    # ─────────────────────────────────────────────────────────────────────────

    async def decision(self) -> CorridorDecision:
        """Tính lại quyết định hiện tại, bao gồm chuyển trạng thái stale."""
        now = time.time()
        async with self._lock:
            return self._build_decision(now)

    # ─────────────────────────────────────────────────────────────────────────

    async def list_sources(self) -> List[SourceStatus]:
        """Trả trạng thái mọi source theo thứ tự ID ổn định."""
        now = time.time()
        async with self._lock:
            return [
                self._to_source_status(source_id, state, now)
                for source_id, state in sorted(self._sources.items())
            ]

    # ─────────────────────────────────────────────────────────────────────────

    async def list_cameras(self) -> List[CameraStatus]:
        """Trả trạng thái mọi camera đã cấu hình theo thứ tự hành lang."""
        now = time.time()
        async with self._lock:
            result = []
            for location in sorted(self._config.cameras, key=lambda item: item.order):
                reading = self._readings.get(location.camera_id)
                threshold = self._config.corridor.maximum_occupancy_ratio
                measured_zones = reading.payload.zones if reading is not None else []
                blocked_zones = [
                    zone.index
                    for zone in measured_zones
                    if zone.occupancy_ratio >= threshold
                ]
                camera_state = reading.payload.state if reading is not None else None
                if camera_state in ("pass", "blocked"):
                    camera_state = "blocked" if blocked_zones else "pass"
                result.append(
                    CameraStatus(
                        camera_id=location.camera_id,
                        camera_name=(
                            reading.payload.camera_name if reading is not None else None
                        ),
                        source_id=location.source_id,
                        order=location.order,
                        location_name=location.location_name,
                        state=camera_state,
                        age_ms=self._reading_age_ms(reading, now),
                        stale=self._is_stale(reading, now),
                        blocked_zones=blocked_zones,
                        zones=(
                            [
                                zone.model_copy(
                                    update={"blocked": zone.index in blocked_zones},
                                    deep=True,
                                )
                                for zone in measured_zones
                            ]
                            if reading is not None
                            else []
                        ),
                        maximum_occupancy_ratio=(
                            max(
                                zone.occupancy_ratio
                                for zone in measured_zones
                            )
                            if reading is not None
                            and measured_zones
                            else None
                        ),
                        occupancy_threshold_ratio=(
                            threshold
                            if reading is not None
                            else None
                        ),
                        observed_at=(
                            reading.payload.observed_at
                            if reading is not None
                            else None
                        ),
                    )
                )
            return result

    # ─────────────────────────────────────────────────────────────────────────

    async def latest(self, source_id: str) -> Optional[LatestPayloadResponse]:
        """Trả payload cuối của source hoặc None khi chưa nhận dữ liệu."""
        async with self._lock:
            state = self._sources.get(source_id)
            if (
                state is None
                or state.latest_payload is None
                or state.last_received_at is None
            ):
                return None
            return LatestPayloadResponse(
                source_id=source_id,
                received_at=state.last_received_at,
                payload=state.latest_payload.model_copy(deep=True),
            )

    # ─────────────────────────────────────────────────────────────────────────

    async def list_latest(self) -> List[LatestPayloadResponse]:
        """Trả payload cuối của từng camera theo thứ tự hành lang."""
        async with self._lock:
            result = []
            for location in sorted(self._config.cameras, key=lambda item: item.order):
                reading = self._readings.get(location.camera_id)
                if reading is None:
                    continue
                result.append(
                    LatestPayloadResponse(
                        source_id=reading.source_id,
                        received_at=reading.received_at,
                        payload=reading.payload.model_copy(deep=True),
                    )
                )
            return result

    # ─────────────────────────────────────────────────────────────────────────

    async def health(self) -> HealthResponse:
        """Tổng hợp số nguồn, camera cấu hình và message đã nhận."""
        async with self._lock:
            return HealthResponse(
                connected_sources=sum(
                    state.connection_count > 0 for state in self._sources.values()
                ),
                known_sources=len(self._sources),
                configured_cameras=len(self._config.cameras),
                received_messages=self._received_messages,
            )

    # ─────────────────────────────────────────────────────────────────────────

    def _build_decision(self, now: float) -> CorridorDecision:
        """Dựng kết luận khi caller đang giữ registry lock."""
        blocked_areas: List[BlockedArea] = []
        unavailable: List[UnavailableCamera] = []

        # Bước 1: duyệt theo order cấu hình, tuyệt đối không dựa thứ tự message.
        for location in sorted(self._config.cameras, key=lambda item: item.order):
            reading = self._readings.get(location.camera_id)
            if reading is None:
                unavailable.append(self._unavailable(location, None, "missing"))
                continue
            if self._is_stale(reading, now):
                unavailable.append(self._unavailable(location, reading, "stale"))
                continue
            if reading.payload.state in ("warming_up", "error"):
                unavailable.append(
                    self._unavailable(
                        location,
                        reading,
                        reading.payload.reason or reading.payload.state,
                    )
                )
                continue

            # Bước 2: Aggregator tự áp ngưỡng lên tỷ lệ tổng của từng zone.
            threshold = self._config.corridor.maximum_occupancy_ratio
            blocked_zones = [
                zone.index
                for zone in reading.payload.zones
                if zone.occupancy_ratio >= threshold
            ]
            if blocked_zones:
                blocked_areas.append(
                    BlockedArea(
                        order=location.order,
                        location_name=location.location_name,
                        camera_id=location.camera_id,
                        camera_name=reading.payload.camera_name,
                        blocked_zones=blocked_zones,
                        zone_count=reading.payload.zone_count or 1,
                        zones=[
                            zone.model_copy(
                                update={"blocked": zone.index in blocked_zones},
                                deep=True,
                            )
                            for zone in reading.payload.zones
                        ],
                        maximum_occupancy_ratio=max(
                            zone.occupancy_ratio for zone in reading.payload.zones
                        ),
                        occupancy_threshold_ratio=threshold,
                        reason="occupancy_threshold_exceeded",
                        source=reading.source_id,
                        observed_at=reading.payload.observed_at,
                    )
                )

        # Bước 3: blocked có bằng chứng chắc chắn; unknown chỉ dùng khi chưa đủ data.
        if blocked_areas:
            state = "blocked"
            can_pass = False
        elif unavailable:
            state = "unknown"
            can_pass = None
        else:
            state = "pass"
            can_pass = True
        return CorridorDecision(
            zone_code=self._config.corridor.zone_code,
            corridor_id=self._config.corridor.corridor_id,
            corridor_name=self._config.corridor.corridor_name,
            state=state,
            can_pass=can_pass,
            occupancy_threshold_ratio=(
                self._config.corridor.maximum_occupancy_ratio
            ),
            blocked_areas=blocked_areas,
            unavailable_cameras=unavailable,
            decided_at=datetime.now(timezone.utc),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _unavailable(
        self,
        location: CameraLocationConfig,
        reading: Optional[_CameraReading],
        reason: str,
    ) -> UnavailableCamera:
        """Tạo mô tả camera thiếu dữ liệu với metadata cấu hình."""
        return UnavailableCamera(
            order=location.order,
            location_name=location.location_name,
            camera_id=location.camera_id,
            camera_name=reading.payload.camera_name if reading is not None else None,
            reason=reason,
            source=location.source_id,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _is_stale(self, reading: Optional[_CameraReading], now: float) -> bool:
        """Xác định camera chưa có hoặc đã quá ngưỡng tuổi dữ liệu."""
        return reading is None or now - reading.received_at > self._stale_seconds

    # ─────────────────────────────────────────────────────────────────────────

    def _reading_age_ms(
        self,
        reading: Optional[_CameraReading],
        now: float,
    ) -> Optional[int]:
        """Tính tuổi message theo đồng hồ nhận tại Aggregator."""
        if reading is None:
            return None
        return max(int(round((now - reading.received_at) * 1000)), 0)

    # ─────────────────────────────────────────────────────────────────────────

    def _to_source_status(
        self,
        source_id: str,
        state: _SourceState,
        now: float,
    ) -> SourceStatus:
        """Chuyển source state nội bộ thành response bất biến."""
        age_ms = None
        if state.last_received_at is not None:
            age_ms = max(int(round((now - state.last_received_at) * 1000)), 0)
        return SourceStatus(
            source_id=source_id,
            connected=state.connection_count > 0,
            connection_count=state.connection_count,
            message_count=state.message_count,
            connected_at=state.connected_at,
            last_received_at=state.last_received_at,
            age_ms=age_ms,
            stale=(
                state.last_received_at is None
                or now - state.last_received_at > self._stale_seconds
            ),
        )
