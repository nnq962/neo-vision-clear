"""Detector thuần chuyển một depth map thành trạng thái chiếm dụng lối đi."""

from __future__ import annotations

import time

import cv2
import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.alignment import align_depth
from walkway_monitor.detection.components import (
    clean_changed_mask,
    filter_components_by_area,
    largest_component,
    measure_walkway_clearance,
)
from walkway_monitor.detection.models import (
    DetectionOutput,
    DetectionResult,
    OccupancyState,
)
from walkway_monitor.models import BaselineArtifact


class OccupancyDetector:
    """Căn chỉnh robust rồi so sánh depth với baseline theo từng frame."""

    def __init__(self, baseline: BaselineArtifact, config: DetectionConfig):
        """Chuẩn bị mask và threshold chuẩn hóa dùng chung cho detector."""
        # Bước 1: kiểm tra dữ liệu baseline và các tham số detection trước khi
        # tạo những dữ liệu trung gian dùng chung cho tất cả frame.
        baseline.validate()
        config.validate()
        self._baseline = baseline
        self._config = config

        # Bước 2: chuyển polygon ROI thành mask toàn ảnh. Đây là vùng duy nhất
        # được dùng để tính diện tích vật cản, quyết định trạng thái và vẽ đỏ.
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

        # Bước 9: bắt đầu đánh số các depth map được process() xử lý từ 0.
        self._frame_index = 0

    # ─────────────────────────────────────────────────────────────────────────

    def process(self, current_depth: np.ndarray) -> DetectionOutput:
        """Xử lý một depth map và trả về trạng thái cùng các mask debug."""
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
        # padding sẽ không được vẽ và không tham gia quyết định trạng thái.
        decision_mask = cleaned_check_mask
        decision_mask[~self._roi] = 0

        # Bước 7: bỏ các component quá nhỏ rồi dùng chính mask này cho cả phần
        # hiển thị lẫn đánh giá bề rộng, tránh vật cản vô hình làm đổi trạng thái.
        changed_mask = filter_components_by_area(
            decision_mask,
            self._display_minimum_area,
        )

        # Bước 8: giữ thống kê component và diện tích để debug, nhưng không dùng
        # diện tích tổng để quyết định lối đi có bị chặn hay không.
        component = largest_component(changed_mask)
        largest_area_ratio = component.area / self._roi_area
        changed_area_ratio = float(np.count_nonzero(changed_mask) / self._roi_area)

        # Bước 9: trên mỗi hàng của polygon ROI, đo khoảng trống liên tục lớn
        # nhất từ trái sang phải. Median trên vài hàng lân cận giúp một hàng
        # pixel nhiễu không trở thành nút thắt giả.
        clearance = measure_walkway_clearance(
            changed_mask,
            self._roi_mask,
            self._config.width_smoothing_rows,
        )
        width_blocked = (
            clearance.minimum_free_width_ratio
            < self._config.minimum_free_width_ratio
        )

        # Bước 10: kết luận trực tiếp theo bề rộng còn trống của frame hiện tại,
        # không chờ xác nhận qua nhiều frame.
        state = (
            OccupancyState.OCCUPIED
            if width_blocked
            else OccupancyState.CLEAR
        )

        # Bước 11: đóng gói trạng thái và các số liệu debug của frame hiện tại.
        result = DetectionResult(
            state=state,
            width_blocked=width_blocked,
            largest_component_area=component.area,
            bounding_box=component.bounding_box,
            largest_area_ratio=float(largest_area_ratio),
            changed_area_ratio=changed_area_ratio,
            minimum_free_width_ratio=clearance.minimum_free_width_ratio,
            obstacle_width_ratio=clearance.obstacle_width_ratio,
            bottleneck_row=clearance.bottleneck_row,
            bottleneck_span=clearance.bottleneck_span,
            alignment_scale=scale,
            alignment_shift=shift,
            alignment_inlier_ratio=self._config.alignment_inlier_ratio,
            alignment_enabled=self._config.depth_alignment,
            frame_index=self._frame_index,
            timestamp=time.time(),
        )

        # Bước 12: tăng frame index và trả cả kết quả logic lẫn các map dùng để
        # render giao diện, heatmap và mask đỏ.
        self._frame_index += 1
        return DetectionOutput(
            result=result,
            raw_depth=depth,
            aligned_depth=aligned,
            check_area_mask=self._check_area_mask,
            changed_mask=changed_mask,
            normalized_difference=normalized_difference,
            threshold_map=self._threshold_map,
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
