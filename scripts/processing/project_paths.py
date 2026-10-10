"""Shared paths for the supported Stage 7/8 pipeline; importing creates no files."""

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def configured_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else default.resolve()


DATA_ROOT = configured_path("AIRBORNE_LIDAR_PROJECT_DATA_ROOT", REPO_ROOT / "data")
STAGE_ROOT = configured_path("AIRBORNE_LIDAR_STAGE_ROOT", REPO_ROOT / "outputs" / "stages")
