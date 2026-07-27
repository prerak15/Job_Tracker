"""Shared atomic JSON persistence for the tracker's data files.

Every domain (jobs, resumes, dsa) is a single pretty-printed JSON file under
data/. Writes go to a temp file in the same directory and are then os.replace'd,
so an interrupted write can never leave a half-written file behind.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# One lock per file so the three domains don't block each other.
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def lock_for(filename: str) -> threading.RLock:
    with _locks_guard:
        if filename not in _locks:
            _locks[filename] = threading.RLock()
        return _locks[filename]


def today() -> str:
    return date.today().isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def read(filename: str, key: str) -> dict[str, Any]:
    """Load data/<filename>; returns {key: [...]} even if the file is absent."""
    path = DATA_DIR / filename
    if not path.exists():
        return {key: []}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not valid JSON ({exc}). Fix or restore the file before continuing."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise ValueError(f'{path} must be an object with a "{key}" array.')
    return data


def write(filename: str, data: dict[str, Any]) -> None:
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def apply_defaults(record: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Fill missing/None keys so hand-edited records still work everywhere."""
    out = dict(record)
    out.setdefault("id", new_id())
    for field, default in defaults.items():
        if out.get(field) is None:
            out[field] = copy.deepcopy(default)
    return out


def pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0
