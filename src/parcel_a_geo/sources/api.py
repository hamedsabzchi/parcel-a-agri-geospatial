"""Small REST API queries for Stage 02."""

from __future__ import annotations

import json
from typing import Any

from ..validation import validate_values
from .base import BaseSourceAdapter


class ApiSourceAdapter(BaseSourceAdapter):
    def get_metadata(self) -> dict[str, Any]:
        endpoint = str(self.dataset.get("access_endpoint", "UNKNOWN"))
        if self.dataset["dataset_id"] in {"CLIMATE_NASA_POWER", "ACCESS_OSM"}:
            return {"catalogue_verified": True, "bands": str(self.dataset.get("variables"))}
        response = self.client.request("GET", endpoint, maximum_bytes=3 * 1024 * 1024)
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"response_bytes": len(response.content)}
        self._metadata_payload = payload
        return {"catalogue_verified": True}

    def get_minimal_sample(self, aoi: Any) -> Any:
        dataset_id = str(self.dataset["dataset_id"])
        lon, lat = aoi.centroid
        endpoint = str(self.dataset["access_endpoint"])
        if dataset_id == "CLIMATE_NASA_POWER":
            test_dates = self.config.get("test_dates", {})
            params = {
                "parameters": "PRECTOTCORR,T2M,T2M_MIN,T2M_MAX",
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": str(test_dates.get("start", "2024-01-01")).replace("-", ""),
                "end": str(test_dates.get("end", "2024-01-10")).replace("-", ""),
                "format": "JSON",
            }
            return self.client.request("GET", endpoint, params=params, use_cache=False).json()
        if dataset_id == "ACCESS_OSM":
            minx, miny, maxx, maxy = aoi.bounds
            query = (
                f"[out:json][timeout:15];(way[highway]({miny},{minx},{maxy},{maxx});"
                f"node[place]({miny},{minx},{maxy},{maxx});"
                f"nwr[amenity=marketplace]({miny},{minx},{maxy},{maxx}););out count;"
            )
            return self.client.request("POST", endpoint, data={"data": query}, use_cache=False).json()
        return getattr(self, "_metadata_payload", None)

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        dataset_id = str(self.dataset["dataset_id"])
        if dataset_id == "CLIMATE_NASA_POWER":
            parameters = sample.get("properties", {}).get("parameter", {}) if isinstance(sample, dict) else {}
            values = [value for series in parameters.values() for value in series.values()]
            self.metadata["record_count"] = len(values)
            return validate_values(values, nodata=-999)
        if dataset_id == "ACCESS_OSM":
            elements = sample.get("elements", []) if isinstance(sample, dict) else []
            if elements:
                self.metadata["record_count"] = elements[0].get("tags", {}).get("total", "UNKNOWN")
            return ("VALID_RECORDS", "Overpass returned a bounded count response") if elements else (
                "NO_VALID_DATA",
                "Overpass returned no count response",
            )
        if sample:
            return "VALID_RECORDS", "API returned a non-empty documented response"
        return "NO_VALID_DATA", "API returned an empty response"

    def get_access_information(self) -> str:
        return "AUTOMATED_OPEN"
