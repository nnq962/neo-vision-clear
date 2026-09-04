"""Kiểm thử resize full frame về đúng kích thước baseline."""

import unittest

import numpy as np

from walkway_monitor.detection.pipeline import resize_to_baseline
from tests.detection.test_detector import make_baseline


class DetectionPipelineTestCase(unittest.TestCase):
    """Kiểm tra resize giữ đúng hệ tọa độ baseline."""

    def test_resize_matching_aspect_ratio(self) -> None:
        """Frame cùng tỷ lệ phải resize chính xác về shape baseline."""
        baseline = make_baseline()
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        resized = resize_to_baseline(frame, baseline)
        self.assertEqual(resized.shape, (60, 80, 3))

    # ─────────────────────────────────────────────────────────────────────────

    def test_reject_changed_aspect_ratio(self) -> None:
        """Frame đổi tỷ lệ phải bị từ chối để tránh làm sai polygon ROI."""
        baseline = make_baseline()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with self.assertRaises(RuntimeError):
            resize_to_baseline(frame, baseline)


if __name__ == "__main__":
    unittest.main()
