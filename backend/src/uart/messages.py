"""Các định nghĩa message nhị phân dùng cho giao tiếp UART với robot."""

from __future__ import annotations

from abc import ABC, abstractmethod
import binascii
from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import ClassVar


CHECKSUM_STRUCT = struct.Struct("<H")
DATA_AVAILABLE_FLAG = 0x01
NO_DATA_AGE_MS = 0xFFFFFFFF


class MessageType(IntEnum):
    """Mã loại message được truyền trong byte đầu của payload."""

    GET_CORRIDOR_INFO = 0x10
    CORRIDOR_INFO = 0x11


class CorridorStatus(IntEnum):
    """Trạng thái của snapshot lối đi trả về cho robot."""

    OK = 0
    WARMING_UP = 1
    STALE = 2
    ERROR = 3


class MessageDecodeError(ValueError):
    """Báo lỗi packet sai checksum, sai kích thước hoặc sai nội dung."""


# ─────────────────────────────────────────────────────────────────────────────


def calculate_checksum(payload: bytes) -> int:
    """Tính checksum bằng 16 bit thấp của CRC32 trên toàn bộ payload."""
    # Giữ nguyên công thức của giao thức cũ để firmware có thể tái sử dụng.
    return binascii.crc32(payload) & 0xFFFF


# ─────────────────────────────────────────────────────────────────────────────


def _validate_unsigned(name: str, value: int, maximum: int) -> None:
    """Kiểm tra một giá trị nguyên không dấu nằm trong miền cho phép."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} phải là số nguyên.")
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} phải nằm trong [0, {maximum}].")


# ─────────────────────────────────────────────────────────────────────────────


def _validate_signed(name: str, value: int, minimum: int, maximum: int) -> None:
    """Kiểm tra một giá trị nguyên có dấu nằm trong miền cho phép."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} phải là số nguyên.")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} phải nằm trong [{minimum}, {maximum}].")


class MessageBase(ABC):
    """Lớp cơ sở đăng ký, mã hóa và giải mã mọi message của giao thức."""

    MESSAGE_TYPE: ClassVar[MessageType]
    PAYLOAD_STRUCT: ClassVar[struct.Struct]
    _registry: ClassVar[dict[MessageType, type["MessageBase"]]] = {}

    # ─────────────────────────────────────────────────────────────────────────

    def __init_subclass__(cls, **kwargs) -> None:
        """Đăng ký message con theo MESSAGE_TYPE để phục vụ decode động."""
        super().__init_subclass__(**kwargs)
        message_type = getattr(cls, "MESSAGE_TYPE", None)
        if message_type is None:
            return
        normalized = MessageType(message_type)
        if normalized in MessageBase._registry:
            raise TypeError(f"Message type đã được đăng ký: {normalized!r}.")
        MessageBase._registry[normalized] = cls

    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def encode_payload(self) -> bytes:
        """Mã hóa message thành payload bắt đầu bằng message_type."""

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    @abstractmethod
    def decode_payload(cls, payload: bytes) -> "MessageBase":
        """Giải mã payload đã được kiểm tra checksum thành message cụ thể."""

    # ─────────────────────────────────────────────────────────────────────────

    def encode(self) -> bytes:
        """Mã hóa message thành payload kèm checksum, chưa gồm UART framing."""
        # Bước 1: lớp con tạo payload có message_type ở byte đầu tiên.
        payload = self.encode_payload()

        # Bước 2: checksum uint16 little-endian luôn nằm ở cuối packet.
        checksum = calculate_checksum(payload)
        return payload + CHECKSUM_STRUCT.pack(checksum)

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def decode(cls, packet: bytes) -> "MessageBase":
        """Giải mã packet payload+checksum và báo lỗi khi packet không hợp lệ."""
        # Bước 1: cần ít nhất một byte message_type và hai byte checksum.
        if len(packet) < 3:
            raise MessageDecodeError("Packet quá ngắn để chứa message và checksum.")

        # Bước 2: kiểm tra checksum trước khi đọc hoặc tin cậy payload.
        payload = packet[:-CHECKSUM_STRUCT.size]
        actual_checksum = CHECKSUM_STRUCT.unpack(packet[-CHECKSUM_STRUCT.size :])[0]
        expected_checksum = calculate_checksum(payload)
        if actual_checksum != expected_checksum:
            raise MessageDecodeError("Checksum của packet không hợp lệ.")

        # Bước 3: chọn lớp message bằng byte đầu của payload.
        try:
            message_type = MessageType(payload[0])
        except ValueError as exc:
            raise MessageDecodeError(
                f"Message type không được hỗ trợ: 0x{payload[0]:02X}."
            ) from exc
        message_class = cls._registry.get(message_type)
        if message_class is None:
            raise MessageDecodeError(
                f"Chưa đăng ký bộ giải mã cho message type {message_type!r}."
            )
        try:
            return message_class.decode_payload(payload)
        except MessageDecodeError:
            raise
        except (TypeError, ValueError, struct.error) as exc:
            raise MessageDecodeError("Nội dung payload không hợp lệ.") from exc

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def decode_any(cls, packet: bytes) -> "MessageBase | None":
        """Giải mã packet và trả None để UART bỏ qua frame lỗi an toàn."""
        try:
            return cls.decode(packet)
        except MessageDecodeError:
            return None


@dataclass(frozen=True)
class GetCorridorInfo(MessageBase):
    """Yêu cầu của robot muốn đọc snapshot lối đi mới nhất."""

    MESSAGE_TYPE: ClassVar[MessageType] = MessageType.GET_CORRIDOR_INFO
    PAYLOAD_STRUCT: ClassVar[struct.Struct] = struct.Struct("<BBH")

    robot_id: int
    request_id: int

    # ─────────────────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """Kiểm tra ID robot và request trước khi cho phép mã hóa."""
        _validate_unsigned("robot_id", self.robot_id, 0xFF)
        _validate_unsigned("request_id", self.request_id, 0xFFFF)

    # ─────────────────────────────────────────────────────────────────────────

    def encode_payload(self) -> bytes:
        """Mã hóa yêu cầu thành payload có kích thước cố định bốn byte."""
        return self.PAYLOAD_STRUCT.pack(
            int(self.MESSAGE_TYPE),
            self.robot_id,
            self.request_id,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def decode_payload(cls, payload: bytes) -> "GetCorridorInfo":
        """Giải mã payload yêu cầu và kiểm tra đúng message type."""
        if len(payload) != cls.PAYLOAD_STRUCT.size:
            raise MessageDecodeError("Payload GET_CORRIDOR_INFO sai kích thước.")
        message_type, robot_id, request_id = cls.PAYLOAD_STRUCT.unpack(payload)
        if message_type != cls.MESSAGE_TYPE:
            raise MessageDecodeError("Payload không phải GET_CORRIDOR_INFO.")
        return cls(robot_id=robot_id, request_id=request_id)


@dataclass(frozen=True)
class CorridorInfo(MessageBase):
    """Snapshot lối đi của vision phản hồi cho một yêu cầu của robot."""

    MESSAGE_TYPE: ClassVar[MessageType] = MessageType.CORRIDOR_INFO
    PAYLOAD_STRUCT: ClassVar[struct.Struct] = struct.Struct("<BBHBBIHHiI")

    robot_id: int
    request_id: int
    status: CorridorStatus
    flags: int
    age_ms: int
    maximum_passable_width_mm: int
    walkway_width_mm: int
    bottleneck_y_mm: int
    frame_index: int

    # ─────────────────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """Chuẩn hóa enum và kiểm tra miền cùng quan hệ giữa các field."""
        # Bước 1: chuyển int hợp lệ thành enum để API Python luôn nhất quán.
        try:
            normalized_status = CorridorStatus(self.status)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"status không hợp lệ: {self.status!r}.") from exc
        object.__setattr__(self, "status", normalized_status)

        # Bước 2: kiểm tra đúng miền biểu diễn của từng field nhị phân.
        _validate_unsigned("robot_id", self.robot_id, 0xFF)
        _validate_unsigned("request_id", self.request_id, 0xFFFF)
        _validate_unsigned("flags", self.flags, 0xFF)
        _validate_unsigned("age_ms", self.age_ms, 0xFFFFFFFF)
        _validate_unsigned(
            "maximum_passable_width_mm",
            self.maximum_passable_width_mm,
            0xFFFF,
        )
        _validate_unsigned("walkway_width_mm", self.walkway_width_mm, 0xFFFF)
        _validate_signed("bottleneck_y_mm", self.bottleneck_y_mm, -(2**31), 2**31 - 1)
        _validate_unsigned("frame_index", self.frame_index, 0xFFFFFFFF)
        if self.flags & ~DATA_AVAILABLE_FLAG:
            raise ValueError("flags chứa bit chưa được định nghĩa.")

        # Bước 3: trạng thái và cờ dữ liệu phải mô tả cùng một sự thật.
        if self.status in {CorridorStatus.OK, CorridorStatus.STALE} and not self.data_available:
            raise ValueError("Trạng thái OK/STALE bắt buộc phải có dữ liệu.")
        if self.status is CorridorStatus.WARMING_UP and self.data_available:
            raise ValueError("Trạng thái WARMING_UP không được kèm dữ liệu.")
        if self.data_available and self.age_ms == NO_DATA_AGE_MS:
            raise ValueError("Snapshot có dữ liệu không được dùng age_ms sentinel.")
        if not self.data_available and (
            self.age_ms != NO_DATA_AGE_MS
            or self.maximum_passable_width_mm != 0
            or self.walkway_width_mm != 0
            or self.bottleneck_y_mm != 0
            or self.frame_index != 0
        ):
            raise ValueError("Response không có dữ liệu phải dùng các giá trị rỗng quy ước.")

    # ─────────────────────────────────────────────────────────────────────────

    @property
    def data_available(self) -> bool:
        """Trả True khi bit DATA_AVAILABLE đang được bật."""
        return bool(self.flags & DATA_AVAILABLE_FLAG)

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def without_data(
        cls,
        robot_id: int,
        request_id: int,
        status: CorridorStatus,
    ) -> "CorridorInfo":
        """Tạo response chưa có snapshot cho trạng thái warming-up hoặc lỗi."""
        if status not in {CorridorStatus.WARMING_UP, CorridorStatus.ERROR}:
            raise ValueError("Chỉ WARMING_UP hoặc ERROR được phép không có dữ liệu.")
        return cls(
            robot_id=robot_id,
            request_id=request_id,
            status=status,
            flags=0,
            age_ms=NO_DATA_AGE_MS,
            maximum_passable_width_mm=0,
            walkway_width_mm=0,
            bottleneck_y_mm=0,
            frame_index=0,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def encode_payload(self) -> bytes:
        """Mã hóa snapshot thành payload có kích thước cố định 22 byte."""
        return self.PAYLOAD_STRUCT.pack(
            int(self.MESSAGE_TYPE),
            self.robot_id,
            self.request_id,
            int(self.status),
            self.flags,
            self.age_ms,
            self.maximum_passable_width_mm,
            self.walkway_width_mm,
            self.bottleneck_y_mm,
            self.frame_index,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def decode_payload(cls, payload: bytes) -> "CorridorInfo":
        """Giải mã payload snapshot và kiểm tra đúng message type."""
        if len(payload) != cls.PAYLOAD_STRUCT.size:
            raise MessageDecodeError("Payload CORRIDOR_INFO sai kích thước.")
        values = cls.PAYLOAD_STRUCT.unpack(payload)
        if values[0] != cls.MESSAGE_TYPE:
            raise MessageDecodeError("Payload không phải CORRIDOR_INFO.")
        return cls(
            robot_id=values[1],
            request_id=values[2],
            status=CorridorStatus(values[3]),
            flags=values[4],
            age_ms=values[5],
            maximum_passable_width_mm=values[6],
            walkway_width_mm=values[7],
            bottleneck_y_mm=values[8],
            frame_index=values[9],
        )
