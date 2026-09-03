"""Kiểm thử lớp tích hợp với package media-sources."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from media_sources import BaseReader

from occupancy_monitor.stream import open_stream, read_frame


class StreamTests(unittest.TestCase):
    """Xác nhận ứng dụng ủy quyền việc đọc nguồn cho media-sources."""

    @patch("occupancy_monitor.stream.create_media_source")
    def test_open_stream_uses_media_sources(self, factory: MagicMock) -> None:
        """Nguồn webcam dạng chuỗi phải được chuẩn hóa và mở qua factory chung."""
        reader = MagicMock(spec=BaseReader)
        factory.return_value = reader

        result = open_stream("0")

        factory.assert_called_once_with(
            0,
            use_gstreamer=True,
            reconnect=True,
            reconnect_forever=True,
        )
        reader.open.assert_called_once_with()
        self.assertIs(result, reader)

    # ─────────────────────────────────────────────────────────────────────────
    def test_read_frame_unpacks_media_source_result(self) -> None:
        """Frame phải được lấy đúng từ cặp dữ liệu frame và metadata."""
        expected = np.zeros((20, 30, 3), dtype=np.uint8)
        reader = MagicMock(spec=BaseReader)
        reader.read.return_value = (expected, object())

        actual = read_frame(reader)

        self.assertIs(actual, expected)


if __name__ == "__main__":
    unittest.main()
