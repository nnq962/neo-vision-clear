"""Service chạy calibration headless trong một worker nền."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable

import numpy as np

from server.models.calibration import CalibrationRunResponse
from server.services.config_store import CameraNotFoundError, ConfigStore
from server.services.worker_resources import release_worker_memory
from server.settings import ServerSettings
from utils.logger import LOGGER
from walkway_monitor.calibration.pipeline import CalibrationPipeline
from walkway_monitor.calibration.storage import (
    artifact_path_for_id,
    delete_artifacts_for_id,
)
from walkway_monitor.config import (
    CalibrationConfig as PipelineCalibrationConfig,
    default_checkpoint_path,
)
from walkway_monitor.depth.estimator import DepthAnythingEstimator, DepthEstimator
from walkway_monitor.models import RoiDefinition, WorldCoordinates


EstimatorFactory = Callable[..., DepthEstimator]


class CalibrationBusyError(RuntimeError):
    """Báo lỗi khi một calibration khác đang chạy."""


class CalibrationCameraError(RuntimeError):
    """Báo lỗi khi baseline không khớp camera hiện tại."""


class CalibrationArtifactNotFoundError(FileNotFoundError):
    """Báo lỗi khi ảnh kết quả của baseline chưa tồn tại."""


@dataclass
class _JobState:
    """State nội bộ có thể cập nhật dưới lock của service."""

    baseline_id: str
    status: str
    processed_frames: int
    total_frames: int
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_available: bool = False
    noise_p99: float | None = None
    alignment_median_error: float | None = None


class CalibrationService:
    """Điều phối tối đa một công việc calibration tại một thời điểm."""

    def __init__(
        self,
        settings: ServerSettings,
        config_store: ConfigStore,
        estimator_factory: EstimatorFactory = DepthAnythingEstimator,
    ):
        """Lưu dependency và khởi tạo worker ở trạng thái rảnh."""
        self.settings = settings
        self.config_store = config_store
        self._estimator_factory = estimator_factory
        self._lock = Lock()
        self._jobs: dict[str, _JobState] = {}
        self._thread: Thread | None = None
        self._stop_event = Event()

    # ─────────────────────────────────────────────────────────────────────────

    def start(self, baseline_id: str) -> CalibrationRunResponse:
        """Khởi động calibration headless và trả trạng thái ban đầu."""
        # Bước 1: sao chép cấu hình trước khi chiếm slot worker.
        baseline = self.config_store.get_baseline(baseline_id)
        try:
            camera = self.config_store.get_camera(baseline.camera_id)
        except CameraNotFoundError as exc:
            raise CalibrationCameraError(
                "Camera của baseline không còn tồn tại; hãy tạo baseline mới."
            ) from exc
        with self._lock:
            # Bước 2: MVP chỉ cho một model calibration chạy để tránh tranh GPU.
            if self._thread is not None and self._thread.is_alive():
                raise CalibrationBusyError("Một baseline khác đang được calibration.")
            state = _JobState(
                baseline_id=baseline.id,
                status="running",
                processed_frames=0,
                total_frames=baseline.frame_count,
                started_at=datetime.now(timezone.utc),
            )
            self._jobs[baseline.id] = state
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                args=(
                    baseline,
                    self._camera_stream_url(camera.id),
                    camera.open_timeout_ms,
                    camera.read_timeout_ms,
                ),
                daemon=True,
                name=f"calibration-{baseline.id}",
            )
            self._thread.start()
            return self._to_response(state)

    # ─────────────────────────────────────────────────────────────────────────

    def status(self, baseline_id: str) -> CalibrationRunResponse:
        """Trả trạng thái bộ nhớ hoặc suy ra từ artifact đã tồn tại."""
        baseline = self.config_store.get_baseline(baseline_id)
        with self._lock:
            state = self._jobs.get(baseline_id)
            if state is not None:
                return self._to_response(state)

        # Bước 1: sau restart, file NPZ hoàn chỉnh là bằng chứng calibration xong.
        artifact_exists = self._artifact_path(baseline_id).is_file()
        status = "completed" if artifact_exists else "idle"
        return CalibrationRunResponse(
            baseline_id=baseline_id,
            status=status,
            processed_frames=baseline.frame_count if status == "completed" else 0,
            total_frames=baseline.frame_count,
            artifact_available=status == "completed",
        )

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Yêu cầu công việc hiện tại dừng khi application shutdown."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            # Bước 1: chờ có giới hạn vì đọc camera có thể đang block theo timeout.
            thread.join(timeout=self.settings.worker_shutdown_timeout_seconds)
            if thread.is_alive():
                LOGGER.warning("Calibration worker chưa dừng trước khi hết timeout.")

    # ─────────────────────────────────────────────────────────────────────────

    def delete_artifacts(self, baseline_id: str) -> tuple[Path, ...]:
        """Xóa bộ artifact của baseline khi không có calibration đang chạy."""
        with self._lock:
            # Bước 1: không cho xóa file mà worker hiện tại có thể đang ghi.
            state = self._jobs.get(baseline_id)
            if state is not None and state.status == "running":
                raise CalibrationBusyError(
                    "Không thể xóa baseline đang được calibration."
                )

            # Bước 2: dọn thư mục artifact của baseline đã chọn.
            return delete_artifacts_for_id(
                self.settings.baselines_directory,
                baseline_id,
            )

    # ─────────────────────────────────────────────────────────────────────────

    def get_artifact_image_path(self, baseline_id: str, image_type: str) -> Path:
        """Trả đường dẫn ảnh preview hoặc depth của một baseline đã hoàn tất."""
        # Bước 1: giới hạn loại ảnh vào hai artifact công khai được hỗ trợ.
        suffixes = {
            "preview": ".preview.jpg",
            "depth": ".depth.jpg",
        }
        suffix = suffixes.get(image_type)
        if suffix is None:
            raise ValueError(f"Loại ảnh artifact không được hỗ trợ: {image_type}")

        # Bước 2: chỉ dùng ảnh trong thư mục artifact chuẩn của baseline.
        image_path = self._artifact_path(baseline_id).with_suffix(suffix)
        if image_path.is_file():
            return image_path
        raise CalibrationArtifactNotFoundError(
            f"Baseline '{baseline_id}' chưa có ảnh {image_type}."
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _run(
        self,
        baseline,
        source: str,
        open_timeout_ms: int,
        read_timeout_ms: int,
    ) -> None:
        """Nạp model, chạy pipeline headless và cập nhật kết quả worker."""
        estimator = None
        pipeline = None
        try:
            # Bước 1: chuyển cấu hình API thành các model miền calibration.
            config = PipelineCalibrationConfig(
                frame_count=baseline.frame_count,
                input_size=baseline.input_size,
                process_width=baseline.process_width,
                encoder=baseline.encoder,
            )
            roi = RoiDefinition(
                normalized_points=np.asarray(baseline.roi_points, dtype=np.float32),
                world_coordinates=WorldCoordinates(
                    points=np.asarray(baseline.world_points, dtype=np.float32),
                    unit=baseline.unit,
                    origin=baseline.origin,
                    x_axis=baseline.x_axis,
                    y_axis=baseline.y_axis,
                ),
            )
            checkpoint = (
                self.settings.checkpoint_path
                or default_checkpoint_path(baseline.encoder)
            )
            estimator = self._estimator_factory(
                checkpoint=checkpoint,
                encoder=baseline.encoder,
                input_size=baseline.input_size,
            )

            # Bước 2: chạy không display và lưu artifact theo ID ổn định.
            pipeline = CalibrationPipeline(estimator=estimator, config=config)
            artifact = pipeline.run(
                source=source,
                output_path=self._artifact_path(baseline.id),
                roi=roi,
                display=False,
                stop_event=self._stop_event,
                on_progress=lambda current, total: self._set_progress(
                    baseline.id,
                    current,
                    total,
                ),
                open_timeout_ms=open_timeout_ms,
                read_timeout_ms=read_timeout_ms,
            )

            # Bước 3: công bố thống kê chỉ sau khi toàn bộ artifact đã lưu xong.
            with self._lock:
                state = self._jobs[baseline.id]
                state.status = "completed"
                state.processed_frames = state.total_frames
                state.completed_at = datetime.now(timezone.utc)
                state.artifact_available = True
                state.noise_p99 = artifact.noise_p99
                state.alignment_median_error = artifact.alignment_median_error
        except Exception as exc:
            LOGGER.exception("Calibration baseline '%s' thất bại.", baseline.id)
            with self._lock:
                state = self._jobs[baseline.id]
                state.status = "failed"
                state.error = str(exc)
                state.completed_at = datetime.now(timezone.utc)
        finally:
            # Bước 4: bỏ model/pipeline rồi trả CUDA cache như worker runtime.
            pipeline = None
            estimator = None
            release_worker_memory("calibration")

    # ─────────────────────────────────────────────────────────────────────────

    def _set_progress(self, baseline_id: str, current: int, total: int) -> None:
        """Cập nhật tiến độ frame dưới lock từ calibration worker."""
        with self._lock:
            state = self._jobs.get(baseline_id)
            if state is not None:
                state.processed_frames = current
                state.total_frames = total

    # ─────────────────────────────────────────────────────────────────────────

    def _artifact_path(self, baseline_id: str) -> Path:
        """Tạo đường dẫn NPZ trong thư mục riêng của một baseline."""
        # Bước 1: dùng helper chung để mọi consumer tuân theo cùng layout.
        return artifact_path_for_id(
            self.settings.baselines_directory,
            baseline_id,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _camera_stream_url(self, camera_id: str) -> str:
        """Tạo URL RTSP nội bộ từ path camera đã đăng ký trên MediaMTX."""
        # Bước 1: tái sử dụng một kết nối camera qua MediaMTX thay vì kéo source lần hai.
        return f"{self.settings.mediamtx_rtsp_url.rstrip('/')}/{camera_id}"

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_response(state: _JobState) -> CalibrationRunResponse:
        """Sao chép state nội bộ thành response Pydantic bất biến với caller."""
        # Bước 1: dựng payload tách rời để request không giữ tham chiếu worker.
        return CalibrationRunResponse(
            baseline_id=state.baseline_id,
            status=state.status,
            processed_frames=state.processed_frames,
            total_frames=state.total_frames,
            error=state.error,
            started_at=state.started_at,
            completed_at=state.completed_at,
            artifact_available=state.artifact_available,
            noise_p99=state.noise_p99,
            alignment_median_error=state.alignment_median_error,
        )
