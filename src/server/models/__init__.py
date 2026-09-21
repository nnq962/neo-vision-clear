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
    "BottleneckPayload",
    "CorridorInfoData",
    "CorridorInfoRequest",
    "CorridorInfoResponse",
    "DifferenceZonePayload",
    "OverviewCameraInfo",
    "OverviewInfoData",
    "OverviewInfoRequest",
    "OverviewInfoResponse",
    "ProtocolErrorResponse",
    "RuntimeConfig",
    "RuntimeDetectionConfig",
    "RuntimeProcessResponse",
]
