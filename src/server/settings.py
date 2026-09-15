"""Cấu hình runtime và HTTP server lấy từ biến môi trường."""

from __future__ import annotations

from dataclasses import dataclass
import os

from walkway_monitor.config import DEFAULT_BASELINE_PATH, DEFAULT_BASELINES_DIRECTORY


@dataclass(frozen=True)
class ServerSettings:
    """Nhóm cấu hình cần để khởi động FastAPI và worker camera."""

    source: str | int = 0
    camera_config_path: str = "data/config.json"
    baselines_directory: str = DEFAULT_BASELINES_DIRECTORY
    mediamtx_rtsp_url: str = "rtsp://127.0.0.1:8554"
    baseline_path: str = DEFAULT_BASELINE_PATH
    checkpoint_path: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    snapshot_max_age_seconds: float = 2.0
    open_timeout_ms: int = 5000
    read_timeout_ms: int = 5000
    log_interval: float = 2.0

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Tạo cấu hình từ các biến môi trường WALKWAY_* của process."""
        # Bước 1: chuyển source chỉ gồm chữ số thành webcam index.
        source_value = os.getenv("WALKWAY_SOURCE", "0")
        source: str | int = (
            int(source_value) if source_value.isdigit() else source_value
        )

        # Bước 2: đọc các giá trị còn lại và dùng mặc định an toàn cho server.
        checkpoint = os.getenv("WALKWAY_CHECKPOINT") or None
        return cls(
            source=source,
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
            baseline_path=os.getenv(
                "WALKWAY_BASELINE",
                DEFAULT_BASELINE_PATH,
            ),
            checkpoint_path=checkpoint,
            host=os.getenv("WALKWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("WALKWAY_PORT", "8000")),
            snapshot_max_age_seconds=float(
                os.getenv("WALKWAY_SNAPSHOT_MAX_AGE_SECONDS", "2.0")
            ),
            open_timeout_ms=int(os.getenv("WALKWAY_OPEN_TIMEOUT_MS", "5000")),
            read_timeout_ms=int(os.getenv("WALKWAY_READ_TIMEOUT_MS", "5000")),
            log_interval=float(os.getenv("WALKWAY_LOG_INTERVAL", "2.0")),
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
        if not str(self.baseline_path).strip():
            raise ValueError("baseline_path không được để trống.")
        if not 1 <= self.port <= 65535:
            raise ValueError("port phải nằm trong [1, 65535].")
        if self.snapshot_max_age_seconds <= 0:
            raise ValueError("snapshot_max_age_seconds phải là số dương.")
        if self.open_timeout_ms < 0 or self.read_timeout_ms < 0:
            raise ValueError("Timeout media không được âm.")
        if self.log_interval < 0:
            raise ValueError("log_interval không được âm.")
