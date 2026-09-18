"""Spatial coverage checks used by source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CoverageResult:
    status: str
    percentage: float | str
    reason: str


def _valid_bounds(bounds: Iterable[float] | object) -> tuple[float, float, float, float] | None:
    if isinstance(bounds, str):
        return None
    try:
        values = tuple(float(value) for value in bounds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if len(values) != 4:
        return None
    minx, miny, maxx, maxy = values
    if minx > maxx or miny > maxy:
        return None
    return minx, miny, maxx, maxy


def classify_bbox_coverage(
    aoi_bounds: Iterable[float], dataset_bounds: Iterable[float] | object
) -> CoverageResult:
    """Classify a dataset bounding box against the AOI bounding box."""

    aoi = _valid_bounds(aoi_bounds)
    dataset = _valid_bounds(dataset_bounds)
    if aoi is None:
        raise ValueError("AOI bounds must contain four ordered numeric values")
    if dataset is None:
        return CoverageResult("COVERAGE_UNKNOWN", "UNKNOWN", "No verified spatial extent")

    aminx, aminy, amaxx, amaxy = aoi
    dminx, dminy, dmaxx, dmaxy = dataset
    if dmaxx < aminx or dminx > amaxx or dmaxy < aminy or dminy > amaxy:
        return CoverageResult("NO_COVERAGE", 0.0, "Dataset extent does not intersect AOI")
    if dminx <= aminx and dminy <= aminy and dmaxx >= amaxx and dmaxy >= amaxy:
        return CoverageResult("FULL_COVERAGE", 100.0, "Dataset extent contains AOI")
    return CoverageResult(
        "PARTIAL_COVERAGE",
        "UNKNOWN",
        "Bounding boxes intersect but exact coverage percentage was not calculated",
    )
