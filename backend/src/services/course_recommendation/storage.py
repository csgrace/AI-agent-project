from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data" / "course_recommendation"
RAW_DIR = DATA_DIR / "raw"


def ensure_storage_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def store_raw_snapshot(prefix: str, payload: Any) -> Path:
    ensure_storage_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in {"-", "_"})
    file_path = RAW_DIR / f"{safe_prefix}_{stamp}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return file_path
