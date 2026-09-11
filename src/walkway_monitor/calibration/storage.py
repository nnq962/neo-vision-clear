"""Lưu và đọc baseline bằng định dạng NPZ không sử dụng pickle."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np

from utils.logger import LOGGER
from walkway_monitor.models import BaselineArtifact, RoiDefinition, WorldCoordinates


def save_baseline(artifact: BaselineArtifact, path: str | Path) -> Path:
    """Lưu artifact vào NPZ, tạo JSON đi kèm và trả về đường dẫn NPZ."""
    # Bước 1: kiểm tra artifact và chuẩn hóa đường dẫn file baseline.
    artifact.validate()
    output_path = Path(path)
    if output_path.suffix.lower() != ".npz":
        output_path = output_path.with_suffix(".npz")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = _build_metadata(artifact)

    # Bước 2: ghi NPZ vào file tạm rồi thay thế nguyên tử file đích.
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

    # Bước 3: xuất metadata và các điểm ROI sang JSON dễ đọc cùng tên.
    json_path = _save_baseline_json(artifact, output_path.with_suffix(".json"))
    LOGGER.info("Đã lưu baseline: %s", output_path)
    LOGGER.info("Đã lưu metadata baseline: %s", json_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────


def _save_baseline_json(artifact: BaselineArtifact, path: str | Path) -> Path:
    """Lưu metadata và ROI của baseline vào file JSON dễ đọc."""
    # Bước 1: tạo payload chỉ gồm metadata nhỏ và tọa độ ROI chuẩn hóa.
    artifact.validate()
    output_path = Path(path).with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_metadata(artifact)
    payload["roi_points_normalized"] = (
        artifact.roi.normalized_points.astype(np.float32).tolist()
    )
    if artifact.roi.world_coordinates is not None:
        world = artifact.roi.world_coordinates
        payload["world_coordinates"] = {
            "unit": world.unit,
            "origin": world.origin,
            "x_axis": world.x_axis,
            "y_axis": world.y_axis,
            "points": np.round(world.points.astype(np.float64), 6).tolist(),
        }

    # Bước 2: ghi qua file tạm để không để lại JSON dở dang nếu có lỗi.
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return output_path


# ─────────────────────────────────────────────────────────────────────────────


def _build_metadata(artifact: BaselineArtifact) -> dict[str, object]:
    """Tạo metadata dùng chung cho nội dung NPZ và file JSON đi kèm."""
    return {
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
            roi_points = data["roi_points_normalized"].astype(np.float32)
            world_coordinates = _load_world_coordinates(input_path, roi_points)
            artifact = BaselineArtifact(
                reference_depth=data["reference_depth"].astype(np.float32),
                noise_map=data["noise_map"].astype(np.float32),
                roi=RoiDefinition(
                    normalized_points=roi_points,
                    world_coordinates=world_coordinates,
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


# ─────────────────────────────────────────────────────────────────────────────


def _load_world_coordinates(
    baseline_path: Path,
    roi_points: np.ndarray,
) -> WorldCoordinates | None:
    """Đọc hệ tọa độ thực tùy chọn từ file JSON cùng tên baseline."""
    # Bước 1: giữ tương thích với baseline cũ chưa có file JSON đi kèm.
    json_path = baseline_path.with_suffix(".json")
    if not json_path.is_file():
        return None

    # Bước 2: đọc JSON và bỏ qua khi chưa khai báo tọa độ thực.
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON baseline không hợp lệ: {json_path}") from exc
    world_payload = payload.get("world_coordinates")
    if world_payload is None:
        return None

    # Bước 3: bảo đảm JSON thuộc đúng NPZ trước khi ghép tọa độ theo index.
    try:
        json_roi_points = np.asarray(
            payload["roi_points_normalized"],
            dtype=np.float32,
        )
        if json_roi_points.shape != roi_points.shape or not np.allclose(
            json_roi_points,
            roi_points,
            rtol=0.0,
            atol=1e-6,
        ):
            raise ValueError("ROI trong JSON không khớp với baseline NPZ.")
        world_coordinates = WorldCoordinates(
            points=np.asarray(world_payload["points"], dtype=np.float32),
            unit=str(world_payload["unit"]),
            origin=str(world_payload["origin"]),
            x_axis=str(world_payload["x_axis"]),
            y_axis=str(world_payload["y_axis"]),
        )
        world_coordinates.validate(len(roi_points))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Tọa độ thực trong JSON không hợp lệ: {json_path}") from exc
    return world_coordinates
