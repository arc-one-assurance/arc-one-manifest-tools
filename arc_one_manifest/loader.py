from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def load_manifest(path: str | Path) -> Dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest must be a YAML mapping")
    return data
