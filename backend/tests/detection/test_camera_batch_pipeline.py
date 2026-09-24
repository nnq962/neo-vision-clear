"""Kiểm thử pipeline gom một frame từ mỗi camera vào batch model."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.detection.camera_batch_pipeline import CameraBatchDetectionPipeline
from tests.detection.test_detector import make_baseline


class CameraBatchDetectionPipelineTestCase(unittest.TestCase):
    """Kiểm tra ánh xạ source, depth và analyzer theo camera."""

    def test_one_camera_uses_same_batch_pipeline(self) -> None:
        """Một camera vẫn gọi batch estimator và công bố output index 0."""
        baseline = make_baseline()
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        batch_sizes: list[int] = []

        class FakeEstimator:
            """Estimator giả ghi nhận số frame trong mỗi lượt inference."""

            def predict_batch(self, frames: list[np.ndarray]) -> list[np.ndarray]:
                """Trả một depth map tương ứng với frame camera duy nhất."""
                # Bước 1: kiểm tra pipeline gửi đúng một frame trong batch.
                batch_sizes.append(len(frames))
                return [baseline.reference_depth.copy()]

        class FakeMedia:
            """Nguồn giả phát đúng một frame rồi kết thúc."""

            def __init__(self) -> None:
                """Đánh dấu frame đầu tiên chưa được phát."""
                self.finished = False

            # ─────────────────────────────────────────────────────────────────

            def __enter__(self) -> "FakeMedia":
                """Trả nguồn giả cho context manager."""
                return self

            # ─────────────────────────────────────────────────────────────────

            def __exit__(self, *_args: object) -> None:
                """Không có tài nguyên thật cần giải phóng."""

            # ─────────────────────────────────────────────────────────────────

            def __iter__(self) -> "FakeMedia":
                """Trả iterator của nguồn giả."""
                return self

            # ─────────────────────────────────────────────────────────────────

            def __next__(self):
                """Phát batch một frame ở lần gọi đầu tiên."""
                if self.finished:
                    raise StopIteration
                self.finished = True
                return [frame.copy()], [None]

        published: list[int] = []
        pipeline = CameraBatchDetectionPipeline(
            estimator=FakeEstimator(),
            baselines=[baseline],
            config=DetectionConfig(),
            display=False,
            log_interval=0,
        )
        with patch(
            "walkway_monitor.detection.camera_batch_pipeline.MediaSources",
            return_value=FakeMedia(),
        ):
            processed = pipeline.run(
                ["rtsp://camera-1"],
                on_output=lambda camera_index, _output: published.append(camera_index),
            )

        self.assertEqual(processed, 1)
        self.assertEqual(batch_sizes, [1])
        self.assertEqual(published, [0])

    # ─────────────────────────────────────────────────────────────────────────

    def test_requires_at_least_one_baseline(self) -> None:
        """Pipeline từ chối batch không có camera."""
        with self.assertRaisesRegex(ValueError, "ít nhất một baseline"):
            CameraBatchDetectionPipeline(
                estimator=object(),
                baselines=[],
                config=DetectionConfig(),
                display=False,
            )

    # ─────────────────────────────────────────────────────────────────────────

    def test_two_cameras_share_one_batch_inference(self) -> None:
        """Một lượt đọc hai nguồn chỉ được gọi predict_batch đúng một lần."""
        baselines = [make_baseline(), make_baseline()]
        frames = [np.zeros((60, 80, 3), dtype=np.uint8) for _index in range(2)]

        class FakeEstimator:
            """Estimator giả ghi nhận kích thước batch model."""

            def __init__(self) -> None:
                """Khởi tạo lịch sử batch rỗng."""
                self.batch_sizes: list[int] = []

            # ─────────────────────────────────────────────────────────────────

            def predict(self, _frame: np.ndarray) -> np.ndarray:
                """Trả depth baseline khi API đơn được gọi trực tiếp."""
                return baselines[0].reference_depth.copy()

            # ─────────────────────────────────────────────────────────────────

            def predict_batch(
                self,
                batch_frames: list[np.ndarray],
            ) -> list[np.ndarray]:
                """Trả một depth map cho mỗi camera trong cùng lời gọi."""
                self.batch_sizes.append(len(batch_frames))
                return [
                    baseline.reference_depth.copy()
                    for baseline in baselines
                ]

        class FakeMedia:
            """Nguồn giả phát một batch gồm hai camera."""

            def __init__(self) -> None:
                """Đánh dấu batch chưa được phát."""
                self.finished = False

            # ─────────────────────────────────────────────────────────────────

            def __enter__(self) -> "FakeMedia":
                """Trả chính nguồn giả khi mở context."""
                return self

            # ─────────────────────────────────────────────────────────────────

            def __exit__(self, *_args: object) -> None:
                """Đóng context mà không cần giải phóng tài nguyên."""

            # ─────────────────────────────────────────────────────────────────

            def __iter__(self) -> "FakeMedia":
                """Trả chính đối tượng làm iterator."""
                return self

            # ─────────────────────────────────────────────────────────────────

            def __next__(self):
                """Phát đúng một frame cho mỗi camera rồi kết thúc."""
                if self.finished:
                    raise StopIteration
                self.finished = True
                return [frame.copy() for frame in frames], [None, None]

        estimator = FakeEstimator()
        published: list[tuple[int, int]] = []
        pipeline = CameraBatchDetectionPipeline(
            estimator=estimator,
            baselines=baselines,
            config=DetectionConfig(),
            display=False,
            log_interval=0,
        )
        with patch(
            "walkway_monitor.detection.camera_batch_pipeline.MediaSources",
            return_value=FakeMedia(),
        ):
            processed = pipeline.run(
                ["rtsp://camera-1", "rtsp://camera-2"],
                on_output=lambda camera_index, output: published.append(
                    (camera_index, output.snapshot.frame_index)
                ),
            )

        self.assertEqual(processed, 2)
        self.assertEqual(estimator.batch_sizes, [2])
        self.assertEqual(published, [(0, 0), (1, 0)])


if __name__ == "__main__":
    unittest.main()
