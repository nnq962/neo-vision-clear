"""Phép chiếu mask từ ảnh camera sang raster BEV có tỷ lệ mét cố định."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from walkway_monitor.models import BaselineArtifact


@dataclass(frozen=True)
class MetricBevTransform:
    """Thông tin biến đổi từ pixel camera sang raster tọa độ thực."""

    homography: np.ndarray
    roi_mask: np.ndarray
    entrance_mask: np.ndarray
    exit_mask: np.ndarray
    pixels_per_meter: float
    minimum_world_x: float
    minimum_world_y: float

    # ─────────────────────────────────────────────────────────────────────────

    def warp_mask(self, mask: np.ndarray) -> np.ndarray:
        """Chiếu một mask camera sang BEV và cắt kết quả trong ROI thực."""
        # Bước 1: kiểm tra mask đầu vào trước khi chạy phép chiếu phối cảnh.
        if mask.ndim != 2:
            raise ValueError("Mask cần chiếu sang BEV phải là mảng hai chiều.")

        # Bước 2: warp bằng nearest-neighbor để không tạo giá trị mask trung gian.
        height, width = self.roi_mask.shape
        warped = cv2.warpPerspective(
            mask.astype(np.uint8),
            self.homography,
            (width, height),
            flags=cv2.INTER_NEAREST,
        )
        warped[self.roi_mask == 0] = 0
        return warped


# ─────────────────────────────────────────────────────────────────────────────


def build_metric_bev_transform(
    baseline: BaselineArtifact,
    pixels_per_meter: float,
) -> MetricBevTransform:
    """Tạo phép chiếu BEV theo mét và báo lỗi khi baseline thiếu dữ liệu."""
    world = baseline.roi.world_coordinates
    if world is None or len(world.points) != 4:
        raise ValueError(
            "Baseline cần đúng 4 tọa độ thực P1-P4 để phân tích lối đi theo mét."
        )
    if pixels_per_meter <= 0:
        raise ValueError("pixels_per_meter phải là số dương.")
    world.validate(len(baseline.roi.normalized_points))
    if world.unit.strip().lower() not in {
        "m",
        "meter",
        "meters",
        "metre",
        "metres",
        "mét",
    }:
        raise ValueError("Phép đo metric BEV yêu cầu tọa độ thực dùng đơn vị mét.")

    # Bước 1: tạo canvas metric từ hộp bao của polygon tọa độ thực.
    world_points = world.points.astype(np.float32)
    minimum = np.min(world_points, axis=0)
    span = np.ptp(world_points, axis=0)
    if np.any(span <= 1e-6):
        raise ValueError("Vùng tọa độ thực phải có chiều rộng và chiều dài dương.")
    canvas_width = max(2, int(round(float(span[0]) * pixels_per_meter)))
    canvas_height = max(2, int(round(float(span[1]) * pixels_per_meter)))
    if canvas_width > 10_000 or canvas_height > 10_000:
        raise ValueError("Raster BEV vượt quá 10000 pixel; hãy giảm pixels_per_meter.")
    # Các đỉnh cực đại nằm tại tâm ô cuối; số ô vẫn biểu diễn đúng độ dài mét.
    destination_points = (world_points - minimum) / span
    destination_points *= np.array(
        [canvas_width - 1, canvas_height - 1],
        dtype=np.float32,
    )
    destination_points = destination_points.astype(np.float32)

    # Bước 2: fit homography từ polygon camera sang polygon tọa độ thực.
    source_points = baseline.roi.to_pixel_points(
        baseline.frame_width,
        baseline.frame_height,
    ).astype(np.float32)
    homography, _mask = cv2.findHomography(
        source_points,
        destination_points,
        method=0,
    )
    if homography is None:
        raise ValueError("Không thể tính homography cho phép đo BEV.")
    # Bước 3: raster hóa trực tiếp polygon thực. Cách này tránh mất một hoặc
    # hai ô biên do warp mask camera rồi làm tròn lần thứ hai.
    raster_points = np.rint(destination_points).astype(np.int32)
    roi_mask = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
    cv2.fillPoly(roi_mask, [raster_points], 255, lineType=cv2.LINE_8)

    # Bước 4: lưu riêng hai cạnh P1-P2 và P4-P3. Hai cạnh có thể nghiêng nên
    # không thể thay bằng hàng Y nhỏ nhất/lớn nhất của bounding box.
    entrance_mask = np.zeros_like(roi_mask, dtype=np.uint8)
    exit_mask = np.zeros_like(roi_mask, dtype=np.uint8)
    cv2.line(
        entrance_mask,
        tuple(raster_points[0]),
        tuple(raster_points[1]),
        255,
        2,
        cv2.LINE_8,
    )
    cv2.line(
        exit_mask,
        tuple(raster_points[-1]),
        tuple(raster_points[-2]),
        255,
        2,
        cv2.LINE_8,
    )
    entrance_mask[roi_mask == 0] = 0
    exit_mask[roi_mask == 0] = 0
    return MetricBevTransform(
        homography=homography,
        roi_mask=roi_mask,
        entrance_mask=entrance_mask,
        exit_mask=exit_mask,
        pixels_per_meter=float(pixels_per_meter),
        minimum_world_x=float(minimum[0]),
        minimum_world_y=float(minimum[1]),
    )
