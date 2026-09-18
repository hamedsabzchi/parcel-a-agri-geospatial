from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parcel_a_geo.aoi import (  # noqa: E402
    REPORT_VERTICES_UTM33N,
    build_feature_collection,
    build_summary,
    is_simple_ring,
    polygon_area_m2,
    report_points,
    utm33n_to_wgs84,
)


class TestReportAOI(unittest.TestCase):
    def test_source_has_seven_unique_vertices(self) -> None:
        self.assertEqual(len(REPORT_VERTICES_UTM33N), 7)
        self.assertEqual(len(set(report_points())), 7)

    def test_polygon_is_simple(self) -> None:
        self.assertTrue(is_simple_ring(report_points()))

    def test_area_matches_report_within_point_one_percent(self) -> None:
        area_ha = polygon_area_m2(report_points()) / 10000.0
        self.assertAlmostEqual(area_ha, 5127.480571516418, places=6)
        self.assertLess(abs(area_ha - 5128.69) / 5128.69 * 100.0, 0.1)

    def test_location_is_in_expected_cameroon_extent(self) -> None:
        lon, lat = utm33n_to_wgs84(380375.67136140884, 731146.4554194005)
        self.assertTrue(13.8 < lon < 14.0)
        self.assertTrue(6.5 < lat < 6.7)

    def test_geojson_ring_is_closed(self) -> None:
        feature_collection = build_feature_collection()
        ring = feature_collection["features"][0]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(len(ring), 8)

    def test_checked_in_summary_matches_calculation(self) -> None:
        checked = json.loads((ROOT / "data/aoi/aoi_candidate_summary.json").read_text())
        calculated = build_summary()
        self.assertAlmostEqual(
            checked["computed_area_ha"], calculated["computed_area_ha"], places=9
        )
        self.assertEqual(checked["g0_gate"], "HOLD")


if __name__ == "__main__":
    unittest.main()
