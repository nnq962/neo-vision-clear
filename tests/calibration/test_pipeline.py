"""Kiểm thử tích hợp pipeline calibration bằng dependency giả."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from walkway_monitor.calibration.pipeline import CalibrationPipeline
from walkway_monitor.config import CalibrationConfig
from walkway_monitor.models import RoiDefinition


class FakeEstimator:
    """Depth estimator xác định dùng để test mà không cần checkpoint."""

    def predict(self, frame: np.ndarray) -> np.ndarray:
        """Trả về gradient depth cố định cùng kích thước frame."""
        height, width = frame.shape[:2]
        return np.linspace(0.1, 2.0, height * width, dtype=np.float32).reshape(
            height, width
        )


class FakeMediaSources:
    """MediaSources giả cung cấp một frame ROI và năm frame calibration."""

    def __init__(self, _source, **_options):
        """Tạo sẵn sáu frame và metadata video tối thiểu."""
        self._index = 0
        self._frames = [np.zeros((20, 30, 3), dtype=np.uint8) for _ in range(6)]
        self._meta = SimpleNamespace(source_type=SimpleNamespace(name="VIDEO"))

    # ─────────────────────────────────────────────────────────────────────────

    def __enter__(self):
        """Trả về chính nguồn giả khi vào context manager."""
        return self

    # ─────────────────────────────────────────────────────────────────────────

    def __exit__(self, *_args) -> None:
        """Kết thúc context manager mà không cần giải phóng tài nguyên."""

    # ─────────────────────────────────────────────────────────────────────────

    def __next__(self):
        """Trả về batch một frame cho tới khi hết dữ liệu giả."""
        if self._index >= len(self._frames):
            raise StopIteration
        frame = self._frames[self._index]
        self._index += 1
        return [frame], [self._meta]


class CalibrationPipelineTestCase(unittest.TestCase):
    """Kiểm tra pipeline điều phối và tạo đủ artifact đầu ra."""

    def test_pipeline_writes_baseline_and_previews(self) -> None:
        """Pipeline phải lưu NPZ, JSON cùng preview RGB và reference depth."""
        roi = RoiDefinition(
            normalized_points=np.array(
                [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                dtype=np.float32,
            )
        )
        pipeline = CalibrationPipeline(
            estimator=FakeEstimator(),
            config=CalibrationConfig(frame_count=5, process_width=0),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.npz"
            with (
                patch(
                    "walkway_monitor.calibration.pipeline.MediaSources",
                    FakeMediaSources,
                ),
                patch(
                    "walkway_monitor.calibration.pipeline.select_polygon",
                    return_value=roi,
                ),
                patch(
                    "walkway_monitor.calibration.pipeline.wait_for_empty_confirmation"
                ),
                patch("walkway_monitor.calibration.pipeline.cv2.imshow"),
                patch("walkway_monitor.calibration.pipeline.cv2.waitKey", return_value=-1),
                patch("walkway_monitor.calibration.pipeline.cv2.destroyWindow"),
                patch("walkway_monitor.calibration.pipeline.cv2.destroyAllWindows"),
            ):
                artifact = pipeline.run("video.mp4", output)
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_suffix(".json").is_file())
            self.assertTrue(output.with_suffix(".preview.jpg").is_file())
            self.assertTrue(output.with_suffix(".depth.jpg").is_file())
            self.assertEqual(artifact.frame_count, 5)
            self.assertEqual(artifact.source_type, "VIDEO")


if __name__ == "__main__":
    unittest.main()
