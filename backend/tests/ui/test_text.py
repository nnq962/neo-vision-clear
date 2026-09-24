"""Kiểm thử renderer chữ Unicode trên frame OpenCV."""

import unittest

import numpy as np

from walkway_monitor.ui import draw_text


class UnicodeTextTestCase(unittest.TestCase):
    """Kiểm tra chữ tiếng Việt có thể được render lên frame."""

    def test_draw_vietnamese_text(self) -> None:
        """Renderer phải tạo pixel hiển thị cho chuỗi có đầy đủ dấu tiếng Việt."""
        frame = np.zeros((80, 500, 3), dtype=np.uint8)
        rendered = draw_text(
            frame,
            "Đảm bảo lối đi TRỐNG – nhấn Enter để bắt đầu",
            (5, 5),
            font_size=22,
        )
        self.assertEqual(rendered.shape, frame.shape)
        self.assertGreater(int(np.count_nonzero(rendered)), 0)


if __name__ == "__main__":
    unittest.main()
