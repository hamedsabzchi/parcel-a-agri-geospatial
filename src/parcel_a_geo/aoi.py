"""Core AOI calculations with no third-party dependency.

The production Colab notebook uses GeoPandas, Shapely and PyProj as an
independent implementation.  These standard-library functions keep the source
coordinates testable in lightweight CI and make the reconstruction auditable.
"""

from __future__ import annotations

from math import cos, degrees, hypot, radians, sin, sqrt, tan
from typing import Iterable, Sequence

Point = tuple[float, float]

REPORT_VERTICES_UTM33N: tuple[tuple[str, float, float, float], ...] = (
    ("A1", 375142.89553203, 730553.78023993, 927.0),
    ("A2", 381315.67865558, 726934.57048810, 952.0),
    ("A3", 386655.47274849, 730036.88441500, 933.0),
    ("A4", 381124.21918453, 733184.44527635, 918.0),
    ("A5", 382254.47034824, 735241.34560231, 914.0),
    ("A6", 380256.00132039, 736073.12628858, 912.0),
    ("A7", 376031.75713711, 732703.05038135, 925.0),
)

REPORTED_AREA_HA = 5128.69


def report_points() -> list[Point]:
    return [(row[1], row[2]) for row in REPORT_VERTICES_UTM33N]


def signed_double_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        raise ValueError("A polygon requires at least three vertices.")
    return sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )


def polygon_area_m2(points: Sequence[Point]) -> float:
    """Planar polygon area in square metres for projected input coordinates."""
    return abs(signed_double_area(points)) / 2.0


def polygon_perimeter_m(points: Sequence[Point]) -> float:
    return sum(
        hypot(
            points[i][0] - points[(i + 1) % len(points)][0],
            points[i][1] - points[(i + 1) % len(points)][1],
        )
        for i in range(len(points))
    )


def polygon_centroid(points: Sequence[Point]) -> Point:
    area2 = signed_double_area(points)
    if area2 == 0:
        raise ValueError("Cannot calculate the centroid of a zero-area polygon.")
    cx = sum(
        (points[i][0] + points[(i + 1) % len(points)][0])
        * (
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
        )
        for i in range(len(points))
    ) / (3.0 * area2)
    cy = sum(
        (points[i][1] + points[(i + 1) % len(points)][1])
        * (
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
        )
        for i in range(len(points))
    ) / (3.0 * area2)
    return cx, cy


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point, eps: float = 1e-9) -> bool:
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
        and abs(_cross(a, b, p)) <= eps
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if (ab_c > 0 > ab_d or ab_d > 0 > ab_c) and (
        cd_a > 0 > cd_b or cd_b > 0 > cd_a
    ):
        return True
    return (
        _on_segment(a, b, c)
        or _on_segment(a, b, d)
        or _on_segment(c, d, a)
        or _on_segment(c, d, b)
    )


def is_simple_ring(points: Sequence[Point]) -> bool:
    """Return False when non-adjacent polygon edges intersect."""
    n = len(points)
    if n < 3 or len(set(points)) != n:
        return False
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = points[j], points[(j + 1) % n]
            if _segments_intersect(a, b, c, d):
                return False
    return True


def utm33n_to_wgs84(easting: float, northing: float) -> Point:
    """Convert WGS84 / UTM zone 33N to longitude and latitude.

    Formula follows the standard inverse Transverse Mercator expansion and is
    used here only for deterministic source-data QA. PyProj is used in Colab.
    """
    semi_major = 6378137.0
    flattening = 1.0 / 298.257223563
    e2 = flattening * (2.0 - flattening)
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996

    x = easting - 500000.0
    meridional_arc = northing / k0
    mu = meridional_arc / (
        semi_major * (1.0 - e2 / 4.0 - 3.0 * e2**2 / 64.0 - 5.0 * e2**3 / 256.0)
    )
    e1 = (1.0 - sqrt(1.0 - e2)) / (1.0 + sqrt(1.0 - e2))
    footpoint = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * sin(2.0 * mu)
        + (21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0) * sin(4.0 * mu)
        + 151.0 * e1**3 / 96.0 * sin(6.0 * mu)
        + 1097.0 * e1**4 / 512.0 * sin(8.0 * mu)
    )

    c1 = ep2 * cos(footpoint) ** 2
    t1 = tan(footpoint) ** 2
    n1 = semi_major / sqrt(1.0 - e2 * sin(footpoint) ** 2)
    r1 = semi_major * (1.0 - e2) / (1.0 - e2 * sin(footpoint) ** 2) ** 1.5
    d = x / (n1 * k0)

    latitude = footpoint - (n1 * tan(footpoint) / r1) * (
        d**2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1**2 - 9.0 * ep2) * d**4 / 24.0
        + (
            61.0
            + 90.0 * t1
            + 298.0 * c1
            + 45.0 * t1**2
            - 252.0 * ep2
            - 3.0 * c1**2
        )
        * d**6
        / 720.0
    )
    longitude = radians(15.0) + (
        d
        - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
        + (
            5.0
            - 2.0 * c1
            + 28.0 * t1
            - 3.0 * c1**2
            + 8.0 * ep2
            + 24.0 * t1**2
        )
        * d**5
        / 120.0
    ) / cos(footpoint)
    return degrees(longitude), degrees(latitude)


def build_feature_collection() -> dict:
    points_wgs84 = [utm33n_to_wgs84(x, y) for x, y in report_points()]
    closed = points_wgs84 + [points_wgs84[0]]
    summary = build_summary()
    return {
        "type": "FeatureCollection",
        "name": "parcel_a_report_reconstructed",
        "bbox": summary["bounds_wgs84"],
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "aoi_id": "parcel_a",
                    "name": "Parcel A Dir 1",
                    "country": "Cameroon",
                    "region": "Adamaoua",
                    "department": "Mbere",
                    "municipality": "Dir",
                    "source": "Final characterization report table 1",
                    "source_crs": "EPSG:32633",
                    "status": "reconstructed_pending_confirmation",
                    "reported_area_ha": REPORTED_AREA_HA,
                    "computed_area_ha": summary["computed_area_ha"],
                    "g0_gate": "HOLD",
                },
                "geometry": {"type": "Polygon", "coordinates": [closed]},
            }
        ],
    }


def build_summary() -> dict:
    points = report_points()
    area_m2 = polygon_area_m2(points)
    area_ha = area_m2 / 10000.0
    centroid_utm = polygon_centroid(points)
    centroid_wgs = utm33n_to_wgs84(*centroid_utm)
    wgs_points = [utm33n_to_wgs84(x, y) for x, y in points]
    delta_ha = area_ha - REPORTED_AREA_HA
    return {
        "aoi_id": "parcel_a",
        "status": "reconstructed_pending_confirmation",
        "g0_gate": "HOLD",
        "source_crs": "EPSG:32633",
        "exchange_crs": "EPSG:4326",
        "vertex_count": len(points),
        "geometry_type": "Polygon",
        "is_simple": is_simple_ring(points),
        "ring_orientation": (
            "counterclockwise" if signed_double_area(points) > 0 else "clockwise"
        ),
        "computed_area_m2": area_m2,
        "computed_area_ha": area_ha,
        "reported_area_ha": REPORTED_AREA_HA,
        "area_difference_ha": delta_ha,
        "area_difference_percent": delta_ha / REPORTED_AREA_HA * 100.0,
        "perimeter_m": polygon_perimeter_m(points),
        "centroid_utm33n": list(centroid_utm),
        "centroid_wgs84": list(centroid_wgs),
        "bounds_utm33n": [
            min(x for x, _ in points),
            min(y for _, y in points),
            max(x for x, _ in points),
            max(y for _, y in points),
        ],
        "bounds_wgs84": [
            min(x for x, _ in wgs_points),
            min(y for _, y in wgs_points),
            max(x for x, _ in wgs_points),
            max(y for _, y in wgs_points),
        ],
        "confirmation_required": True,
    }
