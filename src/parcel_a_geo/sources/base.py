"""Common adapter interface and bounded network client."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from ..coverage import CoverageResult, classify_bbox_coverage
from ..inventory import assign_processing_priority, normalize_record
from ..metadata import utc_now
from ..validation import AOIContext


@dataclass
class NetworkResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class NetworkClient:
    """HTTP client with timeouts, bounded retries, size limits, and GET caching."""

    def __init__(self, config: dict[str, Any], cache_dir: str | Path) -> None:
        self.timeout = float(config.get("request_timeout_seconds", 20))
        self.retries = int(config.get("retry_limit", 2))
        self.maximum_bytes = int(float(config.get("maximum_download_mb", 10)) * 1024 * 1024)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": str(config.get("user_agent", "parcel-a-stage02/1.0"))})

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json_body: Any = None,
        maximum_bytes: int | None = None,
        use_cache: bool = True,
    ) -> NetworkResponse:
        if not url or url == "UNKNOWN":
            raise ValueError("No valid endpoint was configured")
        limit = self.maximum_bytes if maximum_bytes is None else maximum_bytes
        cache_key = hashlib.sha256(
            f"{method.upper()}|{url}|{urlencode(sorted((params or {}).items()))}".encode()
        ).hexdigest()
        cache_file = self.cache_dir / f"{cache_key}.json"
        if method.upper() == "GET" and use_cache and cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return NetworkResponse(
                status_code=int(cached["status_code"]),
                headers=cached.get("headers", {}),
                content=bytes.fromhex(cached["content_hex"]),
                url=cached.get("url", url),
            )

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with self.session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    json=json_body,
                    timeout=self.timeout,
                    stream=True,
                ) as response:
                    if response.status_code >= 500 and attempt < self.retries:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    declared = int(response.headers.get("Content-Length", "0") or 0)
                    if declared and declared > limit:
                        raise ValueError(f"Response exceeds {limit} byte Stage 02 limit")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_content(64 * 1024):
                        total += len(chunk)
                        if total > limit:
                            raise ValueError(f"Response exceeds {limit} byte Stage 02 limit")
                        chunks.append(chunk)
                    result = NetworkResponse(
                        status_code=response.status_code,
                        headers={key: value for key, value in response.headers.items()},
                        content=b"".join(chunks),
                        url=response.url,
                    )
                    if method.upper() == "GET" and use_cache:
                        cache_file.write_text(
                            json.dumps(
                                {
                                    "status_code": result.status_code,
                                    "headers": result.headers,
                                    "content_hex": result.content.hex(),
                                    "url": result.url,
                                }
                            ),
                            encoding="utf-8",
                        )
                    return result
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(str(last_error or "Network request failed"))


class BaseSourceAdapter(ABC):
    """Interface implemented by every Stage 02 source adapter."""

    def __init__(
        self,
        dataset: dict[str, Any],
        project_config: dict[str, Any],
        aoi: AOIContext,
        client: NetworkClient,
        logger: logging.Logger | None = None,
    ) -> None:
        self.dataset = dataset
        self.config = project_config
        self.aoi = aoi
        self.client = client
        self.logger = logger or logging.getLogger("parcel_a_stage02")
        self.failure_reason = "UNKNOWN"
        self.metadata: dict[str, Any] = {}
        self.coverage = CoverageResult("COVERAGE_UNKNOWN", "UNKNOWN", "Not checked")
        self.sample: Any = None
        self.valid_data_status = "UNKNOWN"
        self.validation_note = "UNKNOWN"
        self.access_status = "MANUAL_INSPECTION_REQUIRED"

    def get_metadata(self) -> dict[str, Any]:
        url = str(self.dataset.get("catalogue_url", "UNKNOWN"))
        if url == "LOCAL_PROJECT_DATA":
            return {"catalogue_verified": True}
        response = self.client.request("GET", url, maximum_bytes=2 * 1024 * 1024)
        return {"catalogue_verified": response.status_code < 400, "catalogue_response_url": response.url}

    def get_spatial_extent(self) -> Any:
        return self.dataset.get("expected_bbox", "UNKNOWN")

    def get_temporal_extent(self) -> tuple[str, str]:
        return "UNKNOWN", "UNKNOWN"

    def check_aoi_intersection(self, aoi: AOIContext) -> CoverageResult:
        return classify_bbox_coverage(aoi.bounds, self.get_spatial_extent())

    def get_minimal_sample(self, aoi: AOIContext) -> Any:
        return None

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        return "UNKNOWN", "No automated valid-data test is available"

    def get_access_information(self) -> str:
        access = str(self.dataset.get("access_type", "MANUAL_PORTAL"))
        if access in {"MANUAL_PORTAL", "DIRECT_DOWNLOAD", "PYTHON_SDK"}:
            return "MANUAL_INSPECTION_REQUIRED"
        return "AUTOMATED_OPEN"

    def agricultural_relevance(self) -> str:
        priority = str(self.dataset.get("initial_priority", "SUPPORTING"))
        return priority if priority in {"CORE", "SUPPORTING", "OPTIONAL", "NOT_RELEVANT"} else "SUPPORTING"

    def run(self) -> dict[str, Any]:
        dataset_id = str(self.dataset["dataset_id"])
        try:
            self.metadata = self.get_metadata()
            self.coverage = self.check_aoi_intersection(self.aoi)
            self.access_status = self.get_access_information()
            if self.coverage.status != "NO_COVERAGE":
                self.sample = self.get_minimal_sample(self.aoi)
                self.valid_data_status, self.validation_note = self.validate_sample(self.sample)
        except Exception as error:  # source failures must never stop Stage 02
            self.failure_reason = f"{type(error).__name__}: {error}"
            self.valid_data_status = "VERIFICATION_FAILED"
            if isinstance(error, FileNotFoundError):
                self.access_status = "UNAVAILABLE"
            elif isinstance(error, PermissionError):
                self.access_status = "AUTOMATED_AUTHENTICATION_REQUIRED"
            else:
                self.access_status = "VERIFICATION_FAILED"
            self.logger.warning("%s failed: %s", dataset_id, self.failure_reason)
        return self.return_inventory_record()

    def return_inventory_record(self) -> dict[str, Any]:
        earliest, latest = self.get_temporal_extent()
        record = {
            **self.dataset,
            "sample_kind": self.metadata.get("sample_kind", "NONE"),
            "sample_verified": self.valid_data_status == "VALID_DATA" and self.metadata.get("sample_kind") in {"PIXEL_VALUES", "POINT_VALUES", "FEATURE_VALUES"},
            "evidence_json": self.metadata,
            "access_status": self.access_status,
            "authentication_required": self.dataset.get("authentication_requirement", "UNKNOWN"),
            "AOI_coverage_status": self.coverage.status,
            "AOI_coverage_percentage": self.coverage.percentage,
            "valid_data_status": self.valid_data_status,
            "validation_method": self.dataset.get("verification_method", "UNKNOWN"),
            "validation_date_utc": utc_now(),
            "sample_location": f"POINT ({self.aoi.centroid[0]:.6f} {self.aoi.centroid[1]:.6f})",
            "earliest_date": earliest,
            "latest_date": latest,
            "spatial_resolution": self.metadata.get(
                "spatial_resolution", self.dataset.get("spatial_resolution", "UNKNOWN")
            ),
            "bands": self.metadata.get("bands", "UNKNOWN"),
            "record_count": self.metadata.get("record_count", "UNKNOWN"),
            "CRS": self.metadata.get("CRS", self.dataset.get("CRS", "UNKNOWN")),
            "NoData": self.metadata.get("NoData", self.dataset.get("NoData", "UNKNOWN")),
            "agricultural_relevance": self.agricultural_relevance(),
            "failure_reason": self.failure_reason,
            "notes": f"{self.dataset.get('notes', 'UNKNOWN')} | {self.validation_note}",
        }
        record["processing_priority"] = assign_processing_priority(record)
        record["recommended_stage"] = (
            "STAGE_03" if record["processing_priority"] == "USE_NEXT" else "LATER_OR_REVIEW"
        )
        return normalize_record(record)
