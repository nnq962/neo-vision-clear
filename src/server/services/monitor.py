"""Service điều phối worker runtime độc lập với vòng đời FastAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Callable, Literal

from server.models.calibration import CalibrationConfig
from server.models.camera import CameraConfig
from server.models.config import RuntimeConfig, RuntimeProcessResponse
from server.services.snapshot_store import SnapshotRead, SnapshotStore
from server.services.worker_resources import release_worker_memory
from server.settings import ServerSettings
from utils.logger import LOGGER
from walkway_monitor.calibration.storage import (
    artifact_path_for_id,
    legacy_artifact_path_for_id,
    load_baseline,
)
from walkway_monitor.config import default_checkpoint_path
from walkway_monitor.depth.estimator import DepthAnythingEstimator, DepthEstimator
from walkway_monitor.detection.models import DetectionOutput
from walkway_monitor.detection.pipeline import DetectionPipeline
from walkway_monitor.detection.zones import extract_difference_zones


EstimatorFactory = Callable[..., DepthEstimator]
PipelineFactory = Callable[..., DetectionPipeline]
RuntimeState = Literal["stopped", "starting", "running", "stopping", "failed"]


class RuntimeBusyError(RuntimeError):
    """Báo lỗi khi worker đang chạy hoặc đang dừng."""


class RuntimeStartError(RuntimeError):
    """Báo lỗi cấu hình khiến runtime chưa thể bắt đầu."""


class MonitorService:
    """Nạp model và chạy detection trong một thread nền có thể điều khiển."""

    # ─────────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        settings: ServerSettings,
        estimator_factory: EstimatorFactory = DepthAnythingEstimator,
        pipeline_factory: PipelineFactory = DetectionPipeline,
    ):
        """Lưu dependency và khởi tạo state worker ở trạng thái dừng."""
        settings.validate()
        self.settings = settings
        self.snapshot_store = SnapshotStore()
        self._estimator_factory = estimator_factory
        self._pipeline_factory = pipeline_factory
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pipeline: DetectionPipeline | None = None
        self._state: RuntimeState = "stopped"
        self._active_baseline_id: str | None = None
        self._error: str | None = None
        self._started_at: datetime | None = None
        self._snapshot_max_age_seconds = settings.snapshot_max_age_seconds

    # ─────────────────────────────────────────────────────────────────────────

    def start(
        self,
        camera: CameraConfig,
        baseline: CalibrationConfig,
        runtime: RuntimeConfig,
    ) -> RuntimeProcessResponse:
        """Khởi tạo thread runtime và trả ngay mà không nạp model trong request."""
        # Bước 1: kiểm tra quan hệ và artifact trước khi chiếm slot worker.
        if baseline.camera_id != camera.id:
            raise RuntimeStartError("Baseline không thuộc camera hiện tại.")
        artifact_path = self._resolve_artifact_path(baseline.id)

        with self._lock:
            # Bước 2: không cho hai worker dùng chung model, camera và GPU.
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeBusyError("Runtime đang chạy hoặc đang dừng.")

            self.snapshot_store.reset()
            self._stop_event.clear()
            self._state = "starting"
            self._active_baseline_id = baseline.id
            self._error = None
            self._started_at = datetime.now(timezone.utc)
            self._snapshot_max_age_seconds = runtime.snapshot_max_age_seconds
            self._thread = threading.Thread(
                target=self._run,
                args=(camera, baseline, runtime, artifact_path),
                daemon=True,
                name="walkway-monitor-worker",
            )
            self._thread.start()
            return self._status_unlocked()

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self, wait: bool = True) -> RuntimeProcessResponse:
        """Phát tín hiệu dừng; chỉ chờ có giới hạn khi shutdown application."""
        with self._lock:
            # Bước 1: stop là idempotent khi worker đã kết thúc hoặc chưa chạy.
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._state = "stopped"
                self._active_baseline_id = None
                self._error = None
                self.snapshot_store.reset()
                return self._status_unlocked()

            self._stop_event.set()
            self._state = "stopping"
            response = self._status_unlocked()

        # Bước 2: API dùng wait=False nên không bị giữ bởi camera hoặc inference.
        if wait:
            thread.join(timeout=self.settings.worker_shutdown_timeout_seconds)
            if thread.is_alive():
                LOGGER.warning("Worker runtime chưa dừng trước khi hết timeout.")
        return response

    # ─────────────────────────────────────────────────────────────────────────

    def status(self) -> RuntimeProcessResponse:
        """Trả bản sao trạng thái worker cùng tuổi snapshot mới nhất."""
        with self._lock:
            return self._status_unlocked()

    # ─────────────────────────────────────────────────────────────────────────

    def read_snapshot(self) -> SnapshotRead:
        """Đọc snapshot theo ngưỡng tuổi của đúng phiên runtime hiện tại."""
        with self._lock:
            maximum_age_seconds = self._snapshot_max_age_seconds
        return self.snapshot_store.read(maximum_age_seconds)

    # ─────────────────────────────────────────────────────────────────────────

    def _run(
        self,
        camera: CameraConfig,
        baseline_config: CalibrationConfig,
        runtime: RuntimeConfig,
        artifact_path: Path,
    ) -> None:
        """Nạp tài nguyên và chạy pipeline, giữ mọi exception trong worker."""
        try:
            # Bước 1: toàn bộ thao tác nặng được thực hiện ngoài request FastAPI.
            baseline = load_baseline(artifact_path)
            checkpoint = (
                self.settings.checkpoint_path
                or default_checkpoint_path(baseline.encoder)
            )
            estimator = self._estimator_factory(
                checkpoint=checkpoint,
                encoder=baseline.encoder,
                input_size=baseline.input_size,
            )
            pipeline = self._pipeline_factory(
                estimator=estimator,
                baseline=baseline,
                config=runtime.detection.to_detection_config(),
                display=False,
                log_interval=runtime.log_interval_seconds,
            )
            with self._lock:
                self._pipeline = pipeline
                if self._stop_event.is_set():
                    self._state = "stopping"
                else:
                    self._state = "running"

            # Stop có thể đến trong lúc model đang nạp; không mở camera sau đó.
            if self._stop_event.is_set():
                return

            # Bước 2: pipeline hợp tác dừng qua Event và tự đóng MediaSources.
            pipeline.run(
                self._camera_stream_url(camera.id),
                stop_event=self._stop_event,
                on_output=self._publish_output,
                open_timeout_ms=camera.open_timeout_ms,
                read_timeout_ms=camera.read_timeout_ms,
            )
            with self._lock:
                if self._stop_event.is_set():
                    self._state = "stopping"
                else:
                    self._state = "failed"
                    self._error = "Nguồn media đã kết thúc."
                    self.snapshot_store.set_error(self._error)
        except Exception as exc:
            # Bước 3: lỗi model/camera chỉ làm worker failed, không thoát FastAPI.
            LOGGER.exception(
                "Runtime với baseline '%s' đã dừng do lỗi.",
                baseline_config.id,
            )
            with self._lock:
                if self._stop_event.is_set():
                    self._error = None
                else:
                    self._state = "failed"
                    self._error = str(exc)
                    self.snapshot_store.set_error(self._error)
        finally:
            # Bước 4: bỏ cả tham chiếu service lẫn local trước khi dọn allocator.
            with self._lock:
                self._pipeline = None
            pipeline = None
            estimator = None
            baseline = None
            release_worker_memory("runtime")

            # Bước 5: chỉ công bố stopped sau khi camera, model và cache đã dọn.
            with self._lock:
                if self._stop_event.is_set():
                    self._state = "stopped"
                    self._active_baseline_id = None
                    self.snapshot_store.reset()
                self._thread = None

    # ─────────────────────────────────────────────────────────────────────────

    def _publish_output(self, output: DetectionOutput) -> None:
        """Chuyển mask thành zone gọn nhẹ rồi công bố atomically cùng snapshot."""
        # Bước 1: giới hạn polygon trước khi đưa vào store dùng chung với WebSocket.
        zones = extract_difference_zones(
            output.changed_mask,
            maximum_zones=20,
            maximum_vertices=32,
        )
        self.snapshot_store.publish(output.snapshot, zones)

    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_artifact_path(self, baseline_id: str) -> Path:
        """Tìm NPZ theo layout thư mục hiện tại rồi thử layout phẳng cũ."""
        # Bước 1: ưu tiên artifact chuẩn để mọi baseline được cô lập theo ID.
        candidates = (
            artifact_path_for_id(self.settings.baselines_directory, baseline_id),
            legacy_artifact_path_for_id(
                self.settings.baselines_directory,
                baseline_id,
            ),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise RuntimeStartError(
            f"Baseline '{baseline_id}' chưa có artifact hoàn chỉnh."
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _camera_stream_url(self, camera_id: str) -> str:
        """Tạo URL RTSP nội bộ từ path camera trên MediaMTX."""
        # Bước 1: runtime đọc path đã đăng ký thay vì mở thêm source gốc.
        return f"{self.settings.mediamtx_rtsp_url.rstrip('/')}/{camera_id}"

    # ─────────────────────────────────────────────────────────────────────────

    def _status_unlocked(self) -> RuntimeProcessResponse:
        """Dựng response trạng thái khi caller đang giữ lock của service."""
        # Bước 1: tuổi snapshot chỉ là metadata, không làm thay đổi state worker.
        reading = self.snapshot_store.read(self._snapshot_max_age_seconds)
        return RuntimeProcessResponse(
            status=self._state,
            active_baseline_id=self._active_baseline_id,
            snapshot_age_ms=reading.age_ms,
            error=self._error,
            started_at=self._started_at,
        )
