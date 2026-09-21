"""Synthetic integration evidence; no actual project result is claimed."""
import ast
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile,ZIP_DEFLATED
import zlib
from parcel_a_stage04.common import sha,csv_read,csv_write
from parcel_a_stage04.contract import resolve,FILES
from parcel_a_stage04.pipeline import unpack,run,ENTRY,additions
from parcel_a_stage04.browser_qa import inspect

ROOT=Path(__file__).resolve().parents[2]


class RepositoryTests(unittest.TestCase):
    def test_all_139_original_files_unchanged(self):
        accepted=json.loads((ROOT/'stage04/tests/accepted_repository.json').read_text())
        self.assertEqual(len(accepted),139)
        for name,expected in accepted.items():
            with self.subTest(path=name):
                raw=(ROOT/name).read_bytes();actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                self.assertEqual(actual,expected)

    def test_one_cell_self_contained_bundle(self):
        subprocess.run([sys.executable,str(ROOT/'tools/build_stage04.py'),'--check'],check=True)
        n=json.loads((ROOT/'notebooks/04_future_scenario_summary.ipynb').read_text())
        code=[c for c in n['cells'] if c['cell_type']=='code'];self.assertEqual(len(code),1)
        source=''.join(code[0]['source']);parsed=ast.parse(source)
        literal=next(x.value for x in parsed.body if isinstance(x,ast.Assign) and x.targets[0].id=='STAGE04_BUNDLE')
        raw=zlib.decompress(base64.b64decode(ast.literal_eval(literal)));bundle=json.loads(raw)
        self.assertTrue(all(k.startswith('stage04/') for k in bundle))
        for path,value in bundle.items():self.assertEqual(base64.b64decode(value),(ROOT/path).read_bytes())
        self.assertNotIn('ee.Authenticate',source);self.assertNotIn('GITHUB_TOKEN',source)

    def test_worker_error_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            result=Path(temp)/'result.json'
            p=subprocess.run([sys.executable,'-m','parcel_a_stage04','--input',str(Path(temp)/'missing.zip'),'--output-base',temp,'--result-path',str(result)],capture_output=True)
            self.assertEqual(p.returncode,1);self.assertIn('Stage 03 ZIP',json.loads(result.read_text())['error'])


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='stage04-synthetic-');cls.base=Path(cls.temp.name)
        folder=Path(os.getenv('STAGE03_TEST_ARTIFACTS','stage04-test-results/input'))
        cls.source=folder/'SYNTHETIC_TEST_ONLY_stage03_maize.zip'
        if not cls.source.is_file():raise RuntimeError('First run unchanged Stage 03 tests with STAGE03_TEST_ARTIFACTS set; this creates the explicitly synthetic input.')
        cls.payload=cls.base/'original';cls.baseline=unpack(cls.source,cls.payload)
        cls.data=resolve(cls.payload)
        if os.getenv('STAGE04_BROWSER_TESTS')=='1':checker=inspect
        else:
            # Local numerical/packaging test only. CI always supplies the real browser.
            checker=lambda *args:dict(status='PASS',checks={'synthetic_browser_stub_only':True},synthetic_browser_stub_only=True)
        cls.output=run(cls.source,cls.base/'runs',testing=True,browser_check=checker)
        cls.extended=Path(cls.output['dashboard']).parent.parent

    @classmethod
    def tearDownClass(cls):
        target=os.getenv('STAGE04_TEST_ARTIFACTS')
        if target:
            folder=Path(target);folder.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(cls.output['archive'],folder/'SYNTHETIC_TEST_ONLY_stage04.zip')
            shutil.copyfile(cls.output['receipt'],folder/'SYNTHETIC_TEST_ONLY_stage04_receipt.json')
            shutil.copyfile(cls.extended/'qa/stage04_qa_report.json',folder/'SYNTHETIC_TEST_ONLY_stage04_qa.json')
        cls.temp.cleanup()

    @contextmanager
    def edit_json(self,name,change):
        p=self.payload/name;before=p.read_bytes();value=json.loads(before);change(value)
        p.write_text(json.dumps(value))
        try:yield
        finally:p.write_bytes(before)

    def test_all_24_verified_combinations_and_48_products(self):
        self.assertEqual(len(self.data['scenarios']),24,self.data['conflicts'])
        self.assertEqual(sum(len(r['products']) for r in self.data['scenarios']),48)
        self.assertFalse(self.data['conflicts']);self.assertFalse(self.data['gaps'])
        for r in self.data['scenarios']:
            for p in r['products'].values():self.assertEqual(p['summary']['model_count'],5)

    def test_original_paths_bytes_and_html_content_preserved(self):
        for row in self.baseline:
            p=self.extended/row['path'];self.assertTrue(p.is_file())
            if row['path']!=ENTRY:self.assertEqual(sha(p),row['sha256'],row['path'])
        old=(self.payload/ENTRY).read_bytes().decode();new=(self.extended/ENTRY).read_bytes().decode()
        data=json.loads((self.extended/'dashboard/assets/stage04_future_scenarios_data.json').read_text())
        rebuilt,evidence=additions(old,data);self.assertEqual(rebuilt,new)
        self.assertTrue(evidence['original_html_preserved_as_subsequence'])
        self.assertEqual(new.count('id="stage04-tab"'),1)

    def test_final_package_manifest_receipt_and_status(self):
        self.assertEqual(self.output['status'],'COMPLETE')
        with ZipFile(self.output['archive']) as z:
            self.assertIsNone(z.testzip());checks=json.loads(z.read('metadata/stage04_package_checksums.json'))
            self.assertEqual(set(z.namelist())-set(checks),{'metadata/stage04_package_checksums.json'})
            for name,digest in checks.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest,name)
            self.assertEqual(len(z.namelist()),self.output['summary']['final_file_count'])
        self.assertEqual(sha(self.output['archive']),self.output['summary']['output_zip_sha256'])
        self.assertEqual(Path(self.output['archive']).stat().st_size,self.output['summary']['output_zip_size'])
        self.assertTrue(self.output['summary']['synthetic_test_only'])

    def test_large_csv_fields_and_full_precision(self):
        p=self.base/'large.csv';csv_write(p,[dict(text='x'*140000,value=1/3)])
        r=csv_read(p)[0];self.assertEqual(len(r['text']),140000);self.assertEqual(float(r['value']),1/3)
        rows=csv_read(self.extended/'tables/stage04_future_scenario_summary.csv')
        self.assertEqual(len(rows),24)
        self.assertAlmostEqual(float(rows[0]['yield_whole_aoi_mean']),self.data['scenarios'][0]['products']['yield']['summary']['whole_aoi_mean'])

    def test_unsafe_zip_and_previous_stage04_rejected(self):
        attack=self.base/'attack.zip'
        for member in ['../escape','/absolute','a\\escape','stage04_previous/foo']:
            with self.subTest(member=member):
                with ZipFile(attack,'w') as z:z.writestr(member,'x')
                with self.assertRaises(ValueError):unpack(attack,self.base/('unsafe-'+hashlib.sha256(member.encode()).hexdigest()[:8]))
        with self.assertRaises(ValueError):unpack(self.output['archive'],self.base/'rerun-rejected')
        with self.assertRaises(ValueError):unpack(self.payload,self.base/'folder-rejected')

    def test_synthetic_fixture_rejected_by_normal_run(self):
        with self.assertRaisesRegex(ValueError,'Synthetic test packages'):run(self.source,self.base/'normal-runs')

    def test_checksum_tampering_rejected(self):
        tampered=self.base/'tampered.zip'
        with ZipFile(self.source) as source,ZipFile(tampered,'w',ZIP_DEFLATED) as target:
            for name in source.namelist():target.writestr(name,source.read(name)+(b' ' if name=='metadata/layer_catalog.json' else b''))
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):unpack(tampered,self.base/'tampered')

    def test_conflicting_model_values_disable_only_affected_product(self):
        path=self.payload/FILES['units'];before=path.read_bytes();rows=csv_read(path)
        values=json.loads(rows[0]['model_values']);model=next(iter(values));values[model]+=1;rows[0]['model_values']=values;csv_write(path,rows)
        try:r=resolve(self.payload)
        finally:path.write_bytes(before)
        self.assertEqual(sum(len(x['products']) for x in r['scenarios']),47)
        self.assertTrue(r['conflicts']);self.assertTrue(r['gaps'])

    def test_duplicate_support_key_does_not_discard_other_products(self):
        path=self.payload/FILES['support'];before=path.read_bytes();rows=csv_read(path);rows.append(rows[0]);csv_write(path,rows)
        try:r=resolve(self.payload)
        finally:path.write_bytes(before)
        self.assertEqual(sum(len(x['products']) for x in r['scenarios']),47)
        self.assertTrue(any('Duplicate' in c['reason'] for c in r['conflicts']))

    def test_source_defined_positive_rule_is_not_silently_overridden(self):
        def change(groups):
            next(g for g in groups if g['map_code']=='RES05-YXX')['positive_yield_rule']='all models > 0'
        with self.edit_json(FILES['groups'],change):r=resolve(self.payload)
        self.assertEqual(sum(len(x['products']) for x in r['scenarios']),47)
        self.assertTrue(any('positive-yield criterion' in c['reason'] for c in r['conflicts']))

    @unittest.skipUnless(os.getenv('STAGE04_BROWSER_TESTS')=='1','Real offline browser runs in CI; local packaging uses an explicitly labelled test stub')
    def test_actual_browser_reports(self):
        qa=json.loads((self.extended/'qa/stage04_qa_report.json').read_text())
        self.assertEqual(qa['baseline_browser']['status'],'PASS',qa['baseline_browser'])
        self.assertEqual(qa['regression_browser']['status'],'PASS',qa['regression_browser'])
        self.assertNotIn('synthetic_browser_stub_only',qa['regression_browser'])
        self.assertTrue(qa['regression_browser']['checks']['offline_reload'])
