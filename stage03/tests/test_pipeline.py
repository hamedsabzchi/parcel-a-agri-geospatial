import base64
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from fixtures import ROOT,fixture
from parcel_a_stage03.common import sha256,write_json
from parcel_a_stage03.pipeline import run,prepare


class PreservationTests(unittest.TestCase):
    def test_stage01_stage02_preserved(self):
        baseline=json.loads((Path(__file__).parent/'stage01_stage02_baseline.json').read_text())
        for name,digest in baseline.items():
            data=(ROOT/name).read_bytes()
            self.assertEqual(hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest(),digest,name)

    def test_notebook_one_cell_explicit_bundle_and_no_outputs(self):
        spec=importlib.util.spec_from_file_location('build_stage03',ROOT/'tools/build_stage03.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        notebook=mod.build_notebook()
        self.assertEqual(json.loads((ROOT/'notebooks/03_data_inventory_visualization.ipynb').read_text()),notebook)
        cells=[c for c in notebook['cells'] if c['cell_type']=='code'];self.assertEqual(len(cells),1);self.assertEqual(cells[0]['outputs'],[])
        files=json.loads(mod.bundle_payload())
        self.assertIn('data/aoi/parcel_a.geojson',files)
        self.assertFalse(any(p.startswith(('src/','tests/','outputs/')) for p in files))
        self.assertIn('pip==',base64.b64decode(files['stage03/requirements-lock.txt']).decode())
        compile(''.join(cells[0]['source']),'stage03_notebook','exec')


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='stage03-synthetic-')
        cls.source,cls.archive=fixture(cls.temp.name)
        cls.result=run(ROOT,cls.archive,Path(cls.temp.name)/'outputs',Path(cls.temp.name)/'cache',progress=lambda _:None)
        cls.payload=Path(cls.result['dashboard']).parent.parent

    @classmethod
    def tearDownClass(cls):
        destination=os.getenv('STAGE03_TEST_ARTIFACTS')
        if destination:
            import shutil
            output=Path(destination);output.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(cls.result['archive'],output/'SYNTHETIC_TEST_ONLY_stage03.zip')
            write_json(output/'test_run_summary.json',dict(synthetic_test_only=True,summary=cls.result['summary']))
        cls.temp.cleanup()

    def test_complete_core_and_counts(self):
        self.assertEqual(self.result['outcome'],'COMPLETE')
        s=self.result['summary'];self.assertEqual(s['source_count'],48);self.assertEqual(s['gaez_extracted'],16)
        self.assertEqual(s['raster_count'],16);self.assertEqual(s['extracted_source_count'],1)
        qa=json.loads((self.payload/'qa/stage03_validation_report.json').read_text());self.assertTrue(all(qa['checks'].values()),qa)

    def test_zip_checksums_no_stale_members(self):
        with ZipFile(self.result['archive']) as z:
            names=z.namelist();self.assertIn('dashboard/parcel_a_data_inventory.html',names)
            self.assertFalse(any(n.endswith('.zip') or '/cache/' in n or 'credentials' in n for n in names))
            checks=json.loads(z.read('metadata/package_checksums.json'))
            self.assertEqual(set(names)-set(checks),{'metadata/package_checksums.json'})
            for name,digest in checks.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest,name)

    def test_legends_licences_and_shared_yield(self):
        legends=json.loads((self.payload/'metadata/legends.json').read_text())
        self.assertEqual(len(legends['GAEZ_V5_AEZ57']['entries']),57)
        self.assertEqual(len(legends['GAEZ_V5_SQX__HIM']['entries']),13)
        domains=[l['domain'] for k,l in legends.items() if k.startswith('GAEZ_V5_RES05_YXX')]
        self.assertTrue(all(d==domains[0] for d in domains))
        catalog=json.loads((self.payload/'metadata/layer_catalog.json').read_text())
        self.assertTrue(all(l['licence']=='CC-BY-4.0' for l in catalog if l['adapter']=='stage02_clip'))

    def test_offline_manifest_paths_and_embedded_data(self):
        manifest=json.loads((self.payload/'metadata/dashboard_manifest.json').read_text())
        for m in manifest['maps']:
            for key in ['visualization_path','download_path','static_map_path']:
                self.assertTrue((self.payload/'dashboard'/m[key]).is_file(),m[key])
        text=Path(self.result['dashboard']).read_text()
        self.assertIn('data:image/png;base64,',text)
        self.assertNotIn('<script src=',text)
        self.assertNotIn('fetch(', (ROOT/'stage03/src/parcel_a_stage03/assets/dashboard.js').read_text())

    def test_offline_browser_when_enabled(self):
        if not os.getenv('STAGE03_BROWSER_TESTS'):self.skipTest('Enabled in isolated Stage 03 CI with Chromium')
        from playwright.sync_api import sync_playwright
        errors=[]
        with sync_playwright() as p:
            kwargs={'args':['--no-sandbox']}
            if os.getenv('CHROMIUM_EXECUTABLE'):kwargs['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=p.chromium.launch(**kwargs)
            context=browser.new_context(offline=True,accept_downloads=True,viewport={'width':1440,'height':1000})
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(Path(self.result['dashboard']).as_uri());page.wait_for_function('window.stage03Ready===true')
            self.assertEqual(page.locator('#cards .card').count(),4)
            page.locator('[data-tab="maps"]').click();page.wait_for_selector('#main-map .leaflet-image-layer')
            self.assertGreater(page.locator('#active-legend .legend-row').count(),1)
            page.locator('#active-layer').select_option('GAEZ_V5_RES05_YXX__HRLM')
            page.locator('#opacity').evaluate("n=>{n.value='0.3';n.dispatchEvent(new Event('input',{bubbles:true}));}");self.assertIn('0.3',page.locator('#main-map .leaflet-image-layer').last.get_attribute('style'))
            page.locator('#comparison-group').select_option('RES05-YXX')
            page.locator('#compare-right').select_option('GAEZ_V5_RES05_YXX__LILM')
            self.assertIn('distinct cells',page.locator('#right-support').inner_text())
            page.locator('#reset-map').click()
            self.assertTrue(page.evaluate('mainMap.getBounds().contains(L.latLngBounds(D.bounds))'))
            image_bounds=page.evaluate('(()=>{const m=mapById["GAEZ_V5_AEZ57"]; return m.bounds;})()')
            self.assertLess(image_bounds[0][0],image_bounds[1][0])
            page.locator('[data-tab="tables"]').click();page.locator('#search').fill('GAEZ')
            self.assertIn('2 records',page.locator('#page-info').inner_text())
            with page.expect_download() as event:page.locator('#export-csv').click()
            download=event.value;self.assertTrue(download.suggested_filename.endswith('.csv'))
            page.locator('#search').fill('');page.locator('#next').click();self.assertIn('page 2',page.locator('#page-info').inner_text())
            page.locator('[data-tab="graphs"]').click();self.assertEqual(page.locator('#chart-space svg').count(),1)
            page.locator('#chart-select').select_option('maize_yield_comparison');self.assertGreater(page.locator('#chart-space circle').count(),0)
            page.set_viewport_size({'width':768,'height':1024});page.locator('[data-tab="maps"]').click()
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),770)
            if os.getenv('STAGE03_TEST_ARTIFACTS'):
                destination=Path(os.environ['STAGE03_TEST_ARTIFACTS']);destination.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(destination/'SYNTHETIC_TEST_ONLY_dashboard.png'),full_page=True)
            self.assertEqual(errors,[])
            browser.close()


class FailureTests(unittest.TestCase):
    def test_required_missing_legend_and_optional_failure(self):
        # Exercise real packaging outcomes; keep rendering cheap for this separate failure test.
        with tempfile.TemporaryDirectory() as temp:
            source,archive=fixture(temp,optional=True)
            prepared=prepare(ROOT,source,Path(temp)/'work')
            prepared[0]['symbology']['legends'].pop('AEZ57')
            with patch('parcel_a_stage03.sources.connect',side_effect=RuntimeError('No test credentials')):
                result=run(ROOT,source,Path(temp)/'out',Path(temp)/'cache',progress=lambda _:None,prepared=prepared)
            self.assertEqual(result['outcome'],'INCOMPLETE');self.assertTrue(result['archive'].endswith('stage03_diagnostics.zip'))
            self.assertEqual(len(result['summary']['gaps']),2)

    def test_optional_failure_retains_core(self):
        with tempfile.TemporaryDirectory() as temp:
            source,archive=fixture(temp,optional=True)
            with patch('parcel_a_stage03.sources.connect',side_effect=RuntimeError('No test credentials')):
                result=run(ROOT,archive,Path(temp)/'out',Path(temp)/'cache',progress=lambda _:None)
            self.assertEqual(result['outcome'],'COMPLETE_WITH_OPTIONAL_GAPS')
            self.assertEqual(result['summary']['gaez_extracted'],16)
