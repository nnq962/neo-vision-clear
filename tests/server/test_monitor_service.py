"""Kiểm thử vòng đời worker runtime độc lập với request FastAPI."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from server.models.calibration import CalibrationConfig
from server.models.camera import CameraConfig
from server.models.config import RuntimeConfig
from server.services.monitor import (
    MonitorService,
    RuntimeStartError,
)
from server.services.worker_resources import release_worker_memory
from server.settings import ServerSettings
from walkway_monitor.calibration.storage import artifact_path_for_id


class BlockingPipeline:
    """Pipeline giả chạy đến khi nhận stop event từ MonitorService."""

    def __init__(self, **_kwargs):
        """Tạo cờ để test biết worker đã đi vào vòng chạy."""
        self.started = threading.Event()

    # ─────────────────────────────────────────────────────────────────────────

    def run(self, _source, *, stop_event, **_kwargs) -> int:
        """Chờ tín hiệu dừng giống một nguồn camera chạy liên tục."""
        # Bước 1: công bố đã chạy rồi chờ có giới hạn để test không bị treo.
        self.started.set()
        stop_event.wait(timeout=2.0)
        return 1


class MonitorServiceTestCase(unittest.TestCase):
    """Xác nhận start/stop bất đồng bộ và cô lập lỗi worker."""

    def setUp(self) -> None:
        """Tạo camera, baseline và artifact tạm cho mỗi test."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.baselines_directory = Path(self.temporary_directory.name)
        timestamp = datetime.now(timezone.utc)
        self.camera = CameraConfig(
            id="camera-01",
            name="Camera",
            source="rtsp://camera.local/stream",
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.baseline = CalibrationConfig(
            id="baseline-01",
            camera_id=self.camera.id,
            name="Baseline",
            roi_points=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
            world_points=[[0, 0], [2, 0], [2, 6], [0, 6]],
            unit="m",
            origin="P1",
            x_axis="P1 → P2",
            y_axis="P1 → P4",
            encoder="vits",
            frame_count=60,
            input_size=518,
            process_width=960,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.runtime = RuntimeConfig(
            enabled=True,
            active_baseline_id=self.baseline.id,
        )
        artifact_path = artifact_path_for_id(
            self.baselines_directory,
            self.baseline.id,
        )
        artifact_path.parent.mkdir(parents=True)
        artifact_path.touch()
        self.load_patcher = patch(
            "server.services.monitor.load_baseline",
            return_value=SimpleNamespace(encoder="vits", input_size=518),
        )
        self.load_patcher.start()

    # ─────────────────────────────────────────────────────────────────────────

    def tearDown(self) -> None:
        """Dừng patch và xóa thư mục artifact tạm."""
        self.load_patcher.stop()
        self.temporary_directory.cleanup()

    # ─────────────────────────────────────────────────────────────────────────

    def _settings(self) -> ServerSettings:
        """Tạo settings trỏ tới thư mục baseline riêng của test."""
        return ServerSettings(
            baselines_directory=str(self.baselines_directory),
            worker_shutdown_timeout_seconds=3.0,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _wait_for_status(
        self,
        service: MonitorService,
        expected: str,
    ) -> None:
        """Chờ ngắn đến khi worker đạt trạng thái mong đợi."""
        # Bước 1: polling có deadline giúp lỗi test kết thúc thay vì treo process.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if service.status().status == expected:
                return
            time.sleep(0.01)
        self.fail(
            f"Runtime không đạt trạng thái '{expected}', "
            f"hiện tại là '{service.status().status}'."
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_start_returns_before_slow_model_finishes_loading(self) -> None:
        """Start chỉ tạo thread nên không chờ model nạp xong trong request."""
        release_estimator = threading.Event()
        pipeline = BlockingPipeline()

        def slow_estimator(**_kwargs):
            """Chặn nạp model giả đến khi test chủ động cho phép."""
            release_estimator.wait(timeout=2.0)
            return object()

        service = MonitorService(
            self._settings(),
            estimator_factory=slow_estimator,
            pipeline_factory=lambda **_kwargs: pipeline,
        )

        started_at = time.monotonic()
        response = service.start(self.camera, self.baseline, self.runtime)
        elapsed = time.monotonic() - started_at

        self.assertEqual(response.status, "starting")
        self.assertLess(elapsed, 0.2)
        release_estimator.set()
        self.assertTrue(pipeline.started.wait(timeout=1.0))
        service.stop(wait=False)
        self._wait_for_status(service, "stopped")

    # ─────────────────────────────────────────────────────────────────────────

    def test_stop_returns_without_waiting_for_worker_cleanup(self) -> None:
        """Stop API chỉ phát Event và không join worker trong request."""
        pipeline = BlockingPipeline()
        service = MonitorService(
            self._settings(),
            estimator_factory=lambda **_kwargs: object(),
            pipeline_factory=lambda **_kwargs: pipeline,
        )
        service.start(self.camera, self.baseline, self.runtime)
        self.assertTrue(pipeline.started.wait(timeout=1.0))

        stopped_at = time.monotonic()
        response = service.stop(wait=False)
        elapsed = time.monotonic() - stopped_at

        self.assertEqual(response.status, "stopping")
        self.assertLess(elapsed, 0.2)
        self._wait_for_status(service, "stopped")

    # ─────────────────────────────────────────────────────────────────────────

    def test_worker_exception_becomes_failed_status(self) -> None:
        """Exception khi nạp model được giữ trong worker và công bố qua status."""
        def broken_estimator(**_kwargs):
            """Mô phỏng checkpoint hoặc GPU không thể khởi tạo."""
            raise RuntimeError("Không nạp được model kiểm thử.")

        service = MonitorService(
            self._settings(),
            estimator_factory=broken_estimator,
        )

        response = service.start(self.camera, self.baseline, self.runtime)

        self.assertEqual(response.status, "starting")
        self._wait_for_status(service, "failed")
        self.assertEqual(service.status().error, "Không nạp được model kiểm thử.")

    # ─────────────────────────────────────────────────────────────────────────

    def test_stopped_is_published_only_after_memory_cleanup(self) -> None:
        """Worker giữ trạng thái stopping cho đến khi cleanup hoàn tất."""
        pipeline = BlockingPipeline()
        cleanup_started = threading.Event()
        release_cleanup = threading.Event()

        def slow_cleanup(_worker_name: str) -> None:
            """Giữ pha cleanup để test quan sát được trạng thái trung gian."""
            cleanup_started.set()
            release_cleanup.wait(timeout=2.0)

        service = MonitorService(
            self._settings(),
            estimator_factory=lambda **_kwargs: object(),
            pipeline_factory=lambda **_kwargs: pipeline,
        )
        with patch("server.services.monitor.release_worker_memory", slow_cleanup):
            service.start(self.camera, self.baseline, self.runtime)
            self.assertTrue(pipeline.started.wait(timeout=1.0))
            service.stop(wait=False)
            self.assertTrue(cleanup_started.wait(timeout=1.0))

            self.assertEqual(service.status().status, "stopping")
            release_cleanup.set()
            self._wait_for_status(service, "stopped")

    # ─────────────────────────────────────────────────────────────────────────

    def test_memory_cleanup_collects_python_and_cuda_cache(self) -> None:
        """Cleanup gọi GC và trả cache CUDA khi accelerator khả dụng."""
        with (
            patch("server.services.worker_resources.gc.collect") as collect,
            patch(
                "server.services.worker_resources.torch.cuda.is_available",
                return_value=True,
            ),
            patch(
                "server.services.worker_resources.torch.cuda.empty_cache"
            ) as empty_cache,
        ):
            release_worker_memory("runtime")

        collect.assert_called_once_with()
        empty_cache.assert_called_once_with()

    # ─────────────────────────────────────────────────────────────────────────

    def test_start_rejects_missing_artifact_before_creating_thread(self) -> None:
        """Baseline chưa hoàn tất bị từ chối đồng bộ với lỗi nghiệp vụ rõ ràng."""
        missing = self.baseline.model_copy(update={"id": "missing"})
        service = MonitorService(self._settings())

        with self.assertRaises(RuntimeStartError):
            service.start(self.camera, missing, self.runtime)

        self.assertEqual(service.status().status, "stopped")


if __name__ == "__main__":
    unittest.main()
