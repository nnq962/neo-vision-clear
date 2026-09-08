"""Kiểm thử voting mask theo nhiều frame gần nhất."""

import unittest

import numpy as np

from walkway_monitor.detection.mask_filter import TemporalMaskFilter


class TemporalMaskFilterTestCase(unittest.TestCase):
    """Kiểm tra nhiễu một frame bị bỏ và vùng bền vững được giữ lại."""

    def test_requires_three_of_five_frames(self) -> None:
        """Pixel chỉ xuất hiện một lần phải bị bỏ, xuất hiện ba lần phải được giữ."""
        mask_filter = TemporalMaskFilter(window_size=5, required_frames=3)
        empty = np.zeros((10, 10), dtype=np.uint8)
        changed = empty.copy()
        changed[3:7, 3:7] = 255
        self.assertEqual(int(np.count_nonzero(mask_filter.update(changed))), 0)
        self.assertEqual(int(np.count_nonzero(mask_filter.update(empty))), 0)
        self.assertEqual(int(np.count_nonzero(mask_filter.update(changed))), 0)
        stable = mask_filter.update(changed)
        self.assertEqual(int(np.count_nonzero(stable)), 16)


if __name__ == "__main__":
    unittest.main()
