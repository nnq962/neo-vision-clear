"""Giao thức message và quản lý kết nối UART dành cho robot."""

from uart.messages import (
    DATA_AVAILABLE_FLAG,
    NO_DATA_AGE_MS,
    CorridorInfo,
    CorridorStatus,
    GetCorridorInfo,
    MessageBase,
    MessageDecodeError,
    MessageType,
    calculate_checksum,
)
from uart.uart_manager import UartManagerV2


__all__ = [
    "DATA_AVAILABLE_FLAG",
    "NO_DATA_AGE_MS",
    "CorridorInfo",
    "CorridorStatus",
    "GetCorridorInfo",
    "MessageBase",
    "MessageDecodeError",
    "MessageType",
    "UartManagerV2",
    "calculate_checksum",
]
