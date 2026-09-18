from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from parcel_a_geo.config import DATASET_REQUIRED_FIELDS, load_dataset_registry
from parcel_a_geo.inventory import INVENTORY_FIELDS, Inventory, assign_processing_priority, normalize_record
from parcel_a_geo.reporting import write_coverage_map, write_html_report
from parcel_a_geo.validation import load_aoi


ROOT = Path(__file__).resolve().parents[1]


class TestInventory(unittest.TestCase):
    def test_registry_fields_and_groups(self) -> None:
        registry = load_dataset_registry(ROOT / "config/datasets.yml")
        self.assertGreaterEqual(len(registry), 40)
        groups = {item["source_group"] for item in registry}
        self.assertTrue(
            {
                "FAO",
                "Earth observation",
                "Land cover and crop information",
                "Terrain and hydrology",
                "Soil and land resources",
                "Weather and historical climate",
                "Future climate",
                "Accessibility and agricultural context",
            }.issubset(groups)
        )
        for item in registry:
            self.assertTrue(set(DATASET_REQUIRED_FIELDS).issubset(item))

    def test_inventory_never_has_blank_fields(self) -> None:
        record = normalize_record({"dataset_id": "TEST", "dataset_name": ""})
        self.assertEqual(list(record), INVENTORY_FIELDS)
        self.assertTrue(all(value not in {None, ""} for value in record.values()))
        self.assertEqual(record["dataset_name"], "UNKNOWN")

    def test_status_assignment(self) -> None:
        use_next = assign_processing_priority(
            {
                "AOI_coverage_status": "FULL_COVERAGE",
                "valid_data_status": "VALID_DATA",
                "access_status": "AUTOMATED_OPEN",
                "agricultural_relevance": "CORE",
            }
        )
        self.assertEqual(use_next, "USE_NEXT")
        self.assertEqual(
            assign_processing_priority({"AOI_coverage_status": "NO_COVERAGE"}),
            "NO_COVERAGE",
        )
        self.assertEqual(
            assign_processing_priority(
                {
                    "AOI_coverage_status": "FULL_COVERAGE",
                    "valid_data_status": "VALID_DATA",
                    "access_status": "AUTOMATED_OPEN",
                    "agricultural_relevance": "OPTIONAL",
                }
            ),
            "OPTIONAL",
        )
        self.assertEqual(
            assign_processing_priority({"agricultural_relevance": "NOT_RELEVANT"}),
            "NOT_SUITABLE",
        )

    def test_output_file_creation(self) -> None:
        inventory = Inventory(
            [
                {
                    "dataset_id": "TEST",
                    "dataset_name": "Test dataset",
                    "AOI_coverage_status": "FULL_COVERAGE",
                    "valid_data_status": "VALID_RECORDS",
                    "access_status": "AUTOMATED_OPEN",
                    "processing_priority": "USE_NEXT",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = inventory.write(root / "tables", root / "metadata")
            aoi = load_aoi(ROOT / "data/aoi/parcel_a.geojson")
            report = write_html_report(inventory, aoi, root / "stage02_report.html")
            coverage_map = write_coverage_map(
                inventory,
                [
                    {
                        "dataset_id": "TEST",
                        "expected_bbox": [-180, -90, 180, 90],
                        "expected_spatial_coverage": "Global",
                    }
                ],
                aoi,
                root / "maps/data_coverage_map.html",
            )
            self.assertTrue(paths["csv"].exists())
            self.assertTrue(paths["xlsx"].exists())
            self.assertTrue(paths["json"].exists())
            self.assertTrue(report.exists())
            self.assertTrue(coverage_map.exists())


if __name__ == "__main__":
    unittest.main()
