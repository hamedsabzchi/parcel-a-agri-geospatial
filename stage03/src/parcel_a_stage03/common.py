from __future__ import annotations
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(data), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, rows, fields=()):
    rows = [clean(r) for r in rows]
    columns = list(dict.fromkeys([*fields, *(k for r in rows for k in r)]))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def code_hash():
    files=sorted(Path(__file__).parent.glob("*.py"))
    return hashlib.sha256("\n".join(p.name+":"+sha256(p) for p in files).encode()).hexdigest()


def relative_file(root, name):
    """Only regular, non-symlink files inside the selected package."""
    root = Path(root).resolve()
    p = Path(name)
    if p.is_absolute() or ".." in p.parts or "\\" in str(name):
        raise ValueError(f"Unsafe package path: {name}")
    full = root / p
    if root not in full.resolve().parents or any(q.is_symlink() for q in [full, *full.parents] if q != root):
        raise ValueError(f"Unsafe package member: {name}")
    if not full.is_file():
        raise ValueError(f"Missing package member: {name}")
    return full
