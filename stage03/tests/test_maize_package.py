"""All 254 supplemental assets through the real package orchestration, offline."""
import base64
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import shape
from parcel_a_stage03.common import write_json,sha256
from parcel_a_stage03.pipeline import run as core_run
from parcel_a_stage03.maize_extension import extend,embedded_dashboard
from parcel_a_stage03.maize_workflow import baseline,preflight,verify_package
from parcel_a_stage03.maize_sources import read_result
from parcel_a_stage03 import render,maize_render
from fixtures import ROOT,fixture


def synthetic_extract(asset,aoi,directory,config):
    directory=Path(directory);directory.mkdir(parents=True)
    resolution=asset['expected_resolution_degrees'];x=13.8333333333333;y=6.75
    w=round(1/6/resolution);h=round(.25/resolution)
    idx=['AGERA5','ENSEMBLE','GFDL-ESM4','IPSL-CM6A-LR','MPI-ESM1-2-HR','MRI-ESM2-0','UKESM1-0-LL'].index(asset['climate_model_code'])
    raw=(np.indices((h,w)).sum(axis=0)+idx)%7+1
    if asset['map_code']=='RES05-YXX':raw=raw*100+int(asset['ssp_code'][-1])*10
    if asset['map_code']=='RES05-SXX30AS':raw=raw*1000
    raw=raw.astype(asset['expected_dtype']);mask=np.full(raw.shape,255,dtype='uint8')
    if asset.get('conditional_cropland_mask'):mask[:]=0
    path=directory/'clip.tif'
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True),rasterio.open(path,'w',driver='GTiff',width=w,height=h,count=1,dtype=raw.dtype,crs=4326,transform=from_origin(x,y,resolution,resolution),nodata=asset['nodata']) as out:
        out.write(raw,1);out.write_mask(mask)
    result=read_result(path,aoi,asset,config['area_crs'])
    write_json(directory/'source.json',dict(synthetic_test_only=True,object=asset['object_name']))
    receipt=dict(layer_id=asset['layer_id'],map_code=asset['map_code'],period_code=asset['period_code'],ssp_code=asset['ssp_code'],
        management_code=asset['management_code'],climate_model_code=asset['climate_model_code'],synthetic_test_only=True,
        verification_status='VERIFIED_INSIDE_AOI' if result['valid'].any() else 'VERIFIED_BUT_EMPTY_INSIDE_AOI',clip_sha256=sha256(path),clip_reopened=True,area_closure_passed=True,**result['stats'])
    write_json(directory/'verification.json',receipt);return receipt


def placeholder_export(path,*args,**kwargs):
    # Repetitive figure I/O is substituted only in this synthetic orchestration test.
    # Actual overlays, legends, native exports, calculations, manifests and HTML run.
    Path(path).write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP9sAAAAASUVORK5CYII='))


class MaizePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='maize-synthetic-');cls.root=Path(cls.temp.name)
        source,archive=fixture(cls.root/'inputs')
        cls.core=core_run(ROOT,archive,cls.root/'core',cls.root/'cache',progress=lambda _:None)
        cls.base=Path(cls.core['dashboard']).parent.parent
        cls.original={p.relative_to(cls.base).as_posix():sha256(p) for p in cls.base.rglob('*') if p.is_file()}
        with patch.object(render,'static_map',placeholder_export),patch.object(render,'static_chart',placeholder_export):
            cls.built=extend(ROOT,cls.base,cls.root/'extended',cls.root/'cache',lambda _:None,synthetic_extract)
        cls.payload=Path(cls.built['dashboard']).parent.parent;cls.data=embedded_dashboard(cls.payload)

    @classmethod
    def tearDownClass(cls):
        destination=os.getenv('STAGE03_TEST_ARTIFACTS')
        if destination:
            path=Path(destination);path.mkdir(exist_ok=True,parents=True)
            shutil.copyfile(cls.built['archive'],path/'SYNTHETIC_TEST_ONLY_stage03_maize.zip')
            write_json(path/'maize_test_summary.json',dict(synthetic_test_only=True,summary=cls.built['summary']))
        cls.temp.cleanup()

    def test_full_scope_and_unchanged_core(self):
        summary=self.data['maize']['summary'];self.assertEqual(summary['planned_assets'],254);self.assertEqual(summary['verified_assets'],254)
        self.assertEqual(summary['complete_five_model_groups'],48);self.assertEqual(summary['groups_with_common_support'],48)
        self.assertEqual(summary['empty_or_outside_layers'],2);self.assertEqual(summary['failed_layers'],0)
        self.assertEqual(self.built['outcome'],'COMPLETE_WITH_COVERAGE_GAPS')
        for name,digest in self.original.items():self.assertEqual(sha256(self.base/name),digest);self.assertEqual(sha256(self.payload/'metadata/core_baseline'/name),digest)
        tables={t['id']:t for t in self.data['tables']};old=embedded_dashboard(self.base)
        for table in old['tables']:
            self.assertEqual(tables[table['id']]['rows'][:len(table['rows'])],table['rows'])
            self.assertEqual(tables[table['id']]['columns'][:len(table['columns'])],table['columns'])
        self.assertEqual(len(tables['source_inventory']['rows']),48)
        self.assertEqual(len(tables['maize_pairwise']['rows']),480)
        self.assertEqual(len(tables['maize_ensemble_diagnostics']['rows']),10)
        self.assertEqual(len(tables['maize_group_status']['rows']),48)
        self.assertEqual(len(tables['maize_source_comparisons']['rows']),850)
        self.assertEqual(len(tables['maize_derived_comparisons']['rows']),120)
        qa=json.loads((self.payload/'qa/maize_validation_report.json').read_text());self.assertTrue(all(qa['checks'].values()),qa)

    def test_all_downloads_and_full_package_checksums(self):
        verify_package(self.payload)
        with ZipFile(self.built['archive']) as z:
            names=set(z.namelist());checks=json.loads(z.read('metadata/package_checksums.json'))
            self.assertEqual(names-set(checks),{'metadata/package_checksums.json'})
        for m in self.data['maps']:
            self.assertTrue((self.payload/'dashboard'/m['download_path']).is_file())
            self.assertTrue((self.payload/'dashboard'/m['static_map_path']).is_file())
        for i in range(1,24):self.assertTrue((self.payload/f'metadata/maize/stage_03_{i}_verification.json').is_file())
        self.assertFalse(any(m['metadata'].get('map_code')=='RES05-SXX30AS' and m['metadata'].get('period_code','').startswith('FP') for m in self.data['maps']))

    def test_completed_stage03_reuse_and_tamper_rejection(self):
        core=baseline(self.payload,ROOT);self.assertEqual(core,self.payload/'metadata/core_baseline')
        with tempfile.TemporaryDirectory() as temp:
            p=preflight(ROOT,self.built['archive'],temp);self.assertFalse(p['needs_earth_engine']);self.assertTrue(p['reuse_existing_core'])
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'bad';shutil.copytree(self.base,target);(target/'maps/parcel_a.png').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):baseline(target,ROOT)

    def test_real_export_readback_and_shared_scales(self):
        derived=next(m for m in self.data['maps'] if m['metadata'].get('view')=='model_mean')
        with rasterio.open(self.payload/'dashboard'/derived['download_path']) as src:
            self.assertEqual(src.count,1);self.assertEqual(src.tags()['project_derived'],'true')
            self.assertEqual(src.res,(1/12,1/12));self.assertTrue(np.isfinite(src.read(1,masked=True).compressed()).all())
        source=next(m for m in self.data['maps'] if m['metadata'].get('map_code')=='RES05-YXX' and m['metadata'].get('management_code')==derived['metadata']['management_code'] and m['metadata'].get('view')=='source')
        self.assertEqual(derived['legend']['domain'],source['legend']['domain'])
        # Exercise the actual static renderer on a representative derived overlay.
        layer=derived['metadata'];aoi=shape(self.data['aoi']['features'][0]['geometry'])
        spec=dict(layer,scale=1,offset=0,nodata=-9999)
        result=read_result(self.payload/'dashboard'/derived['download_path'],aoi,spec,'EPSG:6933')
        preview=render.overlay(result,derived['legend'],aoi,100)
        with tempfile.TemporaryDirectory() as temp:
            png=Path(temp)/'map.png';render.static_map(png,layer,derived['legend'],preview,aoi);self.assertGreater(png.stat().st_size,10000)

    def test_offline_maize_browser_when_enabled(self):
        if not os.getenv('STAGE03_BROWSER_TESTS'):self.skipTest('Offline Chromium acceptance is enabled in CI')
        from playwright.sync_api import sync_playwright
        errors=[]
        with sync_playwright() as p:
            kwargs={'args':['--no-sandbox']}
            if os.getenv('CHROMIUM_EXECUTABLE'):kwargs['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=p.chromium.launch(**kwargs);context=browser.new_context(offline=True,accept_downloads=True,viewport={'width':1440,'height':1000})
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(Path(self.built['dashboard']).as_uri());page.wait_for_function('window.stage03Ready===true')
            self.assertTrue(page.locator('#maize-overview').is_visible());page.locator('#maize-start').click()
            for key,value in [('map_code','RES05-YXX'),('period_code','FP8100'),('ssp_code','SSP585'),('management_code','HRLM'),('climate_model_code','FIVE_MODELS'),('view','model_mean')]:page.locator('#maize-'+key).select_option(value)
            self.assertEqual(page.locator('#active-layer option').count(),1);self.assertIn('Project-derived',page.locator('#active-layer').inner_text())
            page.locator('#layer-downloads button').filter(has_text='Related table').click();self.assertIn('records',page.locator('#page-info').inner_text());self.assertNotIn('0 records',page.locator('#page-info').inner_text())
            page.locator('[data-tab="maps"]').click();page.get_by_role('button',name='Clear filters',exact=True).click()
            page.locator('#comparison-group').select_option('SIX_AND_SXX')
            left=next(m['layer_id'] for m in self.data['maps'] if m['comparison_group']=='RES05-SIX')
            right=next(m['layer_id'] for m in self.data['maps'] if m['comparison_group']=='RES05-SXX30AS')
            page.locator('#compare-left').select_option(left);page.locator('#compare-right').select_option(right)
            self.assertIn('different products',page.locator('#compare-legend').inner_text());self.assertIn('class',page.locator('#left-legend').inner_text());self.assertIn('Index',page.locator('#right-legend').inner_text())
            page.locator('[data-tab="graphs"]').click();self.assertGreater(page.locator('#chart-space svg').count(),0)
            if os.getenv('STAGE03_TEST_ARTIFACTS'):
                screenshot=Path(os.environ['STAGE03_TEST_ARTIFACTS'])/'maize-dashboard.png';screenshot.parent.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(screenshot),full_page=True)
            self.assertEqual(errors,[]);browser.close()
