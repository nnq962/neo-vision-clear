"""Cấu hình runtime và HTTP server lấy từ biến môi trường."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ServerSettings:
    """Nhóm cấu hình cần để khởi động FastAPI và worker camera."""

    source: str | int = 0
    baseline_path: str = "data/walkway_baseline.npz"
    checkpoint_path: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    snapshot_max_age_seconds: float = 2.0
    use_gstreamer: bool = True
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
        use_gstreamer = os.getenv("WALKWAY_USE_GSTREAMER", "true").lower()
        return cls(
            source=source,
            baseline_path=os.getenv(
                "WALKWAY_BASELINE",
                "data/walkway_baseline.npz",
            ),
            checkpoint_path=checkpoint,
            host=os.getenv("WALKWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("WALKWAY_PORT", "8000")),
            snapshot_max_age_seconds=float(
                os.getenv("WALKWAY_SNAPSHOT_MAX_AGE_SECONDS", "2.0")
            ),
            use_gstreamer=use_gstreamer not in {"0", "false", "no", "off"},
            open_timeout_ms=int(os.getenv("WALKWAY_OPEN_TIMEOUT_MS", "5000")),
            read_timeout_ms=int(os.getenv("WALKWAY_READ_TIMEOUT_MS", "5000")),
            log_interval=float(os.getenv("WALKWAY_LOG_INTERVAL", "2.0")),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra cấu hình trước khi FastAPI khởi động worker."""
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
