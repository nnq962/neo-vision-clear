"""Cấu hình runtime và HTTP server lấy từ biến môi trường."""

from __future__ import annotations

from dataclasses import dataclass
import os

from walkway_monitor.config import DEFAULT_BASELINES_DIRECTORY


@dataclass(frozen=True)
class ServerSettings:
    """Nhóm cấu hình cần để khởi động FastAPI và worker camera."""

    camera_config_path: str = "data/config.json"
    baselines_directory: str = DEFAULT_BASELINES_DIRECTORY
    mediamtx_rtsp_url: str = "rtsp://127.0.0.1:8554"
    checkpoint_path: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    snapshot_max_age_seconds: float = 2.0
    worker_shutdown_timeout_seconds: float = 7.0

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Tạo cấu hình hạ tầng server từ các biến môi trường của process."""
        # Bước 1: camera và runtime nghiệp vụ nằm trong config JSON; biến môi
        # trường chỉ còn quản lý hạ tầng của chính process server.
        checkpoint = os.getenv("WALKWAY_CHECKPOINT") or None
        return cls(
            camera_config_path=os.getenv(
                "NVC_CONFIG_PATH",
                "data/config.json",
            ),
            baselines_directory=os.getenv(
                "NVC_BASELINES_PATH",
                DEFAULT_BASELINES_DIRECTORY,
            ),
            mediamtx_rtsp_url=os.getenv(
                "MEDIAMTX_RTSP_URL",
                "rtsp://127.0.0.1:8554",
            ),
            checkpoint_path=checkpoint,
            host=os.getenv("WALKWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("WALKWAY_PORT", "8000")),
            snapshot_max_age_seconds=float(
                os.getenv("WALKWAY_SNAPSHOT_MAX_AGE_SECONDS", "2.0")
            ),
            worker_shutdown_timeout_seconds=float(
                os.getenv("WALKWAY_WORKER_SHUTDOWN_TIMEOUT_SECONDS", "7.0")
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra cấu hình trước khi FastAPI khởi động worker."""
        if not self.camera_config_path.strip():
            raise ValueError("camera_config_path không được để trống.")
        if not self.baselines_directory.strip():
            raise ValueError("baselines_directory không được để trống.")
        if not self.mediamtx_rtsp_url.strip():
            raise ValueError("mediamtx_rtsp_url không được để trống.")
        if not 1 <= self.port <= 65535:
            raise ValueError("port phải nằm trong [1, 65535].")
        if self.snapshot_max_age_seconds <= 0:
            raise ValueError("snapshot_max_age_seconds phải là số dương.")
        if self.worker_shutdown_timeout_seconds <= 0:
            raise ValueError("worker_shutdown_timeout_seconds phải là số dương.")
