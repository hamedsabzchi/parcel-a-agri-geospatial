from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import yaml
from rasterio.transform import from_origin
from shapely.geometry import box, Polygon

from stage02_gaez_verification import EXPECTED_ASSET_KEYS, _asset_records, gaez_complete, verify_gaez_asset
from parcel_a_geo.config import load_dataset_registry
from parcel_a_geo.fao_priority import PRIORITY_IDS, _wapor_sample
from parcel_a_geo.inventory import Inventory
from parcel_a_geo.stage02 import consolidate, run_stage02, strict_inventory

ROOT = Path(__file__).resolve().parents[1]


def gaez_rows(good=16):
    return pd.DataFrame([dict(asset_key=k, verification_status="VERIFIED_INSIDE_AOI" if i < good else "FAILED_NO_VALID_AOI_PIXELS")
                         for i, k in enumerate(sorted(EXPECTED_ASSET_KEYS))])


def fake_records(registry):
    return Inventory([dict(r, sample_verified=False, sample_kind="CATALOGUE_RECORDS", access_status="AUTOMATED_OPEN",
                           valid_data_status="VALID_RECORDS", processing_priority="NEEDS_MANUAL_REVIEW",
                           AOI_coverage_status="FULL_COVERAGE", notes="Metadata only", failure_reason="NONE") for r in registry]).frame()


class TestGaezWindows(unittest.TestCase):
    def asset(self, path, code="RES05-YXX", nodata=-9, unit="kg"):
        return dict(asset_key="TEST", url=str(path), map_code=code, declared_nodata=nodata, declared_unit=unit)

    def write(self, path, values, nodata=None):
        a = np.asarray(values, dtype="float32")
        with rasterio.open(path, "w", driver="GTiff", height=a.shape[0], width=a.shape[1], count=1,
                           dtype="float32", crs="EPSG:4326", transform=from_origin(0, 2, 1, 1), nodata=nodata) as ds:
            ds.write(a, 1)

    def test_small_aoi_between_pixel_centres_and_valid_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "coarse.tif"
            self.write(path, [[0, 99], [99, 99]], nodata=-9)
            aoi = gpd.GeoDataFrame(geometry=[box(.05, 1.8, .15, 1.9)], crs=4326)
            with patch("stage02_gaez_verification.GAEZ_ALL_TOUCHED", False):
                old = verify_gaez_asset(self.asset(path), aoi, root / "old")
            self.assertEqual(old["verification_status"], "FAILED_NO_VALID_AOI_PIXELS")
            new = verify_gaez_asset(self.asset(path), aoi, root / "new")
            self.assertEqual(new["verification_status"], "VERIFIED_INSIDE_AOI")
            self.assertEqual(new["valid_pixel_count"], 1)
            self.assertEqual(new["min"], 0)
            with rasterio.open(root / "new" / new["local_clip"]) as clip:
                self.assertEqual(clip.read(1, masked=True).compressed().tolist(), [0])

    def test_mask_excludes_outside_polygon_and_nodata(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "coarse.tif"
            self.write(path, [[4, -9, -9], [4, -9, -9], [4, 4, 4]], nodata=-9)
            # A thin L selects five cells; its rectangular bounding window has nine.
            polygon = Polygon([(.1, 1.9), (.2, 1.9), (.2, -.8), (2.9, -.8), (2.9, -.9), (.1, -.9)])
            aoi = gpd.GeoDataFrame(geometry=[polygon], crs=4326)
            r = verify_gaez_asset(self.asset(path), aoi, root)
            self.assertEqual(r["valid_pixel_count"], 5)
            self.assertEqual(r["intersecting_pixel_count"], 5)
            self.assertEqual(r["valid_selected_pixel_percent"], 100)
            with rasterio.open(root / r["local_clip"]) as clip:
                self.assertEqual(clip.read(1, masked=True).count(), 5)

    def test_nodata_invalid_class_and_no_overlap_do_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "coarse.tif"
            aoi = gpd.GeoDataFrame(geometry=[box(.1, 1.8, .2, 1.9)], crs=4326)
            for value, code, nd, unit, status in [(-9, "RES05-YXX", -9, "kg", "FAILED_NO_VALID_AOI_PIXELS"),
                (1.5, "RES05-SIX", 0, "class", "FAILED_VALUE_RULE"), (101, "LR-IRR", None, "%", "FAILED_VALUE_RULE")]:
                self.write(path, [[value]])
                result = verify_gaez_asset(self.asset(path, code, nd, unit), aoi, root)
                self.assertEqual(result["verification_status"], status)
            far = gpd.GeoDataFrame(geometry=[box(10, 10, 11, 11)], crs=4326)
            self.assertEqual(verify_gaez_asset(self.asset(path), far, root)["verification_status"], "FAILED_NO_AOI_OVERLAP")

    def test_manifest_preserves_16_selected_assets_and_dimensions(self):
        manifest = yaml.safe_load((ROOT / "config/sources/gaez_v5_source_manifest.yml").read_text())
        assets = list(_asset_records(manifest))
        self.assertEqual(len(assets), 16)
        self.assertEqual({a["asset_key"] for a in assets}, EXPECTED_ASSET_KEYS)
        maize = [a for a in assets if a["map_code"] == "RES05-YXX"]
        self.assertEqual({a["input_code"] for a in maize}, {"HRLM", "LRLM", "HILM", "LILM"})
        self.assertTrue(all(a["period_code"] == "HP0120" for a in maize))

    def test_no_full_download_fallback(self):
        class Response:
            status_code = 200
            headers = {"Content-Length": "900000000"}
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def raise_for_status(self): pass
        with patch("stage02_gaez_verification.requests.get", return_value=Response()), patch("stage02_gaez_verification.rasterio.open") as opening:
            r = verify_gaez_asset(self.asset("https://example.org/global.tif"), None)
        self.assertEqual(r["verification_status"], "FAILED_ACCESS")
        opening.assert_not_called()


class TestDecisions(unittest.TestCase):
    def setUp(self):
        self.registry = load_dataset_registry(ROOT / "config/datasets.yml")
        self.raw = fake_records(self.registry)
        self.fao = pd.DataFrame([dict(dataset_id=k, Stage_02B_status="METADATA_ONLY", pixel_sample_confirmed=False,
            recommended_action="RUN_AOI_DATA_SAMPLE", verification_evidence="Catalogue open", evidence_json={}, failure_reason="NONE") for k in PRIORITY_IDS])

    def test_gaez_complete_requires_all_unique_assets(self):
        self.assertTrue(gaez_complete(gaez_rows()))
        self.assertFalse(gaez_complete(gaez_rows(6)))
        self.assertFalse(gaez_complete(gaez_rows().iloc[:6]))
        duplicated = pd.concat([gaez_rows().iloc[:15], gaez_rows().iloc[:1]], ignore_index=True)
        self.assertFalse(gaez_complete(duplicated))
        for frame in (gaez_rows(6), gaez_rows().iloc[:6], duplicated):
            # Even a misleading priority row cannot bypass the raster-report gate.
            self.fao.loc[self.fao.dataset_id.eq("FAO_GAEZ_V5_CURRENT"), ["Stage_02B_status", "pixel_sample_confirmed", "recommended_action"]] = ["VERIFIED_INSIDE_AOI", True, "USE_NEXT"]
            final = consolidate(self.raw, self.fao, frame, self.registry)
            row = final[final.dataset_id.eq("FAO_GAEZ_V5_CURRENT")].iloc[0]
            self.assertEqual(row.FINAL_ACTION, "REVIEW_GAEZ_VERIFICATION_REPORT")
            self.assertEqual(row.FINAL_STATUS, "METADATA_ONLY")

    def test_metadata_never_becomes_verified_and_local_input_not_forced_missing(self):
        f = strict_inventory(self.raw, self.registry)
        self.assertFalse(f.FINAL_STATUS.eq("VERIFIED_INSIDE_AOI").any())
        local = self.raw.dataset_id.eq("LC_LOCAL_PROJECT")
        self.raw.loc[local, ["sample_verified", "valid_data_status", "processing_priority"]] = [True, "VALID_DATA", "USE_NEXT"]
        f = consolidate(self.raw, self.fao, gaez_rows(), self.registry)
        self.assertEqual(f.loc[local, "FINAL_STATUS"].iloc[0], "VERIFIED_INSIDE_AOI")
        self.assertEqual(len(f), 48)
        with self.assertRaises(ValueError):
            consolidate(self.raw.iloc[:-1], self.fao, gaez_rows(), self.registry)
        with self.assertRaises(ValueError):
            consolidate(self.raw, self.fao.iloc[:-1], gaez_rows(), self.registry)

    def test_wapor_empty_pixel_values_do_not_pass(self):
        import sys
        fake = MagicMock()
        fake.ImageCollection.return_value.filterBounds.return_value.size.return_value.getInfo.return_value = 1
        image = fake.Image.return_value
        image.select.return_value.projection.return_value.nominalScale.return_value.getInfo.return_value = 100
        image.reduceRegion.return_value.getInfo.return_value = {"AETI": None}
        image.id.return_value.getInfo.return_value = "test-image"
        aoi = MagicMock()
        aoi.geometry.__geo_interface__ = box(0, 0, 1, 1).__geo_interface__
        with patch.dict(sys.modules, {"ee": fake}):
            ok, attempts = _wapor_sample(aoi)
        self.assertFalse(ok)
        self.assertEqual(len(attempts), 3)

    def test_full_orchestration_exports_all_results_in_one_zip(self):
        def fake_run(runner):
            runner.inventory = Inventory(self.raw.to_dict("records"))
        def verify(asset, aoi, output_dir):
            asset = dict(asset, url=str(raster))
            return verify_gaez_asset(asset, aoi, output_dir)
        with tempfile.TemporaryDirectory() as d:
            raster = Path(d) / "sample.tif"
            with rasterio.open(raster, "w", driver="GTiff", height=20, width=40, count=1, dtype="uint8",
                               crs="EPSG:4326", transform=from_origin(0, 20, 1, 1)) as ds:
                ds.write(np.full((20, 40), 3, dtype="uint8"), 1)
            with patch("parcel_a_geo.discovery.DiscoveryRunner.run_all", fake_run), \
                 patch("stage02_gaez_verification.verify_gaez_asset", side_effect=verify), \
                 patch("parcel_a_geo.fao_priority._wapor_sample", return_value=(False, [])), \
                 patch("parcel_a_geo.sources.base.NetworkClient.request", side_effect=RuntimeError("Offline fixture")):
                result = run_stage02(ROOT, Path(d) / "outputs")
            self.assertEqual(result["summary"]["registered_datasets"], 48)
            self.assertEqual(result["summary"]["gaez_assets_verified"], 16)
            with ZipFile(result["archive"]) as z:
                paths = set(z.namelist())
                for name in ["stage02a/tables/data_inventory_strict.csv", "stage02b/tables/fao_priority_inventory.csv",
                             "stage02b/gaez/gaez_verification_report.json", "stage02b/gaez/gaez_v5_source_manifest_verified.yml",
                             "final/tables/final_data_inventory.xlsx", "final/metadata/final_summary.json", "final/final_stage02_report.html"]:
                    self.assertIn(name, paths)
                self.assertEqual(len([p for p in paths if p.endswith('.tif')]), 16)
                self.assertFalse(any('/cache/' in p for p in paths))
                final = json.loads(z.read("final/metadata/final_data_inventory.json"))
                self.assertEqual(len({r['dataset_id'] for r in final}), 48)
                self.assertTrue(all(r['FINAL_STATUS'] for r in final))
