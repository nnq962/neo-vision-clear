"""Kiểm thử round-trip của định dạng baseline NPZ."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from walkway_monitor.calibration.storage import load_baseline, save_baseline
from walkway_monitor.models import BaselineArtifact, RoiDefinition


class BaselineStorageTestCase(unittest.TestCase):
    """Kiểm tra artifact không mất dữ liệu sau khi lưu và đọc lại."""

    def test_save_and_load_without_pickle(self) -> None:
        """Baseline NPZ phải round-trip đầy đủ với allow_pickle=False."""
        roi = RoiDefinition(
            normalized_points=np.array(
                [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8]], dtype=np.float32
            )
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
        np.testing.assert_array_equal(loaded.reference_depth, artifact.reference_depth)
        np.testing.assert_array_equal(loaded.noise_map, artifact.noise_map)
        np.testing.assert_allclose(
            loaded.roi.normalized_points,
            artifact.roi.normalized_points,
        )
        self.assertEqual(loaded.encoder, artifact.encoder)


if __name__ == "__main__":
    unittest.main()
