import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box
from parcel_a_stage03.spatial import area_weights,weighted_summary,read_raster,categorical_summary,project_geometry
from parcel_a_stage03.temporal import date,interval_end,aggregate_month,assert_unique_rows
from parcel_a_stage03.render import resolve_legends,rgba
from parcel_a_stage03.sources import cached_job,window


class SpatialTests(unittest.TestCase):
    def test_exact_fractional_weights_touch_and_accounting(self):
        aoi=box(0,0,1.5,1);t=from_origin(0,1,1,1)
        w,area=area_weights(aoi,t,4326,1,3)
        self.assertAlmostEqual(w[0,0]/area,2/3,places=6)
        self.assertAlmostEqual(w[0,1]/area,1/3,places=6)
        self.assertEqual(w[0,2],0)
        self.assertAlmostEqual(w.sum()/area,1,places=8)

    def test_known_weighted_statistics(self):
        s=weighted_summary(np.array([0.,10.,20.]),np.array([1.,2.,1.]))
        self.assertEqual(s['mean'],10);self.assertAlmostEqual(s['std'],np.sqrt(50))
        self.assertEqual(s['median'],10);self.assertEqual(s['p25'],0);self.assertEqual(s['p95'],20)
        self.assertEqual(weighted_summary(np.array([7.]),np.array([1.]))['std'],0)
        self.assertIsNone(weighted_summary(np.array([np.nan]),np.array([1.]))['mean'])

    def test_internal_mask_zero_and_scale_once(self):
        with tempfile.TemporaryDirectory() as work:
            p=Path(work)/'zero.tif'
            with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
                with rasterio.open(p,'w',driver='GTiff',count=1,width=2,height=1,dtype='float32',crs=4326,transform=from_origin(0,1,1,1)) as dst:
                    dst.write(np.array([[0,99]],dtype='float32'),1);dst.write_mask(np.array([[255,0]],dtype='uint8'))
            l=dict(layer_id='test',unit='physical',scale=2,offset=5,data_type='continuous',nodata=None)
            r=read_raster(p,box(0,0,2,1),l)
            self.assertEqual(r['stats']['mean'],5);self.assertEqual(r['stats']['valid_native_cell_count'],1)
            self.assertAlmostEqual(r['stats']['valid_area_percentage'],50,places=5)
            self.assertIsNone(r['stats']['raster_nodata'])
            l['scale_already_applied']=True
            self.assertEqual(read_raster(p,box(0,0,2,1),l)['stats']['mean'],0)

    def test_class_denominators_unknown_codes(self):
        r=dict(values=np.array([1.,2.,np.nan]),weights=np.array([2.,1.,1.]),stats=dict(valid_area_ha=.0003,aoi_area_ha=.0004,area_method='test'))
        l=dict(layer_id='x',dataset_id='y');legend=dict(entries=[dict(code=1,caption='One',colour='#000000'),dict(code=2,caption='Two',colour='#ffffff')])
        rows=categorical_summary(r,l,legend)
        self.assertAlmostEqual(rows[0]['percentage_of_valid_area'],2/3*100)
        self.assertEqual(rows[0]['percentage_of_total_aoi'],50)
        r['values'][0]=3
        with self.assertRaisesRegex(ValueError,'authoritative'):categorical_summary(r,l,legend)

    def test_shared_and_constant_yield_domain(self):
        registry=dict(Y=dict(type='continuous',palette='viridis'))
        layers=[(dict(layer_id='a',legend_id='Y'),dict(values=np.array([5.,8.]))),(dict(layer_id='b',legend_id='Y'),dict(values=np.array([10.])))]
        legends=resolve_legends(layers,registry)
        self.assertEqual(legends['a']['domain'],[5,10]);self.assertEqual(legends['a']['domain'],legends['b']['domain'])
        result=resolve_legends([(dict(layer_id='c',legend_id='Y'),dict(values=np.array([7.])))],registry)['c']
        self.assertTrue(result['constant']);self.assertEqual(result['domain'],[7,7])
        colours=rgba(np.array([[7.,np.nan]]),result);self.assertEqual(colours[0,1,3],0)


class TimeTests(unittest.TestCase):
    def test_variable_dekad_leap_durations(self):
        self.assertEqual((interval_end('2024-02-21','dekadal')-date('2024-02-21')).days,9)
        self.assertEqual((interval_end('2023-02-21','dekadal')-date('2023-02-21')).days,8)
        self.assertEqual((interval_end('2024-01-21','dekadal')-date('2024-01-21')).days,11)

    def test_rate_integration_not_sum_of_rates(self):
        starts=list(map(date,['2024-02-01','2024-02-11','2024-02-21']))
        ends=[interval_end(s,'dekadal') for s in starts]
        _,r=aggregate_month(np.full((3,1,1),2.),starts,ends,np.ones((1,1)),1,'2024-02-01','2024-03-01','integrate_rate')
        self.assertEqual(r['value'],58);self.assertEqual(r['temporal_coverage_percentage'],100)

    def test_amount_is_depth_not_pixel_sum_and_missing_not_zero(self):
        starts=[date('2024-02-01')+timedelta(days=i) for i in range(29)];ends=[d+timedelta(days=1) for d in starts]
        values=np.full((29,1,2),2.);weights=np.array([[.25,.75]])
        _,r=aggregate_month(values,starts,ends,weights,1,'2024-02-01','2024-03-01','sum_amount')
        self.assertEqual(r['value'],58)
        values[0]=np.nan
        _,r=aggregate_month(values,starts,ends,weights,1,'2024-02-01','2024-03-01','sum_amount')
        self.assertEqual(r['value'],56);self.assertEqual(r['quality_flag'],'PARTIAL_TOTAL')
        values[:5]=np.nan
        _,r=aggregate_month(values,starts,ends,weights,1,'2024-02-01','2024-03-01','sum_amount')
        self.assertIsNone(r['value'])

    def test_overlap_duplicate_and_multi_variable_keys(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            aggregate_month(np.ones((2,1,1)),['2024-01-01']*2,['2024-01-02']*2,np.ones((1,1)),1,'2024-01-01','2024-02-01','sum_amount')
        assert_unique_rows([dict(layer_id='a',variable='rain',interval_start='2024-01-01'),dict(layer_id='a',variable='temperature',interval_start='2024-01-01')])
        with self.assertRaisesRegex(ValueError,'Duplicate'):assert_unique_rows([dict(layer_id='a'),dict(layer_id='a')])

    def test_cross_month_rate_and_state_duration(self):
        values=np.array([[[2.]],[[4.]]]);starts=['2024-01-25','2024-02-10'];ends=['2024-02-10','2024-03-01']
        _,r=aggregate_month(values,starts,ends,np.ones((1,1)),1,'2024-02-01','2024-03-01','integrate_rate')
        self.assertEqual(r['value'],2*9+4*20)
        _,r=aggregate_month(values,starts,ends,np.ones((1,1)),1,'2024-02-01','2024-03-01','duration_mean')
        self.assertAlmostEqual(r['value'],(2*9+4*20)/29)


class CacheTests(unittest.TestCase):
    def test_reuse_change_and_corruption(self):
        calls=[]
        def producer(path):calls.append(True);(path/'result.txt').write_text('verified');return {'raster':'result.txt'}
        with tempfile.TemporaryDirectory() as temp:
            folder,_,cached=cached_job({'variable':'x'},'aoi',temp,producer);self.assertFalse(cached)
            self.assertTrue(cached_job({'variable':'x'},'aoi',temp,producer)[2]);self.assertEqual(len(calls),1)
            (folder/'result.txt').write_text('bad');self.assertFalse(cached_job({'variable':'x'},'aoi',temp,producer)[2])
            self.assertFalse(cached_job({'variable':'y'},'aoi',temp,producer)[2])
