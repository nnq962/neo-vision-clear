"""Cấu hình hạ tầng từ môi trường và model mặc định từ config JSON."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from server.models.config import ModelConfig

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = str(BACKEND_DIRECTORY / "data" / "config.json")
DEFAULT_BASELINES_DIRECTORY = str(BACKEND_DIRECTORY / "data" / "baselines")
DEFAULT_TENSORRT_ENGINE_DIRECTORY = str(BACKEND_DIRECTORY / "weights" / "tensorrt")


@dataclass(frozen=True)
class ServerSettings:
    """Nhóm cấu hình cần để khởi động FastAPI và worker camera."""

    camera_config_path: str = DEFAULT_CONFIG_PATH
    baselines_directory: str = DEFAULT_BASELINES_DIRECTORY
    mediamtx_rtsp_url: str = "rtsp://127.0.0.1:8554"
    checkpoint_path: str | None = None
    depth_backend: str = "pytorch"
    tensorrt_engine_path: str | None = None
    tensorrt_engine_directory: str = DEFAULT_TENSORRT_ENGINE_DIRECTORY
    host: str = "0.0.0.0"
    port: int = 8000
    snapshot_max_age_seconds: float = 2.0
    worker_shutdown_timeout_seconds: float = 7.0
    jetson_id: str = "jetson-a"
    aggregator_ws_base_url: str | None = None
    aggregator_reconnect_seconds: float = 2.0

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Tạo cấu hình server và đọc model mặc định từ config JSON."""
        # Bước 1: camera và runtime nghiệp vụ nằm trong config JSON; biến môi
        # trường chỉ còn quản lý hạ tầng của chính process server.
        checkpoint = os.getenv("WALKWAY_CHECKPOINT") or None
        aggregator_url = os.getenv("NVC_AGGREGATOR_WS_BASE_URL", "").strip()
        config_path = os.getenv("NVC_CONFIG_PATH", DEFAULT_CONFIG_PATH)
        try:
            with Path(config_path).open(encoding="utf-8") as source:
                model_config = ModelConfig.model_validate(json.load(source).get("model", {}))
        except FileNotFoundError:
            model_config = ModelConfig()
        return cls(
            camera_config_path=config_path,
            baselines_directory=os.getenv(
                "NVC_BASELINES_PATH",
                DEFAULT_BASELINES_DIRECTORY,
            ),
            mediamtx_rtsp_url=os.getenv(
                "MEDIAMTX_RTSP_URL",
                "rtsp://127.0.0.1:8554",
            ),
            checkpoint_path=checkpoint,
            depth_backend=model_config.depth_backend,
            tensorrt_engine_path=(
                os.getenv("NVC_TENSORRT_ENGINE_PATH", "").strip() or None
            ),
            tensorrt_engine_directory=model_config.tensorrt_engine_directory,
            host=os.getenv("WALKWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("WALKWAY_PORT", "8000")),
            snapshot_max_age_seconds=float(
                os.getenv("WALKWAY_SNAPSHOT_MAX_AGE_SECONDS", "2.0")
            ),
            worker_shutdown_timeout_seconds=float(
                os.getenv("WALKWAY_WORKER_SHUTDOWN_TIMEOUT_SECONDS", "7.0")
            ),
            jetson_id=os.getenv("NVC_JETSON_ID", "jetson-a"),
            aggregator_ws_base_url=aggregator_url or None,
            aggregator_reconnect_seconds=float(
                os.getenv("NVC_AGGREGATOR_RECONNECT_SECONDS", "2.0")
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
        if self.depth_backend not in ("pytorch", "tensorrt"):
            raise ValueError("depth_backend phải là pytorch hoặc tensorrt.")
        if not self.tensorrt_engine_directory.strip():
            raise ValueError("tensorrt_engine_directory không được để trống.")
        if not 1 <= self.port <= 65535:
            raise ValueError("port phải nằm trong [1, 65535].")
        if self.snapshot_max_age_seconds <= 0:
            raise ValueError("snapshot_max_age_seconds phải là số dương.")
        if self.worker_shutdown_timeout_seconds <= 0:
            raise ValueError("worker_shutdown_timeout_seconds phải là số dương.")
        if not self.jetson_id.strip():
            raise ValueError("jetson_id không được để trống.")
        if self.aggregator_ws_base_url is not None:
            if not self.aggregator_ws_base_url.startswith(("ws://", "wss://")):
                raise ValueError(
                    "aggregator_ws_base_url phải bắt đầu bằng ws:// hoặc wss://."
                )
        if self.aggregator_reconnect_seconds <= 0:
            raise ValueError("aggregator_reconnect_seconds phải là số dương.")
