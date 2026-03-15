from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PipelineConfig:
    paths: dict[str, str]
    fmriprep: dict[str, Any]
    extract: dict[str, Any]


def load_config(config_path: str | Path) -> PipelineConfig:
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    paths = raw.get("paths", {}) or {}
    fmriprep = raw.get("fmriprep", {}) or {}
    extract = raw.get("extract", {}) or {}

    if not isinstance(paths, dict) or not isinstance(fmriprep, dict) or not isinstance(extract, dict):
        raise ValueError("Invalid config: expected mappings at top-level keys paths/fmriprep/extract")

    return PipelineConfig(paths=paths, fmriprep=fmriprep, extract=extract)
