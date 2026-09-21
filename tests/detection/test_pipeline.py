"""Kiểm thử resize full frame về đúng kích thước baseline."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.detection.pipeline import DetectionPipeline, resize_to_baseline
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

    # ─────────────────────────────────────────────────────────────────────────

    def test_run_collects_stage_timings_without_changing_frame_count(self) -> None:
        """Pipeline có timing chi tiết vẫn phải xử lý đủ frame từ iterator."""
        baseline = make_baseline()
        frame = np.zeros((60, 80, 3), dtype=np.uint8)

        class FakeEstimator:
            """Estimator giả trả depth của baseline."""

            def __init__(self) -> None:
                """Khởi tạo lịch sử kích thước batch đã nhận."""
                self.batch_sizes: list[int] = []

            def predict(self, _frame: np.ndarray) -> np.ndarray:
                """Trả bản sao depth để analyzer có thể xử lý độc lập."""
                return baseline.reference_depth.copy()

            # ─────────────────────────────────────────────────────────────────

            def predict_batch(self, frames: list[np.ndarray]) -> list[np.ndarray]:
                """Ghi nhận batch và trả một depth map cho mỗi frame."""
                self.batch_sizes.append(len(frames))
                return [self.predict(frame) for frame in frames]

        class FakeMedia:
            """Nguồn giả phát đúng hai frame rồi kết thúc."""

            def __init__(self) -> None:
                """Khởi tạo số frame đã phát bằng không."""
                self.count = 0

            # ─────────────────────────────────────────────────────────────────────────

            def __enter__(self) -> "FakeMedia":
                """Trả chính nguồn giả khi mở context."""
                return self

            # ─────────────────────────────────────────────────────────────────────────

            def __exit__(self, *_args: object) -> None:
                """Đóng context mà không cần giải phóng tài nguyên."""

            # ─────────────────────────────────────────────────────────────────────────

            def __iter__(self) -> "FakeMedia":
                """Trả chính đối tượng làm iterator."""
                return self

            # ─────────────────────────────────────────────────────────────────

            def __next__(self):
                """Phát hai frame theo giao diện batch của MediaSources."""
                if self.count >= 2:
                    raise StopIteration
                self.count += 1
                return [frame.copy()], [None]

        estimator = FakeEstimator()
        pipeline = DetectionPipeline(
            estimator,
            baseline,
            DetectionConfig(),
            display=False,
            log_interval=0,
            batch_size=2,
        )
        with patch(
            "walkway_monitor.detection.pipeline.MediaSources",
            return_value=FakeMedia(),
        ):
            processed = pipeline.run("fake")

        self.assertEqual(processed, 2)
        self.assertEqual(estimator.batch_sizes, [2])


if __name__ == "__main__":
    unittest.main()
