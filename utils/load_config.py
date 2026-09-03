from pathlib import Path

import yaml


def load_config(path: str = "configs/default.yaml") -> dict:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
