"""Offline Earth Engine expression/transport tests and real local-file adapters."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import ee
from ee import apitestcase
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box
from parcel_a_stage03.sources import static_ee,series_ee,local_raster,local_vector,slope
from parcel_a_stage03.common import sha256
from parcel_a_stage03.inventory import configuration,resolve
from fixtures import ROOT,fixture
from parcel_a_stage03.inputs import validate


class EarthEngineAdapterTests(apitestcase.ApiTestCase):
    def test_dynamic_world_expression(self):
        layer=next(l for l in configuration(ROOT)['layer_catalog']['layers'] if l['layer_id']=='dynamicworld_2024')
        expressions=[]
        def download(image,*args,**kwargs):
            expressions.append(json.loads(image.serialize()));return {'crs':'EPSG:4326'}
        with tempfile.TemporaryDirectory() as temp, patch.object(ee.Number,'getInfo',return_value=3),patch.object(ee.Projection,'getInfo',return_value={'crs':'EPSG:4326','transform':[.1,0,0,0,-.1,1]}),patch.object(ee.List,'getInfo',side_effect=[['a','b','c'],[1,2,3]]),patch.object(ee.Image,'getInfo',return_value={'bands':[{'id':'label'}]}),patch('parcel_a_stage03.sources.ee_download',side_effect=download):
            result=static_ee(layer,box(.1,.1,.2,.2),Path(temp),configuration(ROOT)['stage03_config'])
        serialized=json.dumps(expressions)
        self.assertIn('Image.arrayArgmax',serialized);self.assertIn('Image.updateMask',serialized)
        self.assertEqual(result['metadata']['minimum_observations'],3)

    def test_series_expression_grid_scale_mask_and_transport(self):
        layer=next(l for l in configuration(ROOT)['layer_catalog']['layers'] if l['layer_id']=='era5_temperature')
        layer.update(configuration(ROOT)['timeseries_config']['defaults']);layer.update(start='2024-01-01',end='2024-01-03')
        projection={'crs':'EPSG:4326','transform':[.1,0,0,0,-.1,1]}
        def download(image,proj,aoi,path,cfg,bands=1,**kwargs):
            self.assertIn('Image.rename',image.serialize())
            with rasterio.open(path,'w',driver='GTiff',count=bands,width=2,height=2,dtype='float32',crs=4326,transform=from_origin(0,.2,.1,.1),nodata=-999999) as dst:
                dst.write(np.full((bands,2,2),283.15,dtype='float32'))
            return dict(crs='EPSG:4326',original_projection=projection)
        with tempfile.TemporaryDirectory() as temp,patch.object(ee.Number,'getInfo',return_value=2),patch.object(ee.Projection,'getInfo',return_value=projection),patch.object(ee.List,'getInfo',side_effect=[[1704067200000,1704153600000],['20240101','20240102'],[projection,projection]]),patch('parcel_a_stage03.sources.ee_download',side_effect=download):
            result=series_ee(layer,box(0,0,.2,.2),Path(temp),configuration(ROOT)['stage03_config'])
            self.assertAlmostEqual(result['series'][0]['value'],10,places=4)
            self.assertEqual(result['series'][0]['observation_count'],2)
            self.assertTrue((Path(temp)/'monthly.tif').is_file())


class SupplementalTests(unittest.TestCase):
    def test_explicit_file_verification_preserves_stage02_and_native_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source,_=fixture(folder);inputs=validate(source,ROOT)
            raster=folder/'local.tif'
            with rasterio.open(raster,'w',driver='GTiff',count=1,width=4,height=4,dtype='float32',crs=4326,transform=from_origin(13.8,6.8,.1,.1),nodata=-9999) as dst:dst.write(np.arange(16,dtype='float32').reshape(4,4),1)
            supplied=dict(layer_id='supplied_test',dataset_id='LC_LOCAL_PROJECT',display_name='Synthetic supplementary test',local_path=str(raster),expected_sha256=sha256(raster),unit='test unit',data_type='continuous',variable='band1',mask_rule='intrinsic NoData',licence='test only',licence_url='test fixture',source_url='test fixture',metadata_url='test fixture',limitation='Synthetic test only')
            cfg=configuration(ROOT);cfg['stage03_config']['supplemental_files']=[supplied]
            before=next(r for r in inputs['sources'] if r['dataset_id']=='LC_LOCAL_PROJECT')['FINAL_STATUS']
            layers,rows=resolve(inputs,cfg);layer=next(l for l in layers if l['layer_id']=='supplied_test')
            self.assertEqual(layer['extraction_status'],'PENDING');self.assertEqual(layer['stage02_status'],before)
            output=folder/'supplement';output.mkdir()
            result=local_raster(layer,inputs['aoi'],output,cfg['stage03_config'])
            self.assertEqual(result['metadata']['source_sha256'],sha256(raster))
            with rasterio.open(output/'raw.tif') as src:self.assertEqual(src.res,(.1,.1))

    def test_metric_slope_on_known_plane(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'dem.tif';output=Path(temp)/'slope.tif'
            # 30 m rise per 30 m eastward, no northward rise: slope = 45 degrees.
            with rasterio.open(path,'w',driver='GTiff',count=1,width=30,height=30,dtype='float32',crs=32633,transform=from_origin(370000,735000,30,30),nodata=np.nan) as dst:dst.write(np.tile(np.arange(30,dtype='float32')*30,(30,1)),1)
            from parcel_a_stage03.spatial import project_geometry
            aoi=project_geometry(box(370100,734300,370700,734900),32633,4326)
            slope(path,output,aoi)
            with rasterio.open(output) as src:values=src.read(1,masked=True).compressed()
            self.assertTrue(np.allclose(values,45,atol=.01))
