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

    # ─────────────────────────────────────────────────────────────────────────

    def project_zone_polygons_to_camera(
        self,
        zone_count: int,
        frame_width: int,
        frame_height: int,
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Chiếu polygon từng đoạn BEV về tọa độ chuẩn hóa của ảnh camera."""
        if zone_count < 1:
            raise ValueError("zone_count phải là số nguyên dương.")
        if frame_width < 2 or frame_height < 2:
            raise ValueError("Kích thước frame phải lớn hơn một pixel.")

        # Bước 1: chia đúng các hàng BEV mà phép đo clearance đang sử dụng để
        # đường biên overlay và kết quả nghiệp vụ không lệch đoạn nhau.
        valid_rows = np.flatnonzero(np.any(self.roi_mask > 0, axis=1))
        if valid_rows.size < zone_count:
            raise ValueError(
                "Số đoạn không được lớn hơn số lát cắt ngang hợp lệ của BEV."
            )
        row_groups = np.array_split(valid_rows, zone_count)
        inverse_homography = np.linalg.inv(self.homography)
        x_denominator = float(frame_width - 1)
        y_denominator = float(frame_height - 1)

        # Bước 2: lấy contour của phần ROI thuộc từng nhóm hàng. Cách này vẫn
        # đúng với ROI hình thang hoặc cạnh vào/ra nghiêng trên raster BEV.
        polygons: list[tuple[tuple[float, float], ...]] = []
        for rows in row_groups:
            zone_mask = np.zeros_like(self.roi_mask, dtype=np.uint8)
            zone_mask[rows] = self.roi_mask[rows]
            contours, _hierarchy = cv2.findContours(
                zone_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            if not contours:
                raise ValueError("Không thể tạo polygon cho một đoạn BEV.")
            contour = max(contours, key=cv2.contourArea)
            hull = cv2.convexHull(contour)
            perimeter = float(cv2.arcLength(hull, True))
            simplified = hull
            for epsilon_ratio in (0.002, 0.005, 0.01, 0.02, 0.04):
                candidate = cv2.approxPolyDP(
                    hull,
                    max(perimeter * epsilon_ratio, 0.5),
                    True,
                )
                simplified = candidate
                if 3 <= len(candidate) <= 8:
                    break

            if len(simplified) > 8:
                sample_indices = np.linspace(
                    0,
                    len(simplified) - 1,
                    8,
                    dtype=np.int32,
                )
                simplified = simplified[sample_indices]

            # Một đoạn chỉ cao một pixel có thể bị OpenCV coi như đường thẳng.
            # Mở rộng bounding box một pixel để vẫn tạo được tứ giác hợp lệ.
            if len(simplified) < 3:
                x_value, y_value, width, height = cv2.boundingRect(contour)
                top = max(y_value - (1 if height == 1 else 0), 0)
                bottom = min(y_value + max(height - 1, 1), self.roi_mask.shape[0] - 1)
                right = min(x_value + max(width - 1, 1), self.roi_mask.shape[1] - 1)
                simplified = np.array(
                    [
                        [[x_value, top]],
                        [[right, top]],
                        [[right, bottom]],
                        [[x_value, bottom]],
                    ],
                    dtype=np.float32,
                )

            # Bước 3: chiếu ngược về pixel camera rồi chuẩn hóa để frontend có
            # thể scale polygon trực tiếp theo kích thước video đang hiển thị.
            bev_points = simplified.reshape(1, -1, 2).astype(np.float32)
            camera_points = cv2.perspectiveTransform(
                bev_points,
                inverse_homography,
            )[0]
            polygon = tuple(
                (
                    float(np.clip(point[0] / x_denominator, 0.0, 1.0)),
                    float(np.clip(point[1] / y_denominator, 0.0, 1.0)),
                )
                for point in camera_points
            )
            polygons.append(polygon)
        return tuple(polygons)


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
