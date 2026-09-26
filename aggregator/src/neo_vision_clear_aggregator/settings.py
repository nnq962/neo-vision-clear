"""Cấu hình hạ tầng của aggregator lấy từ biến môi trường."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


AGGREGATOR_DIRECTORY = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = str(AGGREGATOR_DIRECTORY / "config" / "config.json")


@dataclass(frozen=True)
class AggregatorSettings:
    """Các tham số cần để chạy HTTP và phân loại nguồn mất kết nối."""

    host: str = "0.0.0.0"
    port: int = 8100
    source_stale_seconds: float = 3.0
    config_path: str = DEFAULT_CONFIG_PATH

    @classmethod
    def from_env(cls) -> "AggregatorSettings":
        """Tạo settings từ environment của process."""
        return cls(
            host=os.getenv("AGGREGATOR_HOST", "0.0.0.0"),
            port=int(os.getenv("AGGREGATOR_PORT", "8100")),
            source_stale_seconds=float(
                os.getenv("AGGREGATOR_SOURCE_STALE_SECONDS", "3.0")
            ),
            config_path=os.getenv("AGGREGATOR_CONFIG_PATH", DEFAULT_CONFIG_PATH),
        )

    def validate(self) -> None:
        """Từ chối cấu hình không thể dùng trước khi mở server."""
        if not self.host.strip():
            raise ValueError("AGGREGATOR_HOST không được để trống.")
        if not 1 <= self.port <= 65535:
            raise ValueError("AGGREGATOR_PORT phải nằm trong [1, 65535].")
        if self.source_stale_seconds <= 0:
            raise ValueError("AGGREGATOR_SOURCE_STALE_SECONDS phải là số dương.")
        if not self.config_path.strip():
            raise ValueError("AGGREGATOR_CONFIG_PATH không được để trống.")
