"""Điều phối luồng setup và theo dõi trạng thái camera."""

from __future__ import annotations

import cv2
import numpy as np
from utils import LOGGER

from .config import DetectorConfig, load_setup, save_setup
from .detection import StableState, changed_ratio, foreground_mask
from .display import resize_for_display, select_polygon
from .stream import open_stream, read_frame


WINDOW_NAME = "Neo Vision Clear"


def run_setup(source: str, display_scale: float) -> None:
    """Chụp nền trống, nhận polygon từ người dùng và lưu cấu hình."""
    stream = open_stream(source)

    selected_frame: np.ndarray | None = None
    try:
        LOGGER.info("Đảm bảo khu vực đang trống. Nhấn SPACE để chụp nền, Q để thoát.")
        while True:
            frame = read_frame(stream)
            preview = frame.copy()
            cv2.putText(
                preview,
                "Clear the area, then press SPACE",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )
            cv2.imshow(WINDOW_NAME, resize_for_display(preview, display_scale))
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == 32:
                selected_frame = frame.copy()
                break

        if selected_frame is not None:
            LOGGER.info("Click trái để đặt các đỉnh polygon, rồi nhấn ENTER.")
            polygon = select_polygon(selected_frame, display_scale)
            if len(polygon) < 3:
                raise RuntimeError("Đã hủy hoặc polygon không hợp lệ.")
            save_setup(selected_frame, polygon)
            LOGGER.info("Đã lưu riêng ảnh nền polygon trong thư mục data/")
    finally:
        stream.close()
        cv2.destroyAllWindows()


# ─────────────────────────────────────────────────────────────────────────────
def build_roi_mask(
    config: DetectorConfig,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Tạo mask polygon cục bộ và danh sách điểm dùng để vẽ lên frame."""
    if not config.polygon:
        return None, None

    x, y, width, height = config.roi
    polygon_points = np.asarray(config.polygon, dtype=np.int32)
    relative_points = polygon_points - np.asarray([x, y], dtype=np.int32)
    roi_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(roi_mask, [relative_points], 255)
    return roi_mask, polygon_points


# ─────────────────────────────────────────────────────────────────────────────
def extract_background_roi(
    background: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """Lấy ROI nền và tương thích với cả dữ liệu setup phiên bản cũ."""
    x, y, width, height = config.roi
    if background.shape[:2] == (height, width):
        return background

    background_roi = background[y : y + height, x : x + width]
    if background_roi.size == 0:
        raise RuntimeError("ROI nằm ngoài ảnh nền.")
    return background_roi


# ─────────────────────────────────────────────────────────────────────────────
def run_detector(source: str, display_scale: float) -> None:
    """Theo dõi camera, tạo foreground mask và hiển thị trạng thái ổn định."""
    background, config = load_setup()
    x, y, width, height = config.roi
    background_roi = extract_background_roi(background, config)
    roi_mask, polygon_points = build_roi_mask(config)

    stream = open_stream(source)

    state = StableState(config.enter_frames, config.exit_frames)
    show_mask = True
    LOGGER.info("Detector đang chạy. Nhấn Q để thoát, M để bật/tắt cửa sổ mask.")
    try:
        while True:
            frame = read_frame(stream)
            expected_size = (config.frame_width, config.frame_height)
            if all(expected_size) and frame.shape[1::-1] != expected_size:
                frame = cv2.resize(frame, expected_size)

            current_roi = frame[y : y + height, x : x + width]
            if current_roi.shape[:2] != background_roi.shape[:2]:
                raise RuntimeError("ROI hiện tại không khớp ảnh nền. Hãy chạy --setup lại.")

            mask = foreground_mask(
                background_roi,
                current_roi,
                config.pixel_threshold,
                config.min_contour_area,
                roi_mask,
            )
            ratio = changed_ratio(mask, roi_mask)
            occupied = state.update(ratio >= config.occupied_ratio)
            color = (0, 0, 255) if occupied else (0, 200, 0)
            label = "OCCUPIED" if occupied else "EMPTY"

            if polygon_points is not None:
                cv2.polylines(frame, [polygon_points], True, color, 3)
            else:
                cv2.rectangle(frame, (x, y), (x + width, y + height), color, 3)
            cv2.putText(
                frame,
                f"{label} | changed: {ratio:.1%}",
                (x, max(30, y - 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )
            cv2.imshow(WINDOW_NAME, resize_for_display(frame, display_scale))
            if show_mask:
                cv2.imshow("Foreground mask", resize_for_display(mask, display_scale))

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("m"):
                show_mask = not show_mask
                if not show_mask:
                    cv2.destroyWindow("Foreground mask")
    finally:
        stream.close()
        cv2.destroyAllWindows()
