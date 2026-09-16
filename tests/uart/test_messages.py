"""Kiểm thử mã hóa và giải mã message UART ở mức byte."""

from __future__ import annotations

import struct
import unittest

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


class MessageTests(unittest.TestCase):
    """Kiểm tra round-trip, checksum và ràng buộc schema message."""

    # ─────────────────────────────────────────────────────────────────────────

    def test_encodes_get_corridor_info_exactly(self) -> None:
        """Request phải dùng đúng layout little-endian đã chốt trong spec."""
        message = GetCorridorInfo(robot_id=3, request_id=0x1234)
        payload = struct.pack("<BBH", MessageType.GET_CORRIDOR_INFO, 3, 0x1234)

        packet = message.encode()

        self.assertEqual(packet, payload + struct.pack("<H", calculate_checksum(payload)))
        self.assertEqual(packet.hex(" "), "10 03 34 12 65 b4")
        self.assertEqual(len(packet), 6)

    # ─────────────────────────────────────────────────────────────────────────

    def test_round_trips_corridor_info_with_data(self) -> None:
        """Response có dữ liệu phải giữ nguyên mọi field sau encode/decode."""
        message = CorridorInfo(
            robot_id=7,
            request_id=65535,
            status=CorridorStatus.OK,
            flags=DATA_AVAILABLE_FLAG,
            age_ms=42,
            maximum_passable_width_mm=820,
            walkway_width_mm=1750,
            bottleneck_y_mm=-2350,
            frame_index=120,
        )

        decoded = MessageBase.decode(message.encode())

        self.assertEqual(decoded, message)
        self.assertEqual(
            message.encode().hex(" "),
            "11 07 ff ff 00 01 2a 00 00 00 34 03 d6 06 "
            "d2 f6 ff ff 78 00 00 00 f9 e0",
        )
        self.assertEqual(len(message.encode()), 24)

    # ─────────────────────────────────────────────────────────────────────────

    def test_builds_and_round_trips_response_without_data(self) -> None:
        """Factory không dữ liệu phải áp dụng đúng sentinel của giao thức."""
        message = CorridorInfo.without_data(
            robot_id=1,
            request_id=9,
            status=CorridorStatus.WARMING_UP,
        )

        decoded = MessageBase.decode(message.encode())

        self.assertEqual(decoded, message)
        self.assertFalse(message.data_available)
        self.assertEqual(message.age_ms, NO_DATA_AGE_MS)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_corrupted_checksum(self) -> None:
        """Packet bị thay đổi payload phải bị từ chối thay vì trả dữ liệu sai."""
        packet = bytearray(GetCorridorInfo(robot_id=1, request_id=2).encode())
        packet[1] ^= 0x01

        with self.assertRaises(MessageDecodeError):
            MessageBase.decode(bytes(packet))
        self.assertIsNone(MessageBase.decode_any(bytes(packet)))

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_invalid_status_even_with_valid_checksum(self) -> None:
        """Payload có checksum đúng nhưng status lạ phải bị bỏ an toàn."""
        payload = struct.pack(
            "<BBHBBIHHiI",
            MessageType.CORRIDOR_INFO,
            1,
            2,
            99,
            0,
            NO_DATA_AGE_MS,
            0,
            0,
            0,
            0,
        )
        packet = payload + struct.pack("<H", calculate_checksum(payload))

        with self.assertRaises(MessageDecodeError):
            MessageBase.decode(packet)
        self.assertIsNone(MessageBase.decode_any(packet))

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_inconsistent_data_flag(self) -> None:
        """Status có dữ liệu không được phép tắt DATA_AVAILABLE."""
        with self.assertRaises(ValueError):
            CorridorInfo(
                robot_id=1,
                request_id=2,
                status=CorridorStatus.OK,
                flags=0,
                age_ms=0,
                maximum_passable_width_mm=820,
                walkway_width_mm=1750,
                bottleneck_y_mm=2350,
                frame_index=120,
            )

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_out_of_range_identifiers(self) -> None:
        """ID vượt kiểu nhị phân phải lỗi trước khi struct.pack được gọi."""
        with self.assertRaises(ValueError):
            GetCorridorInfo(robot_id=256, request_id=1)
        with self.assertRaises(ValueError):
            GetCorridorInfo(robot_id=1, request_id=65536)


if __name__ == "__main__":
    unittest.main()
