"""STAC catalogue adapter."""

from __future__ import annotations

from typing import Any

from ..coverage import classify_bbox_coverage
from .base import BaseSourceAdapter


class StacSourceAdapter(BaseSourceAdapter):
    def _root(self) -> str:
        return str(self.dataset["access_endpoint"]).rstrip("/")

    def get_metadata(self) -> dict[str, Any]:
        collection = str(self.dataset["collection_id"])
        payload = self.client.request("GET", f"{self._root()}/collections/{collection}").json()
        self._collection = payload
        bands = payload.get("bands") or payload.get("summaries", {}).get("eo:bands") or []
        return {
            "catalogue_verified": True,
            "bands": [band.get("name", band) if isinstance(band, dict) else band for band in bands],
        }

    def get_spatial_extent(self) -> Any:
        extent = getattr(self, "_collection", {}).get("extent", {}).get("spatial", {}).get("bbox", [])
        valid = [values for values in extent if isinstance(values, list) and len(values) >= 4]
        if valid:
            return [
                min(values[0] for values in valid),
                min(values[1] for values in valid),
                max(values[-2] for values in valid),
                max(values[-1] for values in valid),
            ]
        return super().get_spatial_extent()

    def get_temporal_extent(self) -> tuple[str, str]:
        intervals = getattr(self, "_collection", {}).get("extent", {}).get("temporal", {}).get("interval", [])
        if intervals:
            start, end = intervals[0]
            return start or "UNKNOWN", end or "PRESENT"
        return "UNKNOWN", "UNKNOWN"

    def check_aoi_intersection(self, aoi: Any) -> Any:
        return classify_bbox_coverage(aoi.bounds, self.get_spatial_extent())

    def get_minimal_sample(self, aoi: Any) -> dict[str, Any]:
        params = {
            "collections": str(self.dataset["collection_id"]),
            "bbox": ",".join(str(value) for value in aoi.bounds),
            "limit": 1,
        }
        return self.client.request("GET", f"{self._root()}/search", params=params, use_cache=False).json()

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        features = sample.get("features", []) if isinstance(sample, dict) else []
        if isinstance(sample, dict):
            self.metadata["record_count"] = (
                sample.get("numberMatched")
                or sample.get("context", {}).get("matched")
                or sample.get("numberReturned")
                or len(features)
            )
        if not features:
            return "NO_VALID_DATA", "STAC search returned no AOI-intersecting item"
        assets = features[0].get("assets", {})
        self.metadata["bands"] = self.metadata.get("bands") or list(assets)
        return "VALID_RECORDS", "STAC returned an AOI-intersecting item record"

    def get_access_information(self) -> str:
        return "AUTOMATED_OPEN"
