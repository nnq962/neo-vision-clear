"""Kiểm thử worker calibration headless và artifact theo baseline ID."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from server.models.calibration import CalibrationCreate
from server.models.camera import CameraCreate
from server.services.calibration import CalibrationService
from server.services.config_store import ConfigStore
from server.settings import ServerSettings


class FakeEstimator:
    """Estimator nhẹ thay cho Depth Anything trong test service."""

    def __init__(self, **_options):
        """Chấp nhận cấu hình model nhưng không nạp checkpoint."""

    # ─────────────────────────────────────────────────────────────────────────

    def predict(self, frame: np.ndarray) -> np.ndarray:
        """Trả gradient depth xác định cùng kích thước frame."""
        height, width = frame.shape[:2]
        return np.linspace(0.1, 2.0, height * width, dtype=np.float32).reshape(
            height,
            width,
        )


class FakeMediaSources:
    """Nguồn giả cung cấp frame đầu và năm frame calibration."""

    def __init__(self, _source, **_options):
        """Tạo batch frame cố định không mở camera thật."""
        self._index = 0
        self._frames = [np.zeros((20, 30, 3), dtype=np.uint8) for _ in range(6)]
        self._meta = SimpleNamespace(source_type=SimpleNamespace(name="RTSP"))

    # ─────────────────────────────────────────────────────────────────────────

    def __enter__(self):
        """Trả nguồn giả khi vào context manager."""
        return self

    # ─────────────────────────────────────────────────────────────────────────

    def __exit__(self, *_args) -> None:
        """Không cần giải phóng tài nguyên trong nguồn giả."""

    # ─────────────────────────────────────────────────────────────────────────

    def __next__(self):
        """Trả từng frame cho tới khi hết dữ liệu giả."""
        if self._index >= len(self._frames):
            raise StopIteration
        frame = self._frames[self._index]
        self._index += 1
        return [frame], [self._meta]


class CalibrationServiceTestCase(unittest.TestCase):
    """Xác nhận service chạy nền và lưu đúng bộ artifact."""

    def test_creates_artifacts_and_reports_completion(self) -> None:
        """Worker hoàn tất phải tạo NPZ, JSON và hai ảnh preview."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ConfigStore(root / "config.json")
            camera = store.create_camera(
                CameraCreate(name="Camera", source="rtsp://camera.local/stream")
            )
            baseline = store.create_baseline(
                camera.id,
                CalibrationCreate(
                    name="Baseline test",
                    roi_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                    world_points=[(0, 0), (2, 0), (2, 6), (0, 6)],
                    frame_count=5,
                    process_width=0,
                ),
            )
            settings = ServerSettings(
                camera_config_path=str(root / "config.json"),
                baselines_directory=str(root / "baselines"),
            )
            service = CalibrationService(
                settings,
                store,
                estimator_factory=FakeEstimator,
            )

            # Worker dùng nguồn và estimator giả nhưng chạy pipeline thật.
            with (
                patch(
                    "walkway_monitor.calibration.pipeline.MediaSources",
                    FakeMediaSources,
                ),
                patch(
                    "walkway_monitor.calibration.pipeline.cv2.imshow"
                ) as imshow_mock,
            ):
                started = service.start(baseline.id)
                result = started
                for _attempt in range(100):
                    result = service.status(baseline.id)
                    if result.status != "running":
                        break
                    time.sleep(0.01)
                service.stop()

            baseline_directory = root / "baselines" / baseline.id
            artifact = baseline_directory / "baseline.npz"
            self.assertEqual(started.status, "running")
            self.assertEqual(result.status, "completed")
            self.assertTrue(result.artifact_available)
            self.assertTrue(artifact.is_file())
            self.assertTrue(artifact.with_suffix(".json").is_file())
            self.assertTrue(artifact.with_suffix(".preview.jpg").is_file())
            self.assertTrue(artifact.with_suffix(".depth.jpg").is_file())
            self.assertEqual(
                sorted(path.name for path in baseline_directory.iterdir()),
                [
                    "baseline.depth.jpg",
                    "baseline.json",
                    "baseline.npz",
                    "baseline.preview.jpg",
                ],
            )
            self.assertEqual(
                service.get_artifact_image_path(baseline.id, "preview"),
                artifact.with_suffix(".preview.jpg"),
            )
            self.assertEqual(
                service.get_artifact_image_path(baseline.id, "depth"),
                artifact.with_suffix(".depth.jpg"),
            )
            imshow_mock.assert_not_called()

    # ─────────────────────────────────────────────────────────────────────────

    def test_recognizes_legacy_flat_artifact_after_restart(self) -> None:
        """Service vẫn nhận artifact phẳng cũ là một calibration hoàn tất."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ConfigStore(root / "config.json")
            camera = store.create_camera(
                CameraCreate(name="Camera", source="rtsp://camera.local/stream")
            )
            baseline = store.create_baseline(
                camera.id,
                CalibrationCreate(
                    name="Baseline cũ",
                    roi_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                    world_points=[(0, 0), (2, 0), (2, 6), (0, 6)],
                    frame_count=5,
                    process_width=0,
                ),
            )
            baselines_directory = root / "baselines"
            baselines_directory.mkdir()
            (baselines_directory / f"{baseline.id}.npz").touch()
            service = CalibrationService(
                ServerSettings(
                    camera_config_path=str(root / "config.json"),
                    baselines_directory=str(baselines_directory),
                ),
                store,
                estimator_factory=FakeEstimator,
            )

            result = service.status(baseline.id)

            self.assertEqual(result.status, "completed")
            self.assertTrue(result.artifact_available)


if __name__ == "__main__":
    unittest.main()
