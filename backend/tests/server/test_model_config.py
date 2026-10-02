"""Kiểm tra cấu hình model mặc định trong tài liệu backend."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.models.config import RuntimeConfig
from server.services.config_store import ConfigStore
from server.settings import ServerSettings


class ModelConfigTestCase(unittest.TestCase):
    """Bảo đảm settings đọc JSON và store giữ cấu hình model khi ghi."""

    def test_model_config_survives_runtime_update(self) -> None:
        """Cập nhật runtime không được xóa lựa chọn TensorRT trong JSON."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({
                    "version": 2,
                    "model": {
                        "depth_backend": "tensorrt",
                        "tensorrt_engine_directory": "/models/tensorrt",
                    },
                }),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"NVC_CONFIG_PATH": str(path)}):
                settings = ServerSettings.from_env()
            self.assertEqual(settings.depth_backend, "tensorrt")
            self.assertEqual(settings.tensorrt_engine_directory, "/models/tensorrt")

            ConfigStore(path).update_runtime(RuntimeConfig())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["model"]["depth_backend"], "tensorrt")
            self.assertEqual(
                saved["model"]["tensorrt_engine_directory"], "/models/tensorrt"
            )
