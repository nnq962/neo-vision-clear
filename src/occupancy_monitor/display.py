"""Các tiện ích hiển thị và chọn polygon ROI."""

from __future__ import annotations

import cv2
import numpy as np


def resize_for_display(image: np.ndarray, scale: float) -> np.ndarray:
    """Thu nhỏ ảnh để hiển thị mà không thay đổi dữ liệu xử lý gốc."""
    if scale == 1.0:
        return image
    return cv2.resize(
        image,
        dsize=None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )


# ─────────────────────────────────────────────────────────────────────────────
def select_polygon(frame: np.ndarray, display_scale: float) -> list[list[int]]:
    """Cho phép người dùng chọn polygon và trả về tọa độ trên frame gốc."""
    window = "Select polygon ROI"
    display_frame = resize_for_display(frame, display_scale)
    points: list[tuple[int, int]] = []

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        """Thêm hoặc hoàn tác một đỉnh polygon theo thao tác chuột."""
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)
    while True:
        preview = display_frame.copy()
        if points:
            cv2.polylines(
                preview,
                [np.asarray(points, dtype=np.int32)],
                isClosed=len(points) >= 3,
                color=(0, 255, 255),
                thickness=2,
            )
            for point in points:
                cv2.circle(preview, point, 4, (0, 0, 255), thickness=-1)
        cv2.putText(
            preview,
            "Left click: point | Right click: undo | ENTER: save | C: clear",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
        )
        cv2.imshow(window, preview)
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10) and len(points) >= 3:
            break
        if key == ord("c"):
            points.clear()
        if key == 27:
            points.clear()
            break

    cv2.destroyWindow(window)
    return [
        [int(round(x / display_scale)), int(round(y / display_scale))]
        for x, y in points
    ]
