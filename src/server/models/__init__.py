"""Các schema JSON dùng bởi API và WebSocket."""

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
    CorridorInfoRequest,
    CorridorInfoResponse,
    DifferenceZonePayload,
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
    "CameraCreate",
    "CameraResponse",
    "CameraUpdate",
    "CpuCoreMetrics",
    "CpuMetrics",
    "BottleneckPayload",
    "CorridorInfoData",
    "CorridorInfoRequest",
    "CorridorInfoResponse",
    "DifferenceZonePayload",
    "GpuMetrics",
    "RamMetrics",
    "OverviewCameraInfo",
    "OverviewInfoData",
    "OverviewInfoRequest",
    "OverviewInfoResponse",
    "ProtocolErrorResponse",
    "RuntimeConfig",
    "RuntimeDetectionConfig",
    "RuntimeProcessResponse",
    "SystemMetricsResponse",
]
