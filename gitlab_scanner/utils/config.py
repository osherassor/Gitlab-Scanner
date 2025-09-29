import os
import yaml
from typing import Any, Dict, Optional


DEFAULT_CONFIG_PATH = os.path.join("config", "scan_config.yaml")


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(config_path):
        return {
            "logging": {"level": "info", "color": "auto", "timestamps": True, "banners": True},
            "output": {"write_jsonl": True, "live_snapshot": {"enabled": True, "interval_seconds": 5, "max_batch": 500, "pretty": True}},
            "http": {"verify_ssl": False},
            "execution": {"timeout_seconds": 20, "rate_limit_rps": 5, "retries": 1, "backoff": {"initial_ms": 500, "max_ms": 5000, "factor": 2.0}},
            "scan": {"max_file_size_bytes": 104857600, "api_page_size": 100, "refs": "default"},
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


