"""Configuration loading for Stage 02 data discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DATASET_REQUIRED_FIELDS = (
    "dataset_id",
    "source_name",
    "dataset_name",
    "provider",
    "source_group",
    "agricultural_theme",
    "description",
    "catalogue_url",
    "access_type",
    "access_endpoint",
    "collection_id",
    "expected_spatial_coverage",
    "expected_temporal_coverage",
    "spatial_resolution",
    "temporal_resolution",
    "variables",
    "units",
    "CRS",
    "NoData",
    "licence",
    "citation",
    "authentication_requirement",
    "verification_method",
    "initial_priority",
    "notes",
)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping and reject invalid root values."""

    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {source}")
    return payload


def load_project_config(path: str | Path) -> dict[str, Any]:
    """Load and validate Stage 02 project settings."""

    config = load_yaml(path)
    required = {
        "project_name",
        "aoi_path",
        "aoi_identifier",
        "output_directory",
        "cache_directory",
        "request_timeout_seconds",
        "retry_limit",
        "earth_engine_enabled",
        "maximum_download_mb",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Missing project configuration fields: {', '.join(missing)}")
    return config


def load_dataset_registry(path: str | Path) -> list[dict[str, Any]]:
    """Load datasets, fill explicit UNKNOWN values, and enforce unique IDs."""

    payload = load_yaml(path)
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("datasets.yml must contain a non-empty datasets list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(datasets, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Dataset record {index} must be a mapping")
        item = dict(raw)
        for field in DATASET_REQUIRED_FIELDS:
            value = item.get(field, "UNKNOWN")
            item[field] = "UNKNOWN" if value is None or value == "" else value
        dataset_id = str(item["dataset_id"])
        if dataset_id == "UNKNOWN":
            raise ValueError(f"Dataset record {index} has no dataset_id")
        if dataset_id in seen:
            raise ValueError(f"Duplicate dataset_id: {dataset_id}")
        seen.add(dataset_id)
        normalized.append(item)
    return normalized


def project_path(project_root: str | Path, configured_path: str | Path) -> Path:
    """Resolve a configured path relative to the repository root."""

    value = Path(configured_path)
    return value if value.is_absolute() else Path(project_root) / value
