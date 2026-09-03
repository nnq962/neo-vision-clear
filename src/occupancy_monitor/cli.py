"""Giao diện dòng lệnh của Neo Vision Clear."""

from __future__ import annotations

import argparse
import json
import os

from media_sources import MediaSourceError
from utils import LOGGER

from .application import run_detector, run_setup


DEFAULT_DISPLAY_SCALE = 0.65


def parse_args() -> argparse.Namespace:
    """Đọc nguồn video, chế độ setup và tỷ lệ hiển thị từ dòng lệnh."""
    parser = argparse.ArgumentParser(
        description="Detect occupancy in a fixed camera ROI without an ML model."
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("CAMERA_RTSP_URL"),
        help="RTSP URL, video path, or webcam index. Defaults to CAMERA_RTSP_URL.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Capture an empty background and select the monitored ROI.",
    )
    parser.add_argument(
        "--display-scale",
        type=float,
        default=DEFAULT_DISPLAY_SCALE,
        help="Window scale in the range (0, 1]. Defaults to 0.65.",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    """Kiểm tra tham số và chạy chế độ setup hoặc detector."""
    args = parse_args()
    if not args.source:
        LOGGER.error("Thiếu nguồn video. Đặt CAMERA_RTSP_URL hoặc truyền --source.")
        return 2
    if not 0 < args.display_scale <= 1:
        LOGGER.error("--display-scale phải lớn hơn 0 và không vượt quá 1.")
        return 2

    try:
        if args.setup:
            run_setup(args.source, args.display_scale)
        else:
            run_detector(args.source, args.display_scale)
    except (MediaSourceError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        LOGGER.error("Lỗi: %s", error)
        return 1
    return 0
