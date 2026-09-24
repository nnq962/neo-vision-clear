"""Kiểm thử round-trip của định dạng baseline NPZ."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from walkway_monitor.calibration.storage import (
    artifact_path_for_id,
    delete_artifacts_for_id,
    load_baseline,
    save_baseline,
)
from walkway_monitor.models import BaselineArtifact, RoiDefinition, WorldCoordinates


class BaselineStorageTestCase(unittest.TestCase):
    """Kiểm tra artifact không mất dữ liệu sau khi lưu và đọc lại."""

    def test_save_and_load_without_pickle(self) -> None:
        """Baseline NPZ phải round-trip và tạo JSON metadata tương ứng."""
        roi = RoiDefinition(
            normalized_points=np.array(
                [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8]], dtype=np.float32
            ),
            world_coordinates=WorldCoordinates(
                points=np.array(
                    [[0.0, 0.0], [1.75, 0.0], [1.75, 4.55]],
                    dtype=np.float32,
                ),
                unit="m",
                origin="P1",
                x_axis="Từ trái sang phải",
                y_axis="Từ trên xuống dưới",
            ),
        )
        artifact = BaselineArtifact(
            reference_depth=np.arange(24, dtype=np.float32).reshape(4, 6),
            noise_map=np.full((4, 6), 0.02, dtype=np.float32),
            roi=roi,
            frame_width=6,
            frame_height=4,
            encoder="vits",
            input_size=518,
            frame_count=60,
            created_at="2026-09-04T00:00:00+00:00",
            source_type="VIDEO",
            alignment_median_error=0.01,
            noise_p99=0.02,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = save_baseline(artifact, Path(directory) / "baseline")
            loaded = load_baseline(path)
            with np.load(path, allow_pickle=False) as raw:
                self.assertIn("metadata_json", raw.files)
            json_path = path.with_suffix(".json")
            self.assertTrue(json_path.is_file())
            exported = json.loads(json_path.read_text(encoding="utf-8"))
        np.testing.assert_array_equal(loaded.reference_depth, artifact.reference_depth)
        np.testing.assert_array_equal(loaded.noise_map, artifact.noise_map)
        np.testing.assert_allclose(
            loaded.roi.normalized_points,
            artifact.roi.normalized_points,
        )
        self.assertEqual(loaded.encoder, artifact.encoder)
        np.testing.assert_allclose(
            exported["roi_points_normalized"],
            artifact.roi.normalized_points,
        )
        self.assertEqual(exported["format_version"], artifact.format_version)
        self.assertEqual(exported["frame_width"], artifact.frame_width)
        self.assertEqual(exported["frame_height"], artifact.frame_height)
        self.assertIsNotNone(loaded.roi.world_coordinates)
        np.testing.assert_allclose(
            loaded.roi.world_coordinates.points,
            artifact.roi.world_coordinates.points,
        )
        self.assertEqual(exported["world_coordinates"]["unit"], "m")

    # ─────────────────────────────────────────────────────────────────────────

    def test_artifact_path_groups_files_by_baseline_id(self) -> None:
        """Helper phải đặt file chính trong thư mục mang ID baseline."""
        path = artifact_path_for_id("data/baselines", "abc123")

        self.assertEqual(
            path,
            Path("data/baselines/abc123/baseline.npz"),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_delete_artifacts_removes_baseline_directory(self) -> None:
        """Xóa baseline phải dọn artifact trong thư mục ID tương ứng."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical_directory = root / "abc123"
            canonical_directory.mkdir()
            for filename in (
                "baseline.npz",
                "baseline.json",
                "baseline.preview.jpg",
                "baseline.depth.jpg",
            ):
                (canonical_directory / filename).touch()
            removed = delete_artifacts_for_id(root, "abc123")

            self.assertEqual(len(removed), 4)
            self.assertFalse(canonical_directory.exists())
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
