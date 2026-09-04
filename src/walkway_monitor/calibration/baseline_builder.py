"""Thuật toán tổng hợp nhiều relative depth map thành baseline ổn định."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from walkway_monitor.config import CalibrationConfig
from walkway_monitor.depth.alignment import align_depth
from walkway_monitor.models import BaselineArtifact, RoiDefinition


def build_baseline(
    depth_maps: list[np.ndarray],
    roi: RoiDefinition,
    config: CalibrationConfig,
    source_type: str,
) -> BaselineArtifact:
    """Căn chỉnh depth, lấy median và ước lượng noise map của cảnh trống."""
    config.validate()
    if len(depth_maps) != config.frame_count:
        raise ValueError(
            f"Cần đúng {config.frame_count} depth map, nhận được {len(depth_maps)}."
        )
    stack = _validate_and_stack(depth_maps)
    provisional_reference = np.median(stack, axis=0).astype(np.float32)

    alignment_errors: list[float] = []
    for index in range(stack.shape[0]):
        aligned, _scale, _shift = align_depth(stack[index], provisional_reference)
        stack[index] = aligned

    reference = np.median(stack, axis=0).astype(np.float32)
    for index in range(stack.shape[0]):
        aligned, _scale, _shift = align_depth(stack[index], reference)
        stack[index] = aligned
        alignment_errors.append(float(np.median(np.abs(aligned - reference))))

    reference = np.median(stack, axis=0).astype(np.float32)
    np.subtract(stack, reference[None, :, :], out=stack)
    np.abs(stack, out=stack)
    noise_map = (1.4826 * np.median(stack, axis=0)).astype(np.float32)

    height, width = reference.shape
    artifact = BaselineArtifact(
        reference_depth=reference,
        noise_map=noise_map,
        roi=roi,
        frame_width=width,
        frame_height=height,
        encoder=config.encoder,
        input_size=config.input_size,
        frame_count=config.frame_count,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_type=source_type,
        alignment_median_error=float(np.median(alignment_errors)),
        noise_p99=float(np.percentile(noise_map, 99.0)),
    )
    artifact.validate()
    return artifact


# ─────────────────────────────────────────────────────────────────────────────


def _validate_and_stack(depth_maps: list[np.ndarray]) -> np.ndarray:
    """Kiểm tra danh sách depth map rồi ghép thành tensor float32 ba chiều."""
    if not depth_maps:
        raise ValueError("Danh sách depth map không được rỗng.")
    expected_shape = np.asarray(depth_maps[0]).shape
    if len(expected_shape) != 2:
        raise ValueError("Depth map phải là mảng hai chiều.")
    normalized: list[np.ndarray] = []
    for depth in depth_maps:
        array = np.asarray(depth, dtype=np.float32)
        if array.shape != expected_shape:
            raise ValueError("Tất cả depth map phải có cùng kích thước.")
        if not np.all(np.isfinite(array)):
            raise ValueError("Depth map chứa giá trị không hữu hạn.")
        normalized.append(array)
    return np.stack(normalized, axis=0)
