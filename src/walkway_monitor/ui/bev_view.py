"""Renderer BEV có cache các phép chiếu cố định của baseline."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import DetectionOutput
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui.text import draw_text


class BevRenderer:
    """Chiếu ảnh camera sang panel BEV mà không tính lại homography mỗi frame."""

    def __init__(
        self,
        baseline: BaselineArtifact,
        panel_width: int,
        panel_height: int,
    ):
        """Tính trước hình học camera, thế giới và panel hiển thị."""
        world = baseline.roi.world_coordinates
        if world is None or len(world.points) != 4:
            raise ValueError("Baseline thiếu tọa độ thực để hiển thị BEV.")
        world.validate(len(baseline.roi.normalized_points))
        self._baseline = baseline
        self._panel_width = panel_width
        self._panel_height = panel_height
        self._world_points = world.points.astype(np.float32)
        self._unit = world.unit

        # Bước 1: đặt polygon thực lên phần bên phải của panel, giữ đúng tỷ lệ.
        self._destination_points = _fit_world_points_to_panel(
            self._world_points,
            panel_width,
            panel_height,
            content_left=int(round(panel_width * 0.44)),
        )
        source_points = baseline.roi.to_pixel_points(
            baseline.frame_width,
            baseline.frame_height,
        ).astype(np.float32)

        # Bước 2: cache cả chiều camera→panel và thế giới→camera.
        self._camera_to_panel, _mask = cv2.findHomography(
            source_points,
            self._destination_points,
            method=0,
        )
        self._world_to_camera, _mask = cv2.findHomography(
            self._world_points,
            source_points,
            method=0,
        )
        if self._camera_to_panel is None or self._world_to_camera is None:
            raise ValueError("Không thể tính homography cho giao diện BEV.")

        # Bước 3: warp ROI tĩnh đúng một lần để dùng lại cho mọi frame.
        source_roi = baseline.roi.to_mask(
            baseline.frame_width,
            baseline.frame_height,
        )
        self._panel_roi = cv2.warpPerspective(
            source_roi,
            self._camera_to_panel,
            (panel_width, panel_height),
            flags=cv2.INTER_NEAREST,
        ) > 0

    # ─────────────────────────────────────────────────────────────────────────

    def render(self, frame: np.ndarray, output: DetectionOutput) -> np.ndarray:
        """Tạo panel BEV từ frame và snapshot hiện tại."""
        panel = np.full(
            (self._panel_height, self._panel_width, 3),
            18,
            dtype=np.uint8,
        )

        # Bước 1: warp ảnh camera và mask thay đổi bằng homography đã cache.
        warped = cv2.warpPerspective(
            frame,
            self._camera_to_panel,
            (self._panel_width, self._panel_height),
            flags=cv2.INTER_LINEAR,
        )
        panel[self._panel_roi] = warped[self._panel_roi]
        changed = cv2.warpPerspective(
            output.changed_mask,
            self._camera_to_panel,
            (self._panel_width, self._panel_height),
            flags=cv2.INTER_NEAREST,
        ) > 0
        changed &= self._panel_roi
        panel[changed] = (
            0.35 * panel[changed] + 0.65 * np.array([0, 0, 255])
        ).astype(np.uint8)

        # Bước 2: vẽ biên polygon, nút thắt và nhãn tọa độ thực.
        destination_pixels = np.rint(self._destination_points).astype(np.int32)
        cv2.polylines(
            panel,
            [destination_pixels],
            True,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        line = self.camera_bottleneck_line(output)
        transformed = cv2.perspectiveTransform(
            line.reshape(1, 2, 2),
            self._camera_to_panel,
        )[0]
        start, end = np.rint(transformed).astype(np.int32)
        cv2.line(panel, tuple(start), tuple(end), (0, 165, 255), 2, cv2.LINE_AA)
        panel = self._draw_coordinate_labels(panel, destination_pixels)
        return self._draw_information(panel, output)

    # ─────────────────────────────────────────────────────────────────────────

    def camera_bottleneck_line(self, output: DetectionOutput) -> np.ndarray:
        """Chiếu lát cắt nút thắt từ tọa độ thực về pixel camera."""
        capacity = output.route_capacity
        left, right = capacity.bottleneck_world_span
        world_line = np.array(
            [[
                [left, capacity.bottleneck_y_meters],
                [right, capacity.bottleneck_y_meters],
            ]],
            dtype=np.float32,
        )
        return cv2.perspectiveTransform(world_line, self._world_to_camera)[0]

    # ─────────────────────────────────────────────────────────────────────────

    def _draw_coordinate_labels(
        self,
        panel: np.ndarray,
        pixel_points: np.ndarray,
    ) -> np.ndarray:
        """Vẽ nhãn P và tọa độ thực cạnh từng đỉnh polygon BEV."""
        canvas = panel
        for index, (pixel_point, world_point) in enumerate(
            zip(pixel_points, self._world_points)
        ):
            pixel_x, pixel_y = int(pixel_point[0]), int(pixel_point[1])
            cv2.circle(canvas, (pixel_x, pixel_y), 5, (0, 255, 255), -1, cv2.LINE_AA)
            label = (
                f"P{index + 1} "
                f"({world_point[0]:.2f}, {world_point[1]:.2f}) {self._unit}"
            )
            label_x = min(max(pixel_x + 8, 0), max(self._panel_width - 175, 0))
            label_y = min(max(pixel_y + 8, 0), max(self._panel_height - 18, 0))
            canvas = draw_text(
                canvas,
                label,
                (label_x, label_y),
                font_size=15,
                color=(0, 255, 255),
                stroke_width=2,
            )
        return canvas

    # ─────────────────────────────────────────────────────────────────────────

    def _draw_information(
        self,
        panel: np.ndarray,
        output: DetectionOutput,
    ) -> np.ndarray:
        """Vẽ các trường snapshot thành từng dòng căn trái trên panel BEV."""
        snapshot = output.snapshot
        ranges_text = ", ".join(
            f"{start:.2f} → {end:.2f}"
            for start, end in snapshot.bottleneck_free_x_ranges_meters
        ) or "không có"
        lines = (
            f"Chiều rộng hành lang: {snapshot.walkway_width_meters:.2f} m",
            (
                "Bề rộng đi xuyên suốt: "
                f"{snapshot.maximum_passable_width_meters:.2f} m"
            ),
            f"Vị trí nút thắt: Y = {snapshot.bottleneck_y_meters:.2f} m",
            f"Khoảng trống tại nút thắt: X = {ranges_text} m",
        )

        # Bước 1: vẽ tiêu đề và dữ liệu từ cùng một lề trái.
        canvas = draw_text(
            panel,
            "THÔNG TIN ĐO LƯỜNG",
            (22, 16),
            font_size=23,
            color=(255, 255, 255),
            stroke_width=2,
        )
        for index, line in enumerate(lines):
            canvas = draw_text(
                canvas,
                line,
                (22, 62 + index * 36),
                font_size=18,
                color=(255, 255, 255),
            )

        # Bước 2: thêm chú thích và tiêu đề vùng ảnh BEV.
        canvas = draw_text(
            canvas,
            "Đỏ: vùng depth thay đổi",
            (22, 234),
            font_size=16,
            color=(0, 0, 255),
        )
        canvas = draw_text(
            canvas,
            "Cam: lát cắt nút thắt",
            (22, 262),
            font_size=16,
            color=(0, 165, 255),
        )
        return draw_text(
            canvas,
            "GÓC NHÌN BEV",
            (int(round(self._panel_width * 0.44)) + 18, 16),
            font_size=23,
            color=(255, 255, 255),
            stroke_width=2,
        )


# ─────────────────────────────────────────────────────────────────────────────


def _fit_world_points_to_panel(
    world_points: np.ndarray,
    panel_width: int,
    panel_height: int,
    content_left: int,
) -> np.ndarray:
    """Đặt các điểm thực lên panel với cùng tỷ lệ theo hai trục."""
    # Bước 1: lấy biên tọa độ và kiểm tra vùng thực không bị suy biến.
    points = np.asarray(world_points, dtype=np.float32)
    minimum = np.min(points, axis=0)
    span = np.ptp(points, axis=0)
    if np.any(span <= 1e-6):
        raise ValueError("Vùng tọa độ thực phải có chiều rộng và chiều dài dương.")

    # Bước 2: chọn scale chung để bảo toàn tỷ lệ mét và căn giữa polygon.
    side_margin = max(10, int(round(panel_width * 0.04)))
    top_margin = max(54, int(round(panel_height * 0.12)))
    bottom_margin = max(10, int(round(panel_height * 0.04)))
    available_width = max(panel_width - content_left - 2 * side_margin, 1)
    available_height = max(panel_height - top_margin - bottom_margin, 1)
    scale = min(available_width / span[0], available_height / span[1])
    rendered_size = span * np.float32(scale)
    offset = np.array(
        [
            content_left + side_margin + (available_width - rendered_size[0]) / 2,
            top_margin + (available_height - rendered_size[1]) / 2,
        ],
        dtype=np.float32,
    )
    return (points - minimum) * np.float32(scale) + offset
