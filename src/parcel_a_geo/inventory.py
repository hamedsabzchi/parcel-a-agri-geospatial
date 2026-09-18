"""Machine-readable inventory construction and export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


INVENTORY_FIELDS = [
    "dataset_id",
    "source_group",
    "source_name",
    "dataset_name",
    "provider",
    "agricultural_theme",
    "description",
    "catalogue_url",
    "access_endpoint",
    "access_type",
    "access_status",
    "authentication_required",
    "AOI_coverage_status",
    "AOI_coverage_percentage",
    "valid_data_status",
    "validation_method",
    "validation_date_utc",
    "sample_location",
    "spatial_resolution",
    "temporal_resolution",
    "earliest_date",
    "latest_date",
    "variables",
    "bands",
    "record_count",
    "units",
    "CRS",
    "NoData",
    "licence",
    "agricultural_relevance",
    "processing_priority",
    "recommended_stage",
    "failure_reason",
    "notes",
    "citation",
    "sample_kind",
    "sample_verified",
    "evidence_json",
]


def _flat(value: Any) -> Any:
    if value is None or value == "":
        return "UNKNOWN"
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value) if value else "UNKNOWN"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return one inventory record with no blank or ambiguous fields."""

    return {field: _flat(record.get(field, "UNKNOWN")) for field in INVENTORY_FIELDS}


def assign_processing_priority(record: dict[str, Any]) -> str:
    coverage = record.get("AOI_coverage_status")
    valid = record.get("valid_data_status")
    access = record.get("access_status")
    relevance = record.get("agricultural_relevance")
    if relevance == "NOT_RELEVANT":
        return "NOT_SUITABLE"
    if coverage == "NO_COVERAGE":
        return "NO_COVERAGE"
    if access in {"ACCESS_RESTRICTED", "AUTOMATED_AUTHENTICATION_REQUIRED"} and valid != "VALID_DATA":
        return "ACCESS_BLOCKED"
    if access in {"MANUAL_DOWNLOAD_AVAILABLE", "MANUAL_INSPECTION_REQUIRED"} or coverage == "COVERAGE_UNKNOWN":
        return "NEEDS_MANUAL_REVIEW"
    if valid in {"VERIFICATION_FAILED", "NO_VALID_DATA", "INVALID_RANGE", "UNKNOWN"}:
        return "NEEDS_MANUAL_REVIEW"
    if record.get("sample_verified") is False:
        return "NEEDS_MANUAL_REVIEW"
    if valid in {"VALID_DATA", "VALID_RECORDS"} and coverage in {"FULL_COVERAGE", "PARTIAL_COVERAGE"}:
        if relevance == "CORE":
            return "USE_NEXT"
        if relevance == "SUPPORTING":
            return "USE_LATER"
        return "OPTIONAL"
    return "OPTIONAL"


class Inventory:
    def __init__(self, records: Iterable[dict[str, Any]] = ()) -> None:
        self.records = [normalize_record(record) for record in records]

    def add(self, record: dict[str, Any]) -> None:
        self.records.append(normalize_record(record))

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.records, columns=INVENTORY_FIELDS)

    def summary(self) -> dict[str, int]:
        frame = self.frame()
        if frame.empty:
            return {
                "registered": 0,
                "verified": 0,
                "full_coverage": 0,
                "partial_coverage": 0,
                "no_coverage": 0,
                "manual_review": 0,
                "use_next": 0,
            }
        return {
            "registered": int(len(frame)),
            "verified": int(frame["sample_verified"].eq(True).sum()),
            "full_coverage": int((frame["AOI_coverage_status"] == "FULL_COVERAGE").sum()),
            "partial_coverage": int((frame["AOI_coverage_status"] == "PARTIAL_COVERAGE").sum()),
            "no_coverage": int((frame["AOI_coverage_status"] == "NO_COVERAGE").sum()),
            "manual_review": int((frame["processing_priority"] == "NEEDS_MANUAL_REVIEW").sum()),
            "use_next": int((frame["processing_priority"] == "USE_NEXT").sum()),
        }

    def write(self, table_dir: str | Path, metadata_dir: str | Path) -> dict[str, Path]:
        table_path = Path(table_dir)
        metadata_path = Path(metadata_dir)
        table_path.mkdir(parents=True, exist_ok=True)
        metadata_path.mkdir(parents=True, exist_ok=True)
        frame = self.frame()
        csv_path = table_path / "data_inventory.csv"
        xlsx_path = table_path / "data_inventory.xlsx"
        json_path = metadata_path / "data_inventory.json"
        frame.to_csv(csv_path, index=False, encoding="utf-8")
        frame.to_excel(xlsx_path, index=False, sheet_name="data_inventory")
        json_path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"csv": csv_path, "xlsx": xlsx_path, "json": json_path}
