"""Kiểm thử adapter batch của depth estimator."""

from __future__ import annotations

import unittest

import numpy as np

from walkway_monitor.depth.estimator import predict_depth_batch


class PredictDepthBatchTestCase(unittest.TestCase):
    """Kiểm tra estimator luôn nhận batch và trả đúng số depth map."""

    def test_prefers_native_batch_prediction(self) -> None:
        """Estimator có predict_batch chỉ được gọi một lần cho toàn bộ frame."""
        class BatchEstimator:
            """Estimator giả có cả API đơn và API batch."""

            def __init__(self) -> None:
                """Khởi tạo bộ đếm lời gọi."""
                self.batch_calls = 0
                self.single_calls = 0

            # ─────────────────────────────────────────────────────────────────

            def predict(self, frame: np.ndarray) -> np.ndarray:
                """Ghi nhận lời gọi đơn không mong muốn."""
                self.single_calls += 1
                return np.zeros(frame.shape[:2], dtype=np.float32)

            # ─────────────────────────────────────────────────────────────────

            def predict_batch(self, frames: list[np.ndarray]) -> list[np.ndarray]:
                """Trả depth map tương ứng bằng một lời gọi batch."""
                self.batch_calls += 1
                return [np.zeros(frame.shape[:2], dtype=np.float32) for frame in frames]

        estimator = BatchEstimator()
        frames = [np.zeros((8, 12, 3), dtype=np.uint8) for _index in range(3)]

        depths = predict_depth_batch(estimator, frames)

        self.assertEqual(len(depths), 3)
        self.assertEqual(estimator.batch_calls, 1)
        self.assertEqual(estimator.single_calls, 0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_incomplete_batch_output(self) -> None:
        """Adapter từ chối estimator trả thiếu depth map trong batch."""
        class IncompleteEstimator:
            """Estimator giả cố ý trả thiếu một kết quả."""

            def predict_batch(self, frames: list[np.ndarray]) -> list[np.ndarray]:
                """Chỉ trả depth map cho frame đầu tiên."""
                # Bước 1: giữ một phần tử để kiểm tra lỗi sai độ dài.
                return [np.zeros(frames[0].shape[:2], dtype=np.float32)]

        estimator = IncompleteEstimator()
        frames = [np.zeros((8, 12, 3), dtype=np.uint8) for _index in range(3)]

        with self.assertRaisesRegex(RuntimeError, "sai số lượng"):
            predict_depth_batch(estimator, frames)


if __name__ == "__main__":
    unittest.main()
