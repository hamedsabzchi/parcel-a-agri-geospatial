"""Local project vector and raster discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd

from ..validation import validate_values
from .base import BaseSourceAdapter


class LocalProjectSourceAdapter(BaseSourceAdapter):
    def _candidates(self) -> list[Path]:
        root = Path(str(self.config.get("project_root", ".")))
        configured = root / str(self.dataset.get("local_path", "UNKNOWN"))
        if configured.is_file():
            return [configured]
        if configured.is_dir():
            return sorted(
                path for path in configured.rglob("*") if path.suffix.lower() in {".geojson", ".gpkg", ".shp", ".tif", ".tiff"}
            )
        return []

    def get_metadata(self) -> dict[str, Any]:
        files = self._candidates()
        if not files:
            raise FileNotFoundError(f"No local source file found at {self.dataset.get('local_path')}")
        self._path = files[0]
        if self._path.suffix.lower() in {".geojson", ".gpkg", ".shp"}:
            frame = gpd.read_file(self._path)
            if frame.crs is None:
                raise ValueError(f"Local vector CRS is missing: {self._path}")
            self._frame = frame.to_crs("EPSG:4326")
            self._spatial_extent = list(self._frame.total_bounds)
            return {
                "catalogue_verified": True,
                "bands": list(frame.columns.drop(frame.geometry.name)),
                "record_count": len(frame),
                "CRS": str(frame.crs),
            }

        import rasterio
        from rasterio.warp import transform_bounds

        with rasterio.open(self._path) as dataset:
            self._spatial_extent = list(
                transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)
            )
            self._nodata = dataset.nodata
            return {
                "catalogue_verified": True,
                "bands": list(range(1, dataset.count + 1)),
                "record_count": dataset.count,
                "CRS": str(dataset.crs),
                "NoData": dataset.nodata,
                "spatial_resolution": list(dataset.res),
            }

    def get_spatial_extent(self) -> Any:
        return getattr(self, "_spatial_extent", "UNKNOWN")

    def get_minimal_sample(self, aoi: Any) -> Any:
        if self._path.suffix.lower() in {".geojson", ".gpkg", ".shp"}:
            return self._frame[self._frame.intersects(aoi.geometry)].head(
                int(self.config.get("maximum_vector_features", 1000))
            )

        import rasterio
        from pyproj import Transformer

        with rasterio.open(self._path) as dataset:
            transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
            x, y = transformer.transform(*aoi.centroid)
            return list(dataset.sample([(x, y)], masked=True))[0].tolist()

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        if hasattr(sample, "empty"):
            return ("VALID_DATA", "Local vector intersects AOI") if not sample.empty else (
                "NO_VALID_DATA",
                "Local vector has no AOI-intersecting feature",
            )
        return validate_values(sample or [], nodata=getattr(self, "_nodata", None))

    def get_access_information(self) -> str:
        return "AUTOMATED_OPEN"
