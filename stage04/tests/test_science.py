"""Hand-computed cases, deliberately unlike the implementation's data flow."""
import math
import unittest
from parcel_a_stage04.analysis import MODELS,unit_metrics,summarize
from parcel_a_stage04.contract import decode,index_evidence

CROSSWALK={i:dict(caption=f'Source class {i}',colour=f'#{i:06x}') for i in range(1,8)}


def values(*numbers):return dict(zip(MODELS,numbers))
def unit(area,*numbers):return dict(area_ha=area,model_values=values(*numbers))


class ScienceTests(unittest.TestCase):
    def test_weighted_mean_preserves_valid_zeros_and_partial_coverage(self):
        r=summarize([unit(2,0,0,0,0,0),unit(1,0,10,20,30,40)],3,4,False,{})
        self.assertAlmostEqual(r['whole_aoi_mean'],20/3)
        self.assertEqual(r['positive_yield_area_ha'],1)
        self.assertEqual(r['valid_zero_area_ha'],2)
        self.assertEqual(r['positive_area_mean'],20)
        self.assertEqual(r['common_valid_percentage'],75)
        self.assertAlmostEqual(r['positive_yield_percentage'],100/3)
        self.assertAlmostEqual(r['positive_yield_area_ha']+r['valid_zero_area_ha'],3)
        self.assertAlmostEqual(r['inter_model_cv'],math.sqrt(200)/20)
        self.assertEqual(r['cv_valid_area_ha'],1)

    def test_population_spread_and_linear_quartiles(self):
        r=unit_metrics(values(0,10,20,30,40),False,{})
        for k,v in [('model_mean',20),('model_median',20),('model_minimum',0),('model_maximum',40),('model_range',40),('model_iqr',20),('zero_model_count',1)]:self.assertEqual(r[k],v)
        self.assertAlmostEqual(r['model_standard_deviation'],math.sqrt(200))

    def test_zero_spread_is_not_zero_yield(self):
        u=unit(10,100,100,100,100,100);r=summarize([u],10,10,False,{})
        self.assertEqual(r['positive_yield_area_ha'],10)
        self.assertEqual(r['valid_zero_area_ha'],0)
        self.assertEqual(r['inter_model_cv'],0)
        self.assertTrue(u['metrics']['positive_yield'])

    def test_no_positive_area_is_undefined_not_zero(self):
        r=summarize([unit(2,0,0,0,0,0)],2,2,False,{})
        self.assertEqual(r['whole_aoi_mean'],0)
        self.assertIsNone(r['positive_area_mean']);self.assertIsNone(r['inter_model_cv'])
        self.assertEqual(r['cv_valid_area_ha'],0)
        self.assertIn('no positive-yield area',r['positive_area_mean_status'])

    def test_cv_is_mean_of_defined_unit_ratios(self):
        r=summarize([unit(1,0,0,0,0,10),unit(3,100,100,100,100,100)],4,4,False,{})
        self.assertEqual(r['inter_model_cv'],.5)
        self.assertEqual(r['whole_aoi_mean'],75.5)

    def test_tied_modes_never_become_categories_or_code_means(self):
        r=unit_metrics(values(1,1,2,2,3),True,CROSSWALK)
        self.assertIsNone(r['modal_class']);self.assertEqual(r['tied_modal_classes'],[1,2])
        self.assertEqual(r['tie_flag'],1);self.assertEqual(r['tied_or_dispersed'],1)
        self.assertEqual(r['unique_class_count'],3)
        self.assertNotIn('model_mean',r)

    def test_strong_agreement_includes_full_and_dominance_uses_area(self):
        r=summarize([unit(3,1,1,1,1,1),unit(1,2,2,2,2,3),unit(2,3,3,3,1,2),unit(4,1,1,2,2,3)],10,10,True,CROSSWALK)
        self.assertEqual(r['dominant_class'],1);self.assertEqual(r['dominant_class_percentage'],30)
        self.assertEqual(r['full_agreement_percentage'],30)
        self.assertEqual(r['strong_agreement_percentage'],40)
        self.assertEqual(r['majority_agreement_percentage'],20)
        self.assertEqual(r['tied_or_dispersed_percentage'],40)

    def test_dominant_spatial_area_tie_is_retained(self):
        r=summarize([unit(2,1,1,1,1,1),unit(2,2,2,2,2,2)],4,4,True,CROSSWALK)
        self.assertIsNone(r['dominant_class']);self.assertIsNone(r['dominant_class_percentage'])

    def test_product_support_remains_separate(self):
        y=summarize([unit(3,1,1,1,1,1)],3,5,False,{})
        s=summarize([unit(2,1,1,1,1,1)],2,5,True,CROSSWALK)
        self.assertEqual((y['common_valid_percentage'],s['common_valid_percentage']),(60,40))

    def test_empty_support_is_explicit(self):
        r=summarize([],0,4,False,{})
        self.assertEqual(r['status'],'NO_COMMON_VALID_AREA');self.assertNotIn('whole_aoi_mean',r)

    def test_nodata_nonfinite_and_nonfive_models_rejected(self):
        for bad in [values(-9,1,1,1,1),values(float('nan'),1,1,1,1),values(float('inf'),1,1,1,1),values(True,1,1,1,1),dict(values(1,1,1,1,1),ENSEMBLE=1),values(1,1,1,1)]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):unit_metrics(bad,False,{})
        with self.assertRaises(ValueError):unit_metrics(values(1,1,1,1,99),True,CROSSWALK)
        with self.assertRaises(ValueError):summarize([unit(2,1,1,1,1,1)],3,4,False,{})

    def test_csv_boolean_decoding_and_ambiguous_keys(self):
        self.assertIs(decode({'valid':'True'})['valid'],True)
        self.assertIs(decode({'valid':'False'})['valid'],False)
        self.assertEqual(decode({'valid':'true'})['valid'],True)
        resolved,duplicates=index_evidence([{'id':1},{'id':1},{'id':2}],lambda r:r['id'])
        self.assertEqual(set(resolved),{2});self.assertEqual(duplicates,{1})
