"""AOI and minimal-sample validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from .metadata import sha256_file


@dataclass
class AOIContext:
    identifier: str
    source_path: Path
    original: gpd.GeoDataFrame
    wgs84: gpd.GeoDataFrame
    geometry: BaseGeometry
    bounds: tuple[float, float, float, float]
    centroid: tuple[float, float]
    checksum: str


def load_aoi(path: str | Path, identifier: str = "PARCEL_A") -> AOIContext:
    """Load, validate, and prepare an AOI without modifying the source file."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"AOI file not found: {source}")
    frame = gpd.read_file(source)
    if frame.empty:
        raise ValueError("AOI is empty")
    if frame.crs is None:
        raise ValueError("AOI CRS is missing")
    if frame.geometry.is_empty.any() or frame.geometry.isna().any():
        raise ValueError("AOI contains empty geometry")
    if not frame.geometry.is_valid.all():
        raise ValueError("AOI geometry is invalid")
    if not frame.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("AOI must contain only Polygon or MultiPolygon geometry")

    original = frame.copy()
    wgs84 = frame.to_crs("EPSG:4326")
    geometry = wgs84.geometry.union_all()
    centroid_projected = frame.to_crs("EPSG:6933").geometry.union_all().centroid
    centroid = (
        gpd.GeoSeries([centroid_projected], crs="EPSG:6933")
        .to_crs("EPSG:4326")
        .iloc[0]
    )
    return AOIContext(
        identifier=identifier,
        source_path=source,
        original=original,
        wgs84=wgs84,
        geometry=geometry,
        bounds=tuple(float(value) for value in geometry.bounds),
        centroid=(float(centroid.x), float(centroid.y)),
        checksum=sha256_file(source),
    )


def validate_values(
    values: Iterable[Any], nodata: Any = None, valid_range: tuple[float, float] | None = None
) -> tuple[str, str]:
    """Validate a minimal value sample without inventing missing information."""

    cleaned = []
    for value in values:
        if value is None or value == nodata:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        cleaned.append(numeric)
    if not cleaned:
        return "NO_VALID_DATA", "Sample is empty or entirely NoData"
    if valid_range:
        lower, upper = valid_range
        numeric_values = [value for value in cleaned if isinstance(value, float)]
        if numeric_values and all(value < lower or value > upper for value in numeric_values):
            return "INVALID_RANGE", "All sampled numeric values are outside the documented range"
    return "VALID_DATA", f"{len(cleaned)} valid sampled value(s)"
