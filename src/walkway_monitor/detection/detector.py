"""Detector thuần chuyển một depth map thành trạng thái chiếm dụng lối đi."""

from __future__ import annotations

import time

import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.alignment import align_depth
from walkway_monitor.detection.components import clean_changed_mask, largest_component
from walkway_monitor.detection.models import DetectionOutput, DetectionResult
from walkway_monitor.detection.temporal_filter import TemporalOccupancyFilter
from walkway_monitor.models import BaselineArtifact


class OccupancyDetector:
    """So sánh depth hiện tại với baseline và ổn định kết quả theo thời gian."""

    def __init__(self, baseline: BaselineArtifact, config: DetectionConfig):
        """Chuẩn bị mask, threshold chuẩn hóa và temporal filter cho detector."""
        baseline.validate()
        config.validate()
        self._baseline = baseline
        self._config = config
        self._roi_mask = baseline.roi.to_mask(
            baseline.frame_width,
            baseline.frame_height,
        )
        self._roi = self._roi_mask > 0
        self._support = ~self._roi
        self._roi_area = int(np.count_nonzero(self._roi))
        support_area = int(np.count_nonzero(self._support))
        minimum_support = max(10, int(self._support.size * 0.001))
        if self._roi_area < 100:
            raise ValueError("ROI baseline quá nhỏ để chạy detection.")
        if support_area < minimum_support:
            raise ValueError(
                "Vùng ngoài ROI quá nhỏ để căn chỉnh depth; hãy calibration ROI hẹp hơn."
            )
        reference_values = baseline.reference_depth[np.isfinite(baseline.reference_depth)]
        self._depth_span = float(
            np.percentile(reference_values, 95.0)
            - np.percentile(reference_values, 5.0)
        )
        self._depth_span = max(self._depth_span, 1e-6)
        normalized_noise = baseline.noise_map / np.float32(self._depth_span)
        self._threshold_map = np.maximum(
            np.float32(config.minimum_difference),
            normalized_noise * np.float32(config.noise_multiplier),
        ).astype(np.float32)
        kernel_size = max(
            3,
            int(round(min(baseline.frame_height, baseline.frame_width) / config.morphology_divisor)),
        )
        self._kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
        self._temporal_filter = TemporalOccupancyFilter(
            occupied_frames=config.occupied_frames,
            clear_frames=config.clear_frames,
        )
        self._frame_index = 0

    # ─────────────────────────────────────────────────────────────────────────

    def process(self, current_depth: np.ndarray) -> DetectionOutput:
        """Xử lý một depth map và trả về trạng thái cùng các mask debug."""
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

        aligned, scale, shift = align_depth(
            depth,
            self._baseline.reference_depth,
            self._support,
        )
        normalized_difference = (
            np.abs(aligned - self._baseline.reference_depth) / self._depth_span
        ).astype(np.float32)
        health_threshold = np.maximum(
            self._threshold_map,
            np.float32(self._config.camera_difference_threshold),
        )
        outside_change_ratio = float(
            np.count_nonzero(
                (normalized_difference >= health_threshold) & self._support
            )
            / np.count_nonzero(self._support)
        )
        camera_is_stable = (
            outside_change_ratio < self._config.camera_change_area_ratio
        )

        raw_mask = (
            (normalized_difference >= self._threshold_map) & self._roi
        ).astype(np.uint8) * 255
        changed_mask = clean_changed_mask(
            raw_mask,
            self._roi_mask,
            self._kernel_size,
        )
        component = largest_component(changed_mask)
        largest_area_ratio = component.area / self._roi_area
        changed_area_ratio = float(np.count_nonzero(changed_mask) / self._roi_area)
        raw_occupied = largest_area_ratio >= self._config.minimum_area_ratio
        state = self._temporal_filter.update(
            raw_occupied=raw_occupied,
            valid=camera_is_stable,
        )
        reason = None if camera_is_stable else "camera_or_scene_changed"
        result = DetectionResult(
            state=state,
            raw_occupied=raw_occupied if camera_is_stable else False,
            largest_component_area=component.area,
            bounding_box=component.bounding_box,
            largest_area_ratio=float(largest_area_ratio),
            changed_area_ratio=changed_area_ratio,
            outside_change_ratio=outside_change_ratio,
            alignment_scale=scale,
            alignment_shift=shift,
            frame_index=self._frame_index,
            timestamp=time.time(),
            reason=reason,
        )
        self._frame_index += 1
        return DetectionOutput(
            result=result,
            aligned_depth=aligned,
            changed_mask=changed_mask,
            normalized_difference=normalized_difference,
            threshold_map=self._threshold_map,
        )
