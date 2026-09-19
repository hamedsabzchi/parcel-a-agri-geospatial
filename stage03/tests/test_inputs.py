import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
import yaml
from fixtures import ROOT,fixture,rehash
from parcel_a_stage03.inputs import validate,unpack,unique
from parcel_a_stage03.inventory import configuration,resolve


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root,self.zip=fixture(Path(self.temp.name))

    def test_complete_input_and_plan(self):
        inputs=validate(self.root,ROOT);layers,sources=resolve(inputs,configuration(ROOT))
        self.assertEqual(len(sources),48)
        self.assertEqual(sum(l["extraction_status"]=="PENDING" for l in layers),16)
        self.assertEqual(len(inputs["gaez"]),16)
        self.assertEqual(next(s for s in sources if s["dataset_id"]=="FAO_GAEZ_V5_FUTURE")["stage03_disposition"],"DEFERRED")

    def test_long_csv_evidence_is_preserved_and_checked(self):
        root,archive=fixture(Path(self.temp.name)/"long-evidence",large_evidence=True)
        root=unpack(archive,Path(self.temp.name)/"unpacked-long-evidence")
        inventory_path=root/"final/metadata/final_data_inventory.json"
        expected=json.loads(inventory_path.read_text())
        self.assertGreater(len(expected[0]["FINAL_EVIDENCE"]),131072)
        previous=csv.field_size_limit(131072)
        try:
            inputs=validate(root,ROOT)
            self.assertEqual(inputs["sources"],expected)
            self.assertEqual(csv.field_size_limit(),131072)
            report=json.loads((root/"stage02b/gaez/gaez_verification_report.json").read_text())
            self.assertEqual(inputs["gaez"][0]["verification_details"],report[0]["verification_details"])
            # A mismatch after the original field limit must still be rejected.
            expected[0]["FINAL_EVIDENCE"]+="changed tail"
            inventory_path.write_text(json.dumps(expected));rehash(root)
            with self.assertRaisesRegex(ValueError,"CSV/JSON disagreement"):
                validate(root,ROOT)
            self.assertEqual(csv.field_size_limit(),131072)
        finally:csv.field_size_limit(previous)

    def test_archive_paths_and_missing_hash(self):
        with ZipFile(Path(self.temp.name)/"bad.zip","w") as z:z.writestr("../escape.txt","bad")
        with self.assertRaisesRegex(ValueError,"Unsafe"):unpack(Path(self.temp.name)/"bad.zip",Path(self.temp.name)/"extracted")
        p=self.root/"final/metadata/package_checksums.json";j=json.loads(p.read_text());del j["final/tables/final_data_inventory.csv"];p.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError,"checksum-covered"):validate(self.root,ROOT)

    def test_corrupt_member(self):
        (self.root/"stage02a/logs/discovery_log.txt").write_text("corrupt")
        with self.assertRaisesRegex(ValueError,"checksum mismatch"):validate(self.root,ROOT)

    def test_wrong_aoi(self):
        p=self.root/"final/metadata/final_summary.json";p.write_text(json.dumps({"aoi_sha256":"wrong"}));rehash(self.root)
        with self.assertRaisesRegex(ValueError,"AOI checksum"):validate(self.root,ROOT)

    def test_wrong_duplicate_source_ids(self):
        p=self.root/"final/metadata/final_data_inventory.json";j=json.loads(p.read_text());j[1]=j[0];p.write_text(json.dumps(j));rehash(self.root)
        with self.assertRaisesRegex(ValueError,"exact unique dataset_id"):validate(self.root,ROOT)

    def test_missing_required_gaez_asset(self):
        p=self.root/"stage02b/gaez/gaez_verification_report.json";j=json.loads(p.read_text());j.pop();p.write_text(json.dumps(j));rehash(self.root)
        with self.assertRaisesRegex(ValueError,"exact unique asset_key"):validate(self.root,ROOT)

    def test_final_decision_overrides_stale_sample(self):
        inputs=validate(self.root,ROOT)
        row=next(r for r in inputs["sources"] if r["dataset_id"]=="LC_ESA_WORLDCOVER_2021")
        row.update(sample_verified=True,processing_priority="USE_NEXT",FINAL_STATUS="METADATA_ONLY")
        layers,_=resolve(inputs,configuration(ROOT));l=next(l for l in layers if l["layer_id"]=="worldcover_2021")
        self.assertEqual(l["extraction_status"],"NOT_REQUESTED")

    def test_optional_requires_explicit_enable_later(self):
        inputs=validate(self.root,ROOT);row=next(r for r in inputs["sources"] if r["dataset_id"]=="LC_ESA_WORLDCOVER_2021")
        row.update(FINAL_STATUS="VERIFIED_INSIDE_AOI",FINAL_ACTION="USE_LATER")
        cfg=configuration(ROOT);layers,_=resolve(inputs,cfg)
        self.assertEqual(next(l for l in layers if l["layer_id"]=="worldcover_2021")["extraction_status"],"NOT_REQUESTED")
        next(l for l in cfg["layer_catalog"]["layers"] if l["layer_id"]=="worldcover_2021")["enable_later"]=True
        layers,_=resolve(inputs,cfg);self.assertEqual(next(l for l in layers if l["layer_id"]=="worldcover_2021")["extraction_status"],"PENDING")

    def test_wapor_product_evidence_is_not_interchangeable(self):
        inputs=validate(self.root,ROOT);row=next(r for r in inputs["sources"] if r["dataset_id"]=="FAO_WAPOR_V3_L2")
        row.update(FINAL_STATUS="VERIFIED_INSIDE_AOI",FINAL_ACTION="USE_NEXT",Stage_02B_evidence_json=json.dumps([{"collection":"projects/UNFAO/wapor/v3/L2-NPP-D","sample":{"L2-NPP-D":25}}]))
        layers,_=resolve(inputs,configuration(ROOT));self.assertEqual(next(l for l in layers if l["layer_id"]=="wapor_l2_aeti")["extraction_status"],"NOT_REQUESTED")

    def test_wapor_uses_actual_single_band_from_verified_product(self):
        inputs=validate(self.root,ROOT);row=next(r for r in inputs["sources"] if r["dataset_id"]=="FAO_WAPOR_V3_L2")
        row.update(FINAL_STATUS="VERIFIED_INSIDE_AOI",FINAL_ACTION="USE_NEXT",Stage_02B_evidence_json=json.dumps([{"collection":"projects/UNFAO/wapor/v3/L2-AETI-D","sample":{"b1":25}}]))
        layers,_=resolve(inputs,configuration(ROOT));layer=next(l for l in layers if l["layer_id"]=="wapor_l2_aeti")
        self.assertEqual(layer['extraction_status'],'PENDING');self.assertEqual(layer['variable'],'b1')
        self.assertEqual(layer['product_variable'],'L2-AETI-D')
