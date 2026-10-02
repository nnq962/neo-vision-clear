"""Kiểm tra manifest và shape đầu vào của nhánh thử TensorRT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from depth_anything_v2.dpt import prepare_image
from walkway_monitor.depth.tensorrt_estimator import (
    dynamic_engine_path,
    read_engine_metadata,
)


class TensorRTMetadataTestCase(unittest.TestCase):
    """Bảo đảm engine chỉ dùng với checkpoint và baseline tương ứng."""

    # ─────────────────────────────────────────────────────────────────────────

    def test_matches_live_two_camera_shape_and_checkpoint(self) -> None:
        """Manifest đúng cho phép chạy batch hai frame 960x540."""
        # Bước 1: xác nhận transform tạo shape dùng để build engine.
        tensor, original = prepare_image(
            np.zeros((540, 960, 3), dtype=np.uint8), 280
        )
        self.assertEqual(tuple(tensor.shape), (3, 280, 504))
        self.assertEqual(original, (540, 960))

        # Bước 2: kiểm tra manifest ràng buộc checkpoint và cấu hình model.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "model.pth"
            checkpoint.write_bytes(b"checkpoint")
            engine = root / "model.engine"
            engine.write_bytes(b"engine")
            metadata = {
                "schema_version": 1,
                "encoder": "vits",
                "input_size": 280,
                "input_shape": [2, 3, 280, 504],
                "precision": "fp16",
                "checkpoint_sha256": hashlib.sha256(b"checkpoint").hexdigest(),
            }
            Path(f"{engine}.json").write_text(json.dumps(metadata))
            self.assertEqual(
                read_engine_metadata(engine, "vits", 280, checkpoint), metadata
            )
            with self.assertRaisesRegex(ValueError, "input_size"):
                read_engine_metadata(engine, "vits", 518, checkpoint)
            checkpoint.write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "checkpoint khác"):
                read_engine_metadata(engine, "vits", 280, checkpoint)

    # ─────────────────────────────────────────────────────────────────────────

    def test_dynamic_engine_path_uses_preprocessing_shape(self) -> None:
        """Các input size hiện có ánh xạ đúng bốn engine batch động."""
        for size, width in ((140, 252), (196, 350), (224, 392), (280, 504)):
            with self.subTest(size=size):
                path = dynamic_engine_path("/models", "vits", size, 960, 540)
                self.assertEqual(path.name, f"vits-b1-2-{size}x{width}.engine")


if __name__ == "__main__":
    unittest.main()
