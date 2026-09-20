"""Synthetic regression evidence for the additive 03.1–03.23 workflow."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box,shape
from parcel_a_stage03 import maize_analysis as a,maize_sources as s
from parcel_a_stage03.spatial import read_raster,area_weights
from parcel_a_stage03.common import write_json,sha256
from fixtures import ROOT


def result(values,aoi=None,transform=None,mask=None):
    values=np.asarray(values,dtype=float);transform=transform or from_origin(0,2,1,1);aoi=aoi or box(0,0,2,2)
    weights,area=area_weights(aoi,transform,'EPSG:4326',*values.shape)
    valid=np.isfinite(values)&(weights>0)
    if mask is not None:valid&=np.asarray(mask,dtype=bool)
    values=values.copy();values[~valid]=np.nan
    return dict(values=values,raw=np.nan_to_num(values,nan=-9),valid=valid,weights=weights,transform=transform,crs='EPSG:4326',
        stats=dict(aoi_area_ha=area/1e4,valid_area_ha=float(weights[valid].sum()/1e4),native_resolution=[abs(transform.a),abs(transform.e)]),
        profile=dict(driver='GTiff',height=values.shape[0],width=values.shape[1],count=1,dtype='float32',crs='EPSG:4326',transform=transform))


def item(model,index,values,product='RES05-SIX',period='FP2140',ssp='SSP126',management='HRLM',**kwargs):
    return (dict(layer_id=f'{product}_{period}_{ssp}_{management}_{model}_{index}',climate_model_code=model,map_code=product,period_code=period,ssp_code=ssp,
        management_code=management,data_type='categorical' if product=='RES05-SIX' else 'continuous',period='2021-2040'),result(values,**kwargs))


class ManifestTests(unittest.TestCase):
    def test_exact_inventory_and_resolved_gaps(self):
        cfg,m=s.configuration(ROOT);assets=m['assets']
        self.assertEqual(len(assets),254);self.assertEqual(len({x['tiff_url'] for x in assets}),254);self.assertEqual(len({x['json_url'] for x in assets}),254)
        self.assertEqual(m['guide_sha256'],sha256(ROOT/m['guide_path']))
        self.assertEqual(len(m['addenda']),23)
        for p,count in [('RES05-SXX30AS',4),('RES05-SIX',124),('RES05-YXX',126)]:self.assertEqual(sum(x['map_code']==p for x in assets),count)
        for product in ['RES05-SIX','RES05-YXX']:
            for period in ['FP2140','FP4160','FP6180','FP8100']:
                for ssp in ['SSP126','SSP370','SSP585']:
                    for management in ['HRLM','HILM']:
                        models=[x['climate_model_code'] for x in assets if (x['map_code'],x['period_code'],x['ssp_code'],x['management_code'])==(product,period,ssp,management) and x['climate_model_code']!='ENSEMBLE']
                        self.assertEqual(sorted(models),sorted(a.MODELS))
        for asset in assets:s.validate_identity(asset)
        self.assertFalse(any(x['map_code']=='RES05-SXX30AS' and x['period_code'].startswith('FP') for x in assets))
        self.assertFalse(any(x['map_code']=='RES05-SIX' and x['ssp_code']=='SSP585' and x['climate_model_code']=='ENSEMBLE' for x in assets))

    def test_original_core_files_preserved(self):
        hashes=json.loads((ROOT/'stage03/tests/stage03_baseline.json').read_text())
        allowed={'README.md','.github/workflows/stage03-quality.yml','stage03/src/parcel_a_stage03/__init__.py','stage03/src/parcel_a_stage03/__main__.py',
            'stage03/src/parcel_a_stage03/dashboard.py','stage03/src/parcel_a_stage03/assets/dashboard.html','stage03/src/parcel_a_stage03/assets/dashboard.js',
            'stage03/tests/test_startup.py','tools/build_stage03.py','tools/stage03_notebook_cell.py','notebooks/03_data_inventory_visualization.ipynb'}
        for name,digest in hashes.items():
            if name in allowed:continue
            data=(ROOT/name).read_bytes();self.assertEqual(hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest(),digest,name)

    def test_official_metadata_snapshots_and_sld(self):
        root=ROOT/'config/stage03/source_metadata';evidence=json.loads((root/'maize_metadata_evidence.json').read_text())
        for row in evidence:self.assertEqual(sha256(root/row['file']),row['sha256'])
        sxx=json.loads((root/'GAEZ-V5.RES05-SXX30AS.json').read_text());self.assertEqual((sxx['measureUnit'],sxx['noDataValue'],sxx['scale']),('Index',-9,1))
        parsed=next(r['parsed_colour_entries'] for r in evidence if r['file']=='GAEZ-V5.SXX.sld')
        self.assertEqual([float(e['quantity']) for e in parsed],[-9,0,1000,2500,5000,7500,10000])


class ScienceTests(unittest.TestCase):
    def test_categorical_ties_unique_plurality_and_ten_pairs(self):
        # Four cells: 2/2/1 tie, unique 2/1/1/1 plurality, 4/1, unanimity.
        vals=[[[1,1],[2,9]],[[1,1],[2,9]],[[2,2],[2,9]],[[2,3],[2,9]],[[3,4],[3,9]]]
        items=[item(model,i,v) for i,(model,v) in enumerate(zip(a.MODELS,vals))]
        r=a.five_models(items,box(0,0,2,2));rows=r['rows']
        self.assertIsNone(rows[0]['modal_class']);self.assertEqual(rows[0]['tied_modal_classes'],[1,2]);self.assertEqual(rows[0]['modal_count'],2)
        self.assertTrue(rows[1]['unique_mode']);self.assertEqual(rows[1]['agreement_group'],'Tied / dispersed');self.assertEqual(rows[1]['tie_flag'],0)
        self.assertEqual(rows[2]['strong_agreement'],1);self.assertEqual(rows[2]['full_agreement'],0)
        self.assertEqual(rows[3]['full_agreement'],1);self.assertIsNone(rows[3]['highest_suitability_label'])
        self.assertEqual(len(r['pairwise']),10);self.assertEqual(len(r['class_frequencies']),36)
        self.assertAlmostEqual(sum(r['summary']['agreement_areas_ha'].values()),r['support']['common_valid_area_ha'])
        self.assertFalse(any(k in rows[0] for k in ['mean','median','minimum','maximum','numeric_range']))

    def test_yield_zero_cv_and_exact_pop_sd(self):
        vals=[[[0,v],[v,2*v]] for v in [1,2,3,4,5]]
        r=a.five_models([item(m,i,v,product='RES05-YXX') for i,(m,v) in enumerate(zip(a.MODELS,vals))],box(0,0,2,2))
        self.assertEqual(r['rows'][0]['model_mean'],0);self.assertIsNone(r['rows'][0]['model_coefficient_of_variation'])
        row=r['rows'][1];self.assertEqual((row['model_mean'],row['model_median'],row['model_iqr'],row['model_range']),(3,3,2,4))
        self.assertAlmostEqual(row['model_standard_deviation'],np.sqrt(2));self.assertEqual(len(row['pairwise_differences']),10)
        self.assertEqual(len(r['summary']['across_five_aoi_model_means']),9)

    def test_missing_duplicate_and_mismatched_models_rejected(self):
        items=[item(m,i,[[1,2],[3,4]]) for i,m in enumerate(a.MODELS)]
        for bad in [items[:4],items[:4]+[items[0]]]:
            with self.assertRaises(ValueError):a.five_models(bad,box(0,0,2,2))
        bad=copy.deepcopy(items);bad[-1][0]['ssp_code']='SSP585'
        with self.assertRaises(ValueError):a.five_models(bad,box(0,0,2,2))

    def test_shifted_native_grids_geometric_common_mask(self):
        aoi=box(0,0,2,2)
        first=item('A',0,[[10,20],[30,40]],product='RES05-YXX',aoi=aoi)
        second=item('B',1,[[50,60],[70,80]],product='RES05-YXX',aoi=aoi,transform=from_origin(.5,2,1,1),mask=[[1,0],[1,1]])
        units,support=a.common_support([first,second],aoi)
        self.assertFalse(support['same_native_grid']);self.assertGreater(support['excluded_outside_footprint_area_ha'],0);self.assertGreater(support['excluded_masked_area_ha'],0)
        self.assertAlmostEqual(support['common_valid_area_ha']+support['excluded_area_ha'],support['aoi_area_ha'])
        self.assertEqual(len(units),5)
        self.assertTrue(all(v in {10,20,30,40,50,60,70,80} for u in units for v in u['values']))

    def test_comparison_zero_baseline_and_matching(self):
        first=item('AGERA5',0,[[0,10],[20,30]],product='RES05-YXX',period='HP0120',ssp='HIST')
        second=item('GFDL-ESM4',1,[[5,20],[30,60]],product='RES05-YXX')
        r=a.compare([first,second],box(0,0,2,2),'historical_future')
        self.assertIsNone(r['rows'][0]['percentage_difference']);self.assertEqual(r['rows'][0]['absolute_difference'],5)
        self.assertEqual(r['rows'][1]['percentage_difference'],100)
        self.assertLess(r['summary']['percentage_defined_area_ha'],r['support']['common_valid_area_ha'])
        with self.assertRaises(ValueError):a.compare([first,second],box(0,0,2,2),'cross_ssp')
        bad=copy.deepcopy(second);bad[0]['management_code']='HILM'
        with self.assertRaises(ValueError):a.compare([first,bad],box(0,0,2,2),'historical_future')

    def test_group_and_ensemble_diagnostics_exclude_tied_modes(self):
        aoi=box(0,0,2,2)
        left=a.five_models([item(m,i,[[v,1],[1,1]]) for i,(m,v) in enumerate(zip(a.MODELS,[1,1,2,2,3]))],aoi)
        right=a.five_models([item(m,i,[[2,2],[2,2]],ssp='SSP585') for i,m in enumerate(a.MODELS)],aoi)
        comp=a.matched_group_comparison(left,right,aoi,'cross_ssp')
        self.assertGreater(comp['summary']['tied_mode_excluded_area_ha'],0)
        ens=item('ENSEMBLE',9,[[1,1],[1,1]])
        diagnostic=a.ensemble_diagnostic(left,ens,aoi)
        self.assertEqual(diagnostic['summary']['matching_percentage'],100)
        self.assertGreater(diagnostic['summary']['tied_mode_excluded_area_ha'],0)


class VerificationTests(unittest.TestCase):
    def test_source_roundtrip_internal_mask_valid_zero_and_checksum(self):
        config,manifest=s.configuration(ROOT);asset=copy.deepcopy(next(x for x in manifest['assets'] if x['map_code']=='RES05-SXX30AS'))
        asset.update(expected_width=4,expected_height=2,expected_resolution_degrees=1.,expected_dtype='int16')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.tif';raw=np.array([[0,100,-9,700],[300,400,500,600]],dtype='int16');mask=np.full(raw.shape,255,dtype='uint8');mask[1,1]=0
            with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True),rasterio.open(source,'w',driver='GTiff',width=4,height=2,count=1,dtype='int16',crs=4326,transform=from_origin(-180,90,1,1),nodata=-9) as dst:
                dst.write(raw,1);dst.write_mask(mask)
            sidecar=dict(workspaceCode='GAEZ-V5',mapsetCode=asset['map_code'],code=asset['object_name'][:-4],dimensionMembers=[dict(dimensionCode=k,code=v) for k,v in [('PERIOD',asset['period_code']),('CLIM',asset['climate_model_code']),('SSP',asset['ssp_code']),('CROP-RES05','MZE'),('WSIM-RES05',asset['management_code'])]])
            def get(url,path,cfg):write_json(path,sidecar);return {'ETag':'synthetic'}
            with patch.object(s,'bounded_get',get),patch.object(s,'range_probe',return_value={'Content-Range':'bytes 0-16383/20000'}):
                receipt=s.extract(asset,box(-180,88,-177,90),root/'clip',config,opener=lambda _:rasterio.open(source))
            self.assertEqual(receipt['verification_status'],'VERIFIED_INSIDE_AOI',receipt)
            self.assertTrue(receipt['clip_reopened']);self.assertTrue(receipt['area_closure_passed']);self.assertEqual(receipt['minimum'],0)
            self.assertEqual(receipt['clip_sha256'],sha256(root/'clip/clip.tif'))
            with rasterio.open(root/'clip/clip.tif') as src:self.assertEqual(src.read_masks(1)[1,1],0);self.assertEqual(src.read_masks(1)[0,0],255)

    def test_wrong_json_identity_rejected(self):
        asset=s.configuration(ROOT)[1]['assets'][0]
        with self.assertRaises(s.VerificationError):s.validate_sidecar(asset,{'workspaceCode':'GAEZ-V5'})
        bad=dict(asset,tiff_url=asset['tiff_url'].replace('MZE','WHE'))
        with self.assertRaises(s.VerificationError):s.validate_identity(bad)

    def test_non_range_server_cannot_trigger_global_download(self):
        cfg,_=s.configuration(ROOT)
        class Response:
            status_code=200;headers={};url='https://example.test/source.tif'
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def raise_for_status(self):pass
            def iter_content(self,*args):raise AssertionError('Response body must not be consumed')
        with patch.object(s.requests,'get',return_value=Response()):
            with self.assertRaises(s.VerificationError):s.range_probe(Response.url,cfg)
