"""Service sở hữu model, nguồn media và worker phân tích nền."""

from __future__ import annotations

from pathlib import Path
import threading

from utils.logger import LOGGER
from server.settings import ServerSettings
from server.services.snapshot_store import SnapshotStore
from walkway_monitor.calibration.storage import load_baseline
from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.estimator import DepthAnythingEstimator
from walkway_monitor.detection.pipeline import DetectionPipeline


class MonitorService:
    """Chạy pipeline thị giác trong thread và công bố snapshot mới nhất."""

    # ─────────────────────────────────────────────────────────────────────────

    def __init__(self, settings: ServerSettings):
        """Lưu cấu hình và tạo state điều phối chưa khởi động."""
        settings.validate()
        self.settings = settings
        self.snapshot_store = SnapshotStore()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pipeline: DetectionPipeline | None = None

    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Nạp baseline, model và khởi động worker camera đúng một lần."""
        if self._thread is not None and self._thread.is_alive():
            return

        # Bước 1: nạp tài nguyên nặng trong lifespan thay vì tại thời điểm import.
        baseline = load_baseline(self.settings.baseline_path)
        checkpoint = self.settings.checkpoint_path or str(
            Path("weights") / f"depth_anything_v2_{baseline.encoder}.pth"
        )
        estimator = DepthAnythingEstimator(
            checkpoint=checkpoint,
            encoder=baseline.encoder,
            input_size=baseline.input_size,
        )
        self._pipeline = DetectionPipeline(
            estimator=estimator,
            baseline=baseline,
            config=DetectionConfig(),
            display=False,
            log_interval=self.settings.log_interval,
        )

        # Bước 2: worker riêng giữ inference blocking nằm ngoài event loop FastAPI.
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="walkway-monitor-worker",
        )
        self._thread.start()
        LOGGER.info("Đã khởi động worker phân tích lối đi cho FastAPI.")

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Yêu cầu worker dừng và chờ nguồn media được giải phóng."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            timeout = max(self.settings.read_timeout_ms / 1000 + 2.0, 3.0)
            thread.join(timeout=timeout)
            if thread.is_alive():
                LOGGER.warning("Worker camera chưa dừng trước khi hết timeout.")
        self._thread = None
        self._pipeline = None

    # ─────────────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Chạy pipeline tới khi shutdown, hết nguồn hoặc phát sinh lỗi."""
        pipeline = self._pipeline
        if pipeline is None:
            self.snapshot_store.set_error("Pipeline chưa được khởi tạo.")
            return
        try:
            # Công bố mỗi snapshot trực tiếp vào store thread-safe.
            pipeline.run(
                self.settings.source,
                stop_event=self._stop_event,
                on_snapshot=self.snapshot_store.publish,
                use_gstreamer=self.settings.use_gstreamer,
                open_timeout_ms=self.settings.open_timeout_ms,
                read_timeout_ms=self.settings.read_timeout_ms,
            )
            if not self._stop_event.is_set():
                self.snapshot_store.set_error("Nguồn media đã kết thúc.")
        except Exception as exc:
            LOGGER.exception("Worker phân tích lối đi đã dừng do lỗi.")
            self.snapshot_store.set_error(str(exc))
