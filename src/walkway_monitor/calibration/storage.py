"""Lưu và đọc baseline bằng định dạng NPZ không sử dụng pickle."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np

from utils.logger import LOGGER
from walkway_monitor.models import BaselineArtifact, RoiDefinition


def save_baseline(artifact: BaselineArtifact, path: str | Path) -> Path:
    """Lưu artifact nguyên tử vào file NPZ và trả về đường dẫn thực tế."""
    artifact.validate()
    output_path = Path(path)
    if output_path.suffix.lower() != ".npz":
        output_path = output_path.with_suffix(".npz")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "format_version": artifact.format_version,
        "frame_width": artifact.frame_width,
        "frame_height": artifact.frame_height,
        "encoder": artifact.encoder,
        "input_size": artifact.input_size,
        "frame_count": artifact.frame_count,
        "created_at": artifact.created_at,
        "source_type": artifact.source_type,
        "alignment_median_error": artifact.alignment_median_error,
        "noise_p99": artifact.noise_p99,
    }

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            np.savez_compressed(
                temporary_file,
                reference_depth=artifact.reference_depth.astype(np.float32),
                noise_map=artifact.noise_map.astype(np.float32),
                roi_points_normalized=artifact.roi.normalized_points.astype(np.float32),
                metadata_json=np.asarray(json.dumps(metadata, ensure_ascii=False)),
            )
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    LOGGER.info("Đã lưu baseline: %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────


def load_baseline(path: str | Path) -> BaselineArtifact:
    """Đọc baseline NPZ an toàn, kiểm tra schema và trả về artifact."""
    input_path = Path(path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy baseline: {input_path}")
    try:
        with np.load(input_path, allow_pickle=False) as data:
            required = {
                "reference_depth",
                "noise_map",
                "roi_points_normalized",
                "metadata_json",
            }
            missing = required - set(data.files)
            if missing:
                raise ValueError(f"Baseline thiếu trường: {sorted(missing)}")
            metadata = json.loads(str(data["metadata_json"].item()))
            artifact = BaselineArtifact(
                reference_depth=data["reference_depth"].astype(np.float32),
                noise_map=data["noise_map"].astype(np.float32),
                roi=RoiDefinition(
                    normalized_points=data["roi_points_normalized"].astype(np.float32)
                ),
                frame_width=int(metadata["frame_width"]),
                frame_height=int(metadata["frame_height"]),
                encoder=str(metadata["encoder"]),
                input_size=int(metadata["input_size"]),
                frame_count=int(metadata["frame_count"]),
                created_at=str(metadata["created_at"]),
                source_type=str(metadata["source_type"]),
                alignment_median_error=float(metadata["alignment_median_error"]),
                noise_p99=float(metadata["noise_p99"]),
                format_version=int(metadata["format_version"]),
            )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Metadata baseline không hợp lệ: {input_path}") from exc
    artifact.validate()
    return artifact
