"""Giao diện OpenCV để chọn và hiển thị polygon ROI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import cv2
import numpy as np

from walkway_monitor.models import RoiDefinition
from walkway_monitor.ui import draw_text


# ─────────────────────────────────────────────────────────────────────────────


def _close_window(window: str) -> None:
    """Đóng cửa sổ OpenCV theo kiểu best-effort khi UI đang thoát."""
    # Bước 1: người dùng có thể đã đóng cửa sổ bằng window manager trước đó.
    try:
        cv2.destroyWindow(window)
    except cv2.error:
        pass


# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def _open_window(window: str, error_message: str) -> Iterator[None]:
    """Mở cửa sổ OpenCV và bảo đảm đóng nó khi rời khỏi context."""
    # Bước 1: chuyển lỗi môi trường headless thành thông báo nghiệp vụ rõ ràng.
    try:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    except cv2.error as exc:
        raise RuntimeError(error_message) from exc
    try:
        yield
    finally:
        # Bước 2: cleanup cũng chạy khi người dùng hủy hoặc render phát sinh lỗi.
        _close_window(window)


# ─────────────────────────────────────────────────────────────────────────────


def normalize_polygon(points: np.ndarray, width: int, height: int) -> RoiDefinition:
    """Chuyển polygon pixel sang RoiDefinition có tọa độ chuẩn hóa."""
    if width <= 1 or height <= 1:
        raise ValueError("Frame quá nhỏ để chuẩn hóa ROI.")
    pixel_points = np.asarray(points, dtype=np.float32)
    if pixel_points.ndim != 2 or pixel_points.shape[1:] != (2,):
        raise ValueError("Polygon pixel phải có shape (N, 2).")
    scale = np.array([width - 1, height - 1], dtype=np.float32)
    roi = RoiDefinition(normalized_points=pixel_points / scale)
    roi.validate()
    if cv2.contourArea(pixel_points) < 1.0:
        raise ValueError("Polygon ROI không được suy biến hoặc có diện tích bằng không.")
    return roi


# ─────────────────────────────────────────────────────────────────────────────


def draw_roi(frame: np.ndarray, roi: RoiDefinition, color=(0, 255, 255)) -> np.ndarray:
    """Vẽ polygon ROI lên bản sao của frame và trả về ảnh kết quả."""
    height, width = frame.shape[:2]
    canvas = frame.copy()
    points = roi.to_pixel_points(width, height)
    cv2.polylines(canvas, [points], True, color, 2, cv2.LINE_AA)
    for index, point in enumerate(points):
        cv2.circle(canvas, tuple(point), 5, color, -1, cv2.LINE_AA)
        cv2.putText(
            canvas,
            str(index + 1),
            (int(point[0]) + 7, int(point[1]) - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )
    return canvas


# ─────────────────────────────────────────────────────────────────────────────


def select_polygon(frame: np.ndarray) -> RoiDefinition:
    """Cho người dùng vẽ polygon ROI bằng chuột trên một cửa sổ OpenCV."""
    window = "Chon ROI loi di"
    points: list[tuple[int, int]] = []

    def on_mouse(event, x, y, _flags, _param) -> None:
        """Thêm hoặc xóa điểm polygon theo sự kiện chuột."""
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()

    with _open_window(
        window,
        "Không thể mở cửa sổ chọn ROI trong môi trường hiện tại.",
    ):
        cv2.setMouseCallback(window, on_mouse)
        while True:
            canvas = frame.copy()
            if points:
                pixel_points = np.asarray(points, dtype=np.int32)
                cv2.polylines(
                    canvas,
                    [pixel_points],
                    len(points) >= 3,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                for index, point in enumerate(points):
                    cv2.circle(canvas, point, 5, (0, 255, 255), -1, cv2.LINE_AA)
                    cv2.putText(
                        canvas,
                        str(index + 1),
                        (point[0] + 7, point[1] - 7),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
            canvas = draw_text(
                canvas,
                "Trái: thêm | Phải/Backspace: xóa | Enter: xong | C: vẽ lại",
                (15, 8),
                font_size=21,
                color=(255, 255, 255),
            )
            cv2.imshow(window, canvas)
            key = cv2.waitKey(20) & 0xFF
            if key in (10, 13) and len(points) >= 3:
                break
            if key in (8, 127) and points:
                points.pop()
            elif key in (ord("c"), ord("C")):
                points.clear()
            elif key in (27, ord("q"), ord("Q")):
                raise KeyboardInterrupt("Đã hủy chọn ROI.")

    height, width = frame.shape[:2]
    return normalize_polygon(np.asarray(points, dtype=np.float32), width, height)


# ─────────────────────────────────────────────────────────────────────────────


def wait_for_empty_confirmation(frame: np.ndarray, roi: RoiDefinition) -> None:
    """Chờ người dùng xác nhận ROI đã hoàn toàn trống trước khi thu baseline."""
    window = "Xac nhan loi di trong"
    canvas = draw_roi(frame, roi)
    canvas = draw_text(
        canvas,
        "Đảm bảo ROI TRỐNG – Enter/Space: bắt đầu | Q: hủy",
        (15, 8),
        font_size=22,
        color=(0, 255, 255),
    )
    with _open_window(
        window,
        "Không thể mở cửa sổ xác nhận ROI trong môi trường hiện tại.",
    ):
        while True:
            cv2.imshow(window, canvas)
            key = cv2.waitKey(20) & 0xFF
            if key in (10, 13, 32):
                return
            if key in (27, ord("q"), ord("Q")):
                raise KeyboardInterrupt("Đã hủy calibration.")
