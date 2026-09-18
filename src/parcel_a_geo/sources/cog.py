"""Minimal COG-window adapter."""

from __future__ import annotations

from typing import Any

from ..validation import validate_values
from .base import BaseSourceAdapter


class CogSourceAdapter(BaseSourceAdapter):
    def get_metadata(self) -> dict[str, Any]:
        import rasterio
        from rasterio.warp import transform_bounds

        endpoint = str(self.dataset.get("access_endpoint", "UNKNOWN"))
        with rasterio.open(endpoint) as dataset:
            self._raster_metadata = {
                "bounds": list(dataset.bounds),
                "bounds_wgs84": list(
                    transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)
                ),
                "crs": str(dataset.crs),
                "bands": list(range(1, dataset.count + 1)),
                "nodata": dataset.nodata,
                "resolution": list(dataset.res),
            }
        return {
            "catalogue_verified": True,
            "bands": self._raster_metadata["bands"],
            "CRS": self._raster_metadata["crs"],
            "NoData": self._raster_metadata["nodata"],
            "spatial_resolution": self._raster_metadata["resolution"],
        }

    def get_spatial_extent(self) -> Any:
        return getattr(self, "_raster_metadata", {}).get("bounds_wgs84", "UNKNOWN")

    def get_minimal_sample(self, aoi: Any) -> list[Any]:
        import rasterio
        from pyproj import Transformer

        endpoint = str(self.dataset["access_endpoint"])
        with rasterio.open(endpoint) as dataset:
            transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
            x, y = transformer.transform(*aoi.centroid)
            values = list(dataset.sample([(x, y)]))[0]
            return values.tolist()

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        self.metadata.update(sample_kind="PIXEL_VALUES", sample_values=sample)
        nodata = getattr(self, "_raster_metadata", {}).get("nodata")
        status, note = validate_values(sample or [], nodata=nodata)
        return status, f"COG centroid sample: {note}"

    def get_access_information(self) -> str:
        return "AUTOMATED_OPEN"
