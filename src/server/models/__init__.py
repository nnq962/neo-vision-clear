"""Các schema JSON dùng bởi API và WebSocket."""

from server.models.messages import (
    BottleneckPayload,
    CorridorInfoData,
    CorridorInfoRequest,
    CorridorInfoResponse,
    ProtocolErrorResponse,
)

__all__ = [
    "BottleneckPayload",
    "CorridorInfoData",
    "CorridorInfoRequest",
    "CorridorInfoResponse",
    "ProtocolErrorResponse",
]
