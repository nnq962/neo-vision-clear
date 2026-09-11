"""Phân tích depth map thành mask và các phép đo hình học của lối đi."""

from __future__ import annotations

import time

import cv2
import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.alignment import align_depth
from walkway_monitor.detection.bev import build_metric_bev_transform
from walkway_monitor.detection.components import (
    clean_changed_mask,
    filter_components_by_area,
    measure_route_capacity,
)
from walkway_monitor.detection.models import (
    AnalysisDiagnostics,
    CorridorSnapshot,
    DetectionOutput,
)
from walkway_monitor.models import BaselineArtifact


class WalkwayAnalyzer:
    """Căn chỉnh depth, tạo mask và trả số đo mà không đưa ra kết luận."""

    def __init__(self, baseline: BaselineArtifact, config: DetectionConfig):
        """Chuẩn bị mask và threshold chuẩn hóa dùng chung cho detector."""
        # Bước 1: kiểm tra dữ liệu baseline và các tham số detection trước khi
        # tạo những dữ liệu trung gian dùng chung cho tất cả frame.
        baseline.validate()
        config.validate()
        self._baseline = baseline
        self._config = config

        # Bước 2: chuyển polygon ROI thành mask toàn ảnh. Đây là vùng duy nhất
        # được dùng để tính diện tích vùng thay đổi và các phép đo hình học.
        self._roi_mask = baseline.roi.to_mask(
            baseline.frame_width,
            baseline.frame_height,
        )
        self._roi = self._roi_mask > 0
        self._roi_area = int(np.count_nonzero(self._roi))
        if self._roi_area < 100:
            raise ValueError("ROI baseline quá nhỏ để chạy detection.")

        # Bước 3: giãn ROI ra ngoài để tạo check area gồm ROI và một lớp đệm.
        # So sánh depth và morphology chỉ nhìn vùng này; cảnh ở xa ROI bị bỏ.
        self._check_area_mask = self._dilate_roi(
            self._roi_mask,
            config.check_area_padding,
        )
        self._check_area = self._check_area_mask > 0

        # Bước 4: tính dải depth điển hình trong check area. Dải này được dùng để
        # chuẩn hóa sai khác, vì Depth Anything trả depth tương đối chứ không
        # phải khoảng cách theo mét.
        reference_values = baseline.reference_depth[self._check_area]
        self._depth_span = float(
            np.percentile(reference_values, 95.0)
            - np.percentile(reference_values, 5.0)
        )
        self._depth_span = max(self._depth_span, 1e-6)

        # Bước 5: làm mượt reference depth một lần tại đây. Mỗi depth map mới
        # cũng sẽ được làm mượt tương tự trước khi so sánh trong process().
        self._reference_smoothed = cv2.GaussianBlur(
            baseline.reference_depth,
            (config.depth_blur_kernel, config.depth_blur_kernel),
            0,
        )

        # Bước 6: tạo threshold riêng cho từng pixel từ noise_map. Pixel vốn
        # nhiều nhiễu sẽ cần sai khác lớn hơn mới được xem là thay đổi thật.
        normalized_noise = baseline.noise_map / np.float32(self._depth_span)
        self._threshold_map = np.maximum(
            np.float32(config.minimum_difference),
            normalized_noise * np.float32(config.noise_multiplier),
        ).astype(np.float32)

        # Bước 7: chọn kích thước kernel morphology theo độ phân giải baseline
        # để loại đốm nhỏ và nối các vùng thay đổi nằm gần nhau.
        kernel_size = max(
            3,
            int(round(min(baseline.frame_height, baseline.frame_width) / config.morphology_divisor)),
        )
        self._kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1

        # Bước 8: quy đổi tỷ lệ component nhỏ nhất cần hiển thị thành số pixel
        # dựa trên diện tích ROI gốc.
        self._display_minimum_area = max(
            1,
            int(round(self._roi_area * config.display_minimum_area_ratio)),
        )

        # Bước 9: chuẩn bị phép chiếu metric một lần. Phân tích cho robot luôn
        # cần đơn vị mét nên baseline thiếu tọa độ thực sẽ báo lỗi ngay tại đây.
        self._metric_bev = build_metric_bev_transform(
            baseline,
            config.bev_pixels_per_meter,
        )

        # Bước 10: bắt đầu đánh số các depth map được process() xử lý từ 0.
        self._frame_index = 0

    # ─────────────────────────────────────────────────────────────────────────

    def process(self, current_depth: np.ndarray) -> DetectionOutput:
        """Xử lý một depth map và trả về phép đo cùng các mask debug."""
        # Bước 1: chuẩn hóa input về float32 và bảo đảm depth map hiện tại có
        # cùng kích thước với baseline, không chứa NaN hoặc giá trị vô cực.
        depth = np.asarray(current_depth, dtype=np.float32)
        expected_shape = (
            self._baseline.frame_height,
            self._baseline.frame_width,
        )
        if depth.shape != expected_shape:
            raise ValueError(
                f"Depth hiện tại có shape {depth.shape}, cần {expected_shape}."
            )
        if not np.all(np.isfinite(depth)):
            raise ValueError("Depth hiện tại chứa giá trị không hữu hạn.")

        # Bước 2: mặc định fit scale/shift trên ROI bằng hồi quy robust. Chỉ
        # nhóm pixel khớp baseline nhất được giữ lại, vì vậy người hoặc vật cản
        # không kéo lệch toàn bộ depth map. Khi CLI tắt alignment, dùng nguyên
        # depth raw và đặt scale=1, shift=0.
        if self._config.depth_alignment:
            aligned, scale, shift = align_depth(
                depth,
                self._baseline.reference_depth,
                self._roi,
                inlier_ratio=self._config.alignment_inlier_ratio,
            )
        else:
            aligned = depth
            scale, shift = 1.0, 0.0

        # Bước 3: làm mượt depth đã căn chỉnh bằng đúng Gaussian kernel đã dùng
        # cho reference để giảm các dao động nhỏ theo không gian.
        smoothed = cv2.GaussianBlur(
            aligned,
            (self._config.depth_blur_kernel, self._config.depth_blur_kernel),
            0,
        )

        # Bước 4: trừ reference và chia cho `_depth_span` để thu sai khác tương
        # đối. Chỉ phần dương được giữ để tìm vật nằm gần camera hơn baseline.
        signed_difference = (
            (smoothed - self._reference_smoothed) / self._depth_span
        ).astype(np.float32)
        normalized_difference = np.maximum(signed_difference, 0.0).astype(np.float32)

        # Bước 5: tạo mask thay đổi và chạy morphology trên toàn check area để
        # padding cung cấp ngữ cảnh cho các pixel nằm sát biên ROI.
        raw_mask = (
            (normalized_difference >= self._threshold_map) & self._check_area
        ).astype(np.uint8) * 255
        cleaned_check_mask = clean_changed_mask(
            raw_mask,
            self._check_area_mask,
            self._kernel_size,
        )

        # Bước 6: sau khi làm sạch, cắt mask trở lại ROI. Thay đổi chỉ nằm trong
        # padding sẽ không được vẽ và không tham gia phép đo trong ROI.
        measurement_mask = cleaned_check_mask
        measurement_mask[~self._roi] = 0

        # Bước 7: bỏ các component quá nhỏ rồi dùng chính mask này cho cả phần
        # hiển thị lẫn đo bề rộng, tránh component vô hình làm sai số liệu.
        changed_mask = filter_components_by_area(
            measurement_mask,
            self._display_minimum_area,
        )

        # Bước 8: chiếu mask sang raster BEV và đo footprint rộng nhất có vùng
        # tâm nối liên tục từ đầu tới cuối hành lang.
        bev_changed_mask = self._metric_bev.warp_mask(changed_mask)
        capacity = measure_route_capacity(
            bev_changed_mask,
            self._metric_bev.roi_mask,
            self._metric_bev.entrance_mask,
            self._metric_bev.exit_mask,
            self._metric_bev.pixels_per_meter,
            self._metric_bev.minimum_world_x,
            self._metric_bev.minimum_world_y,
        )

        # Bước 9: tách snapshot nghiệp vụ khỏi chẩn đoán căn chỉnh nội bộ.
        captured_at = time.time()
        snapshot = CorridorSnapshot(
            maximum_passable_width_meters=(
                capacity.maximum_passable_width_meters
            ),
            walkway_width_meters=capacity.walkway_width_meters,
            bottleneck_y_meters=capacity.bottleneck_y_meters,
            bottleneck_free_x_ranges_meters=(
                capacity.bottleneck_free_x_ranges_meters
            ),
            frame_index=self._frame_index,
            captured_at=captured_at,
        )
        diagnostics = AnalysisDiagnostics(
            alignment_scale=scale,
            alignment_shift=shift,
            alignment_inlier_ratio=self._config.alignment_inlier_ratio,
            alignment_enabled=self._config.depth_alignment,
        )

        # Bước 10: tăng frame index và chỉ trả các ảnh thật sự được UI sử dụng.
        self._frame_index += 1
        return DetectionOutput(
            snapshot=snapshot,
            route_capacity=capacity,
            diagnostics=diagnostics,
            raw_depth=depth,
            aligned_depth=aligned,
            check_area_mask=self._check_area_mask,
            changed_mask=changed_mask,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _dilate_roi(roi_mask: np.ndarray, padding: int) -> np.ndarray:
        """Giãn ROI ra ngoài một số pixel để tạo vùng kiểm tra có lớp đệm."""
        if padding <= 0:
            return roi_mask.astype(np.uint8, copy=True)
        kernel_size = padding * 2 + 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (kernel_size, kernel_size),
        )
        return cv2.dilate(roi_mask.astype(np.uint8), kernel, iterations=1)
