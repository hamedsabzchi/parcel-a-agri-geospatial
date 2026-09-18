"""Earth Engine metadata and bounded native-scale sample adapter."""

from __future__ import annotations

import os
from typing import Any

from .base import BaseSourceAdapter
from ..validation import validate_values


class EarthEngineSourceAdapter(BaseSourceAdapter):
    def _initialize(self) -> Any:
        if not bool(self.config.get("earth_engine_enabled", False)):
            raise PermissionError("Earth Engine checks are disabled")
        import ee

        variable = str(
            self.config.get("earth_engine_project_environment_variable", "EARTH_ENGINE_PROJECT")
        )
        project = os.getenv(variable)
        if not project:
            raise PermissionError(f"Earth Engine project is missing from environment variable {variable}")
        ee.Initialize(project=project)
        ee.data.setDeadline(60000)
        return ee

    def get_metadata(self) -> dict[str, Any]:
        self.ee = self._initialize()
        identifier = str(self.dataset["collection_id"])
        kind = str(self.dataset.get("collection_kind", "IMAGE_COLLECTION"))
        self.object = self.ee.Image(identifier) if kind == "IMAGE" else self.ee.ImageCollection(identifier)
        return {"catalogue_verified": True}

    def get_minimal_sample(self, aoi: Any) -> dict[str, Any]:
        location = aoi.geometry.representative_point()
        point = self.ee.Geometry.Point([location.x, location.y])
        aoi_geometry = self.ee.Geometry(aoi.geometry.__geo_interface__)
        kind = str(self.dataset.get("collection_kind", "IMAGE_COLLECTION"))
        if kind == "IMAGE":
            image = self.object
            count = 1
            first_date = latest_date = "STATIC"
        else:
            full_collection = self.object.filterBounds(aoi_geometry)
            count = int(full_collection.size().getInfo())
            if count == 0:
                return {"count": 0, "values": {}, "bands": []}
            first_millis = full_collection.aggregate_min("system:time_start").getInfo()
            latest_millis = full_collection.aggregate_max("system:time_start").getInfo()
            first_date = (
                self.ee.Date(first_millis).format("YYYY-MM-dd").getInfo()
                if first_millis is not None
                else "UNKNOWN"
            )
            latest_date = (
                self.ee.Date(latest_millis).format("YYYY-MM-dd").getInfo()
                if latest_millis is not None
                else "UNKNOWN"
            )
            collection = full_collection
            test_dates = self.config.get("test_dates", {})
            if test_dates:
                test_collection = full_collection.filterDate(
                    test_dates.get("start"), test_dates.get("end")
                )
                if int(test_collection.size().getInfo()) > 0:
                    collection = test_collection
            image = self.ee.Image(collection.first())
        bands = image.bandNames().getInfo()
        scale = image.select(0).projection().nominalScale().getInfo()
        values = image.reduceRegion(
            reducer=self.ee.Reducer.first(),
            geometry=point,
            scale=scale,
            bestEffort=True,
            maxPixels=100000,
        ).getInfo()
        return {
            "image_id": image.id().getInfo(),
            "point": [location.x, location.y],
            "properties": image.toDictionary(["model", "scenario", "system:time_start"]).getInfo(),
            "count": count,
            "values": values,
            "bands": bands,
            "scale": scale,
            "first_date": first_date,
            "latest_date": latest_date,
        }

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        self.metadata["bands"] = sample.get("bands", []) if isinstance(sample, dict) else []
        self.metadata["record_count"] = (
            sample.get("count", "UNKNOWN") if isinstance(sample, dict) else "UNKNOWN"
        )
        self.metadata["nominal_scale_metres"] = (
            sample.get("scale", "UNKNOWN") if isinstance(sample, dict) else "UNKNOWN"
        )
        self._sample_dates = (
            sample.get("first_date", "UNKNOWN"),
            sample.get("latest_date", "UNKNOWN"),
        )
        if not sample or sample.get("count", 0) == 0:
            return "NO_VALID_DATA", "Earth Engine returned no AOI-intersecting image"
        values = sample.get("values", {})
        status, note = validate_values(values.values())
        self.metadata.update(sample_kind="PIXEL_VALUES", sample=sample)
        if status != "VALID_DATA":
            return "NO_VALID_DATA", "Earth Engine point sample is entirely NoData"
        return "VALID_DATA", f"Earth Engine returned {sample['count']} image record(s); {note}. Verification covers this sample only."

    def get_temporal_extent(self) -> tuple[str, str]:
        return getattr(self, "_sample_dates", ("UNKNOWN", "UNKNOWN"))

    def get_access_information(self) -> str:
        return "AUTOMATED_OPEN"

    def run(self) -> dict[str, Any]:
        if not bool(self.config.get("earth_engine_enabled", False)):
            self.coverage = self.check_aoi_intersection(self.aoi)
            self.access_status = "AUTOMATED_AUTHENTICATION_REQUIRED"
            self.validation_note = "Earth Engine was not enabled; no availability claim was made"
            return self.return_inventory_record()
        return super().run()
