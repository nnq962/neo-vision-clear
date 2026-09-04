"""Căn chỉnh scale và shift giữa các relative depth map."""

from __future__ import annotations

import numpy as np


def fit_affine_alignment(
    current: np.ndarray,
    reference: np.ndarray,
    support_mask: np.ndarray | None = None,
    max_samples: int = 60_000,
    iterations: int = 3,
) -> tuple[float, float]:
    """Fit quan hệ ``reference ≈ scale * current + shift`` bằng hồi quy robust."""
    if current.shape != reference.shape:
        raise ValueError("Hai depth map phải có cùng kích thước.")
    if current.ndim != 2:
        raise ValueError("Depth map phải là mảng hai chiều.")
    if support_mask is not None and support_mask.shape != current.shape:
        raise ValueError("support_mask phải cùng kích thước với depth map.")

    valid = np.isfinite(current) & np.isfinite(reference)
    if support_mask is not None:
        valid &= support_mask.astype(bool)
    indices = np.flatnonzero(valid)
    if indices.size < 2:
        raise ValueError("Không có đủ pixel hợp lệ để căn chỉnh depth.")
    if indices.size > max_samples:
        sample_positions = np.linspace(
            0, indices.size - 1, max_samples, dtype=np.int64
        )
        indices = indices[sample_positions]

    x = current.ravel()[indices].astype(np.float64)
    y = reference.ravel()[indices].astype(np.float64)
    if float(np.std(x)) < 1e-8:
        return 1.0, float(np.median(y) - np.median(x))

    keep = np.ones(x.shape, dtype=bool)
    scale, shift = 1.0, 0.0
    for _ in range(iterations):
        matrix = np.column_stack((x[keep], np.ones(np.count_nonzero(keep))))
        scale, shift = np.linalg.lstsq(matrix, y[keep], rcond=None)[0]
        residual = scale * x + shift - y
        center = float(np.median(residual))
        mad = float(np.median(np.abs(residual - center)))
        limit = max(3.5 * 1.4826 * mad, 1e-7)
        new_keep = np.abs(residual - center) <= limit
        if np.count_nonzero(new_keep) < 2 or np.array_equal(new_keep, keep):
            break
        keep = new_keep
    return float(scale), float(shift)


# ─────────────────────────────────────────────────────────────────────────────


def align_depth(
    current: np.ndarray,
    reference: np.ndarray,
    support_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, float, float]:
    """Căn chỉnh depth hiện tại và trả về depth mới cùng scale, shift đã fit."""
    scale, shift = fit_affine_alignment(current, reference, support_mask)
    aligned = current.astype(np.float32) * np.float32(scale) + np.float32(shift)
    return aligned.astype(np.float32, copy=False), scale, shift
