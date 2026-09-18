from __future__ import annotations

import unittest

from parcel_a_geo.coverage import classify_bbox_coverage


class TestCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.aoi = (13.87, 6.57, 13.98, 6.66)

    def test_full_coverage(self) -> None:
        result = classify_bbox_coverage(self.aoi, (-180, -90, 180, 90))
        self.assertEqual(result.status, "FULL_COVERAGE")
        self.assertEqual(result.percentage, 100.0)

    def test_partial_coverage(self) -> None:
        result = classify_bbox_coverage(self.aoi, (13.90, 6.50, 14.00, 6.70))
        self.assertEqual(result.status, "PARTIAL_COVERAGE")
        self.assertEqual(result.percentage, "UNKNOWN")

    def test_no_coverage(self) -> None:
        result = classify_bbox_coverage(self.aoi, (20, 20, 21, 21))
        self.assertEqual(result.status, "NO_COVERAGE")
        self.assertEqual(result.percentage, 0.0)

    def test_unknown_coverage(self) -> None:
        result = classify_bbox_coverage(self.aoi, "UNKNOWN")
        self.assertEqual(result.status, "COVERAGE_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
