from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "notebooks/01_define_and_display_aoi.ipynb": "75b02d209dc1e3938820a69f78e2c94f967461fba29590835b230d182984c151",
    "data/aoi/aoi_candidate_wgs84.geojson": "559cad30500a878f8b76cb3f30ceb54bb272f434faf4021c1f891b38d140a528",
    "data/aoi/aoi_candidate_utm33n.gpkg": "8e93c4e9757056fa02cf068b31880f841ef0399cf2e7ac9ae613ef66d011b0d9",
    "outputs/maps/01_aoi_candidate.html": "23c113a3fd800572e373b7ec521ac914ee4c15ee7201222a84692d1311214a14",
    "outputs/maps/01_aoi_candidate.png": "457124b08ad4dd77a1411078d29eeba53fbc7b0c41aaf7fde09f00d381afc657",
    "outputs/maps/01_aoi_candidate.svg": "d67539ddc113f0ff80ff229acbf59cdd168f9781873c92a706fbe61caf5a67c7",
    "outputs/tables/01_aoi_validation.csv": "5c6fbf1bbef416a5ce34e66582b4e1a3dfe4beed8e93b6a8e114e3a289e40092",
}


class TestStage01Frozen(unittest.TestCase):
    def test_stage01_files_are_unchanged(self) -> None:
        for relative, expected in EXPECTED.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_stage02_aoi_geometry_matches_stage01(self) -> None:
        stage01 = json.loads((ROOT / "data/aoi/aoi_candidate_wgs84.geojson").read_text())
        stage02 = json.loads((ROOT / "data/aoi/parcel_a.geojson").read_text())
        self.assertEqual(
            stage01["features"][0]["geometry"],
            stage02["features"][0]["geometry"],
        )


if __name__ == "__main__":
    unittest.main()
