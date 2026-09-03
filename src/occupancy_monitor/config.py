"""Cấu hình và dữ liệu nền của detector."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "config.json"
BACKGROUND_PATH = DATA_DIR / "background.jpg"


@dataclass
class DetectorConfig:
    """Lưu vùng giám sát và các ngưỡng phát hiện."""

    roi: tuple[int, int, int, int]
    polygon: list[list[int]] | None = None
    frame_width: int = 0
    frame_height: int = 0
    pixel_threshold: int = 30
    occupied_ratio: float = 0.03
    min_contour_area: int = 250
    enter_frames: int = 3
    exit_frames: int = 15


# ─────────────────────────────────────────────────────────────────────────────
def save_setup(frame: np.ndarray, polygon: list[list[int]]) -> None:
    """Lưu phần ảnh nền bao quanh polygon cùng cấu hình phát hiện."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if len(polygon) < 3:
        raise RuntimeError("Polygon cần ít nhất 3 điểm.")

    points = np.asarray(polygon, dtype=np.int32)
    x, y, width, height = cv2.boundingRect(points)
    roi = (x, y, width, height)
    background_roi = frame[y : y + height, x : x + width]
    if background_roi.size == 0:
        raise RuntimeError("ROI nằm ngoài frame camera.")

    config = DetectorConfig(
        roi=roi,
        polygon=polygon,
        frame_width=frame.shape[1],
        frame_height=frame.shape[0],
    )
    if not cv2.imwrite(str(BACKGROUND_PATH), background_roi):
        raise RuntimeError(f"Không thể lưu ảnh nền vào {BACKGROUND_PATH}.")
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
def load_setup() -> tuple[np.ndarray, DetectorConfig]:
    """Đọc ảnh nền và cấu hình, đồng thời hỗ trợ định dạng ROI cũ."""
    if not CONFIG_PATH.exists() or not BACKGROUND_PATH.exists():
        raise RuntimeError("Chưa có cấu hình. Hãy chạy chương trình với --setup trước.")

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["roi"] = tuple(payload["roi"])
    config = DetectorConfig(**payload)
    background = cv2.imread(str(BACKGROUND_PATH))
    if background is None:
        raise RuntimeError("Ảnh nền bị lỗi hoặc không đọc được.")
    return background, config
