from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from parcel_a_geo.sources.base import BaseSourceAdapter
from parcel_a_geo.sources.earth_engine import EarthEngineSourceAdapter
from parcel_a_geo.validation import load_aoi, validate_values


ROOT = Path(__file__).resolve().parents[1]


class FailingAdapter(BaseSourceAdapter):
    def get_metadata(self):
        raise TimeoutError("mock timeout")


class TestValidation(unittest.TestCase):
    def test_aoi_loading_and_crs_conversion(self) -> None:
        aoi = load_aoi(ROOT / "data/aoi/parcel_a.geojson")
        self.assertEqual(aoi.identifier, "PARCEL_A")
        self.assertEqual(aoi.wgs84.crs.to_epsg(), 4326)
        self.assertEqual(aoi.geometry.geom_type, "Polygon")
        self.assertTrue(13.8 < aoi.centroid[0] < 14.0)

    def test_invalid_geometry_is_rejected(self) -> None:
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.geojson"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_aoi(path)

    def test_nodata_only_sample(self) -> None:
        status, _ = validate_values([None, -999, float("nan"), float("inf"), "metadata"], nodata=-999)
        self.assertEqual(status, "NO_VALID_DATA")

    def test_timeout_is_recorded_without_stopping(self) -> None:
        aoi = load_aoi(ROOT / "data/aoi/parcel_a.geojson")
        adapter = FailingAdapter(
            {
                "dataset_id": "MOCK_TIMEOUT",
                "dataset_name": "Mock timeout",
                "source_group": "Test",
                "source_name": "Test",
                "provider": "Test",
                "expected_bbox": [-180, -90, 180, 90],
                "initial_priority": "CORE",
            },
            {},
            aoi,
            object(),
        )
        record = adapter.run()
        self.assertEqual(record["valid_data_status"], "VERIFICATION_FAILED")
        self.assertIn("mock timeout", record["failure_reason"])

    def test_invalid_endpoint_is_recorded(self) -> None:
        aoi = load_aoi(ROOT / "data/aoi/parcel_a.geojson")
        adapter = BaseSourceAdapter(
            {
                "dataset_id": "MOCK_ENDPOINT",
                "dataset_name": "Mock endpoint",
                "source_group": "Test",
                "source_name": "Test",
                "provider": "Test",
                "catalogue_url": "UNKNOWN",
                "expected_bbox": [-180, -90, 180, 90],
                "initial_priority": "CORE",
            },
            {},
            aoi,
            object(),
        )
        record = adapter.run()
        self.assertEqual(record["access_status"], "VERIFICATION_FAILED")
        self.assertIn("AttributeError", record["failure_reason"])

    def test_missing_earth_engine_credentials(self) -> None:
        aoi = load_aoi(ROOT / "data/aoi/parcel_a.geojson")
        adapter = EarthEngineSourceAdapter(
            {
                "dataset_id": "MOCK_EE",
                "dataset_name": "Mock Earth Engine",
                "source_group": "Test",
                "source_name": "Test",
                "provider": "Test",
                "expected_bbox": [-180, -90, 180, 90],
                "initial_priority": "CORE",
            },
            {"earth_engine_enabled": False},
            aoi,
            object(),
        )
        record = adapter.run()
        self.assertEqual(record["access_status"], "AUTOMATED_AUTHENTICATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
