"""Các schema JSON dùng bởi API và WebSocket."""

from server.models.aggregator import CameraMeasurementMessage
from server.models.calibration import (
    CalibrationConfig,
    CalibrationCreate,
    CalibrationResponse,
    CalibrationRunResponse,
    CalibrationUpdate,
)
from server.models.camera import (
    CameraConfig,
    CameraCreate,
    CameraResponse,
    CameraUpdate,
)
from server.models.config import (
    AppConfigDocument,
    RuntimeConfig,
    RuntimeDetectionConfig,
    RuntimeProcessResponse,
)
from server.models.messages import (
    BottleneckPayload,
    CorridorInfoData,
    DifferenceZonePayload,
    OverviewClearanceZonePayload,
    OverviewCameraInfo,
    OverviewInfoData,
    OverviewInfoRequest,
    OverviewInfoResponse,
    ProtocolErrorResponse,
)
from server.models.system_metrics import (
    CpuCoreMetrics,
    CpuMetrics,
    GpuMetrics,
    RamMetrics,
    SystemMetricsResponse,
)

__all__ = [
    "AppConfigDocument",
    "CalibrationConfig",
    "CalibrationCreate",
    "CalibrationResponse",
    "CalibrationRunResponse",
    "CalibrationUpdate",
    "CameraConfig",
    "CameraMeasurementMessage",
    "CameraCreate",
    "CameraResponse",
    "CameraUpdate",
    "CpuCoreMetrics",
    "CpuMetrics",
    "BottleneckPayload",
    "CorridorInfoData",
    "DifferenceZonePayload",
    "GpuMetrics",
    "RamMetrics",
    "OverviewCameraInfo",
    "OverviewClearanceZonePayload",
    "OverviewInfoData",
    "OverviewInfoRequest",
    "OverviewInfoResponse",
    "ProtocolErrorResponse",
    "RuntimeConfig",
    "RuntimeDetectionConfig",
    "RuntimeProcessResponse",
    "SystemMetricsResponse",
]
