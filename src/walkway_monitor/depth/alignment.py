"""Căn chỉnh scale và shift giữa các relative depth map."""

from __future__ import annotations

import numpy as np


def fit_affine_alignment(
    current: np.ndarray,
    reference: np.ndarray,
    support_mask: np.ndarray | None = None,
    max_samples: int = 60_000,
    iterations: int = 4,
    inlier_ratio: float = 0.55,
    candidate_count: int = 128,
) -> tuple[float, float]:
    """Fit affine robust bằng cách tìm mô hình nền rồi loại pixel ngoại lai."""
    if current.shape != reference.shape:
        raise ValueError("Hai depth map phải có cùng kích thước.")
    if current.ndim != 2:
        raise ValueError("Depth map phải là mảng hai chiều.")
    if support_mask is not None and support_mask.shape != current.shape:
        raise ValueError("support_mask phải cùng kích thước với depth map.")
    if not 0.5 < inlier_ratio <= 1.0:
        raise ValueError("inlier_ratio phải nằm trong (0.5, 1].")
    if iterations < 1:
        raise ValueError("iterations phải lớn hơn hoặc bằng 1.")
    if candidate_count < 1:
        raise ValueError("candidate_count phải lớn hơn hoặc bằng 1.")

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

    # Tìm mô hình khởi tạo theo kiểu least-median-squares. Mỗi candidate được
    # tạo từ hai pixel; mô hình khớp với phần nền chiếm đa số sẽ có percentile
    # residual thấp hơn mô hình chỉ khớp với người hoặc vật cản.
    candidate_size = min(4096, x.size)
    candidate_positions = np.linspace(
        0,
        x.size - 1,
        candidate_size,
        dtype=np.int64,
    )
    candidate_x = x[candidate_positions]
    candidate_y = y[candidate_positions]
    score_index = min(
        candidate_size - 1,
        max(0, int(np.ceil(candidate_size * inlier_ratio)) - 1),
    )
    rng = np.random.default_rng(0)
    first = rng.integers(0, candidate_size, size=candidate_count)
    second = rng.integers(0, candidate_size, size=candidate_count)

    scale = 1.0
    shift = float(np.median(candidate_y - candidate_x))
    initial_residual = np.abs(scale * candidate_x + shift - candidate_y)
    best_score = float(np.partition(initial_residual, score_index)[score_index])
    for first_index, second_index in zip(first, second):
        delta_x = candidate_x[second_index] - candidate_x[first_index]
        if abs(delta_x) < 1e-8:
            continue
        candidate_scale = (
            candidate_y[second_index] - candidate_y[first_index]
        ) / delta_x
        if not np.isfinite(candidate_scale) or candidate_scale <= 0.0:
            continue
        candidate_shift = float(
            np.median(candidate_y - candidate_scale * candidate_x)
        )
        residual = np.abs(
            candidate_scale * candidate_x + candidate_shift - candidate_y
        )
        score = float(np.partition(residual, score_index)[score_index])
        if score < best_score:
            scale = float(candidate_scale)
            shift = candidate_shift
            best_score = score

    # Giữ cố định tỷ lệ pixel có residual nhỏ nhất rồi fit lại. Vì vật cản là
    # outlier so với mặt sàn baseline, nó không còn đủ sức kéo scale/shift.
    keep_count = min(
        x.size,
        max(2, int(np.ceil(x.size * inlier_ratio))),
    )
    for _ in range(iterations):
        residual = np.abs(scale * x + shift - y)
        keep_indices = np.argpartition(residual, keep_count - 1)[:keep_count]
        matrix = np.column_stack(
            (x[keep_indices], np.ones(keep_indices.size))
        )
        new_scale, new_shift = np.linalg.lstsq(
            matrix,
            y[keep_indices],
            rcond=None,
        )[0]
        if not np.isfinite(new_scale) or new_scale <= 0.0:
            break
        if np.isclose(new_scale, scale) and np.isclose(new_shift, shift):
            scale, shift = float(new_scale), float(new_shift)
            break
        scale, shift = float(new_scale), float(new_shift)
    return float(scale), float(shift)


# ─────────────────────────────────────────────────────────────────────────────


def align_depth(
    current: np.ndarray,
    reference: np.ndarray,
    support_mask: np.ndarray | None = None,
    inlier_ratio: float = 0.55,
) -> tuple[np.ndarray, float, float]:
    """Căn chỉnh depth hiện tại và trả về depth mới cùng scale, shift đã fit."""
    scale, shift = fit_affine_alignment(
        current,
        reference,
        support_mask,
        inlier_ratio=inlier_ratio,
    )
    aligned = current.astype(np.float32) * np.float32(scale) + np.float32(shift)
    return aligned.astype(np.float32, copy=False), scale, shift
