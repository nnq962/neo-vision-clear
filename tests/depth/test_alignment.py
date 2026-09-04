"""Kiểm thử phép căn chỉnh affine giữa relative depth map."""

import unittest

import numpy as np

from walkway_monitor.depth.alignment import align_depth, fit_affine_alignment


class AlignmentTestCase(unittest.TestCase):
    """Kiểm tra scale và shift được khôi phục trên dữ liệu tổng hợp."""

    def test_fit_affine_alignment_recovers_reference(self) -> None:
        """Depth sau căn chỉnh phải gần reference khi có scale và shift toàn cục."""
        reference = np.linspace(0.2, 4.0, 400, dtype=np.float32).reshape(20, 20)
        current = (reference - 0.7) / 1.8
        aligned, scale, shift = align_depth(current, reference)
        np.testing.assert_allclose(aligned, reference, atol=1e-5)
        self.assertAlmostEqual(scale, 1.8, places=5)
        self.assertAlmostEqual(shift, 0.7, places=5)

    # ─────────────────────────────────────────────────────────────────────────

    def test_support_mask_ignores_changed_roi(self) -> None:
        """Vùng thay đổi ngoài support mask không được làm lệch phép fit."""
        reference = np.linspace(0.0, 2.0, 400, dtype=np.float32).reshape(20, 20)
        current = reference.copy()
        current[5:15, 5:15] += 10.0
        support = np.ones_like(reference, dtype=bool)
        support[5:15, 5:15] = False
        scale, shift = fit_affine_alignment(current, reference, support)
        self.assertAlmostEqual(scale, 1.0, places=5)
        self.assertAlmostEqual(shift, 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
