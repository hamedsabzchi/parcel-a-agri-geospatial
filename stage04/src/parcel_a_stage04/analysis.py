"""Evidence summaries computed from five verified native-unit model values."""
from collections import Counter
import numpy as np
from .common import number

MODELS=('GFDL-ESM4','IPSL-CM6A-LR','MPI-ESM1-2-HR','MRI-ESM2-0','UKESM1-0-LL')
PERIODS={'FP2140':'2021–2040','FP4160':'2041–2060','FP6180':'2061–2080','FP8100':'2081–2100'}
SSPS={'SSP126':'SSP1-2.6','SSP370':'SSP3-7.0','SSP585':'SSP5-8.5'}
MANAGEMENT={'HRLM':'Rainfed, high input','HILM':'Irrigated, high input'}
YIELD_METRICS=('model_mean','model_median','model_minimum','model_maximum','model_range','model_iqr','model_standard_deviation','model_coefficient_of_variation')
SUIT_METRICS=('modal_class','modal_count','full_agreement','strong_agreement','majority_agreement','unique_class_count','tie_flag','tied_or_dispersed')


def unit_metrics(values,categorical,crosswalk):
    if set(values)!=set(MODELS):raise ValueError('Exactly five distinct individual GCMs required; ENSEMBLE excluded')
    x=np.array([number(values[m]) for m in MODELS])
    if categorical:
        if any(v!=int(v) or int(v) not in crosswalk for v in x):raise ValueError('Unknown suitability class')
        counts=Counter(map(int,x));count=max(counts.values());winners=sorted(k for k,v in counts.items() if v==count)
        return dict(modal_class=winners[0] if len(winners)==1 else None,modal_count=count,full_agreement=int(count==5),
            strong_agreement=int(count>=4),majority_agreement=int(count==3 and len(winners)==1),unique_class_count=len(counts),
            tie_flag=int(len(winners)>1),tied_or_dispersed=int(count<3),tied_modal_classes=winners if len(winners)>1 else [],
            class_frequencies={str(c):counts[c] for c in crosswalk})
    if (x<0).any():raise ValueError('A NoData code or negative yield entered valid common support')
    mean=float(x.mean());sd=float(x.std(ddof=0));q=np.percentile(x,[25,75],method='linear')
    return dict(model_mean=mean,model_median=float(np.median(x)),model_minimum=float(x.min()),model_maximum=float(x.max()),
        model_range=float(x.max()-x.min()),model_iqr=float(q[1]-q[0]),model_standard_deviation=sd,
        model_coefficient_of_variation=sd/mean if mean>0 else None,zero_model_count=int((x==0).sum()),
        positive_yield=mean>0,valid_zero_yield=mean==0)


def summarize(units,common,aoi,categorical,crosswalk,tolerance=.0001):
    common=number(common);aoi=number(aoi)
    if aoi<=0 or common<0 or common>aoi*(1+tolerance):raise ValueError('Invalid common-support denominator')
    weights=np.array([number(u['area_ha']) for u in units]);area=float(weights.sum())
    if any(w<=0 for w in weights) or abs(area-common)>aoi*tolerance:raise ValueError('Common-support area closure failed')
    for u in units:u['metrics']=unit_metrics(u['model_values'],categorical,crosswalk)
    result=dict(common_valid_area_ha=common,common_valid_percentage=100*common/aoi,aoi_area_ha=aoi,analytical_unit_count=len(units),
        excluded_area_ha=max(0.,aoi-common),denominator='Product-specific five-model common valid area',
        status='VERIFIED' if common>0 else 'NO_COMMON_VALID_AREA')
    if not common:return result
    weighted=lambda key:float(sum(u['area_ha']*u['metrics'][key] for u in units if u['metrics'].get(key) is not None)/sum(u['area_ha'] for u in units if u['metrics'].get(key) is not None)) if any(u['metrics'].get(key) is not None for u in units) else None
    if categorical:
        areas={c:sum(u['area_ha'] for u in units if u['metrics']['modal_class']==c) for c in crosswalk}
        maximum=max(areas.values(),default=0.);winners=[c for c,v in areas.items() if maximum>0 and abs(v-maximum)<=max(1e-8,common*1e-10)]
        dominant=winners[0] if len(winners)==1 else None
        result.update(dominant_class=dominant,dominant_class_label=crosswalk[dominant]['caption'] if dominant is not None else 'No unique dominant modal suitability class.',
            dominant_class_area_ha=maximum if dominant is not None else None,dominant_class_percentage=100*maximum/common if dominant is not None else None,
            modal_area_by_class=areas,dominance_rule='Largest area assigned a unique per-unit modal class; equal largest areas retain a tie')
        for metric in ['full_agreement','strong_agreement','majority_agreement','tied_or_dispersed','tie_flag']:
            ha=sum(u['area_ha'] for u in units if u['metrics'][metric]);result[metric+'_area_ha']=ha;result[metric+'_percentage']=100*ha/common
        result['unique_class_count_area_ha']={str(n):sum(u['area_ha'] for u in units if u['metrics']['unique_class_count']==n) for n in range(1,6)}
    else:
        pos=sum(u['area_ha'] for u in units if u['metrics']['positive_yield']);zero=sum(u['area_ha'] for u in units if u['metrics']['valid_zero_yield'])
        if abs(pos+zero-common)>aoi*tolerance:raise ValueError('Positive and valid-zero areas do not partition common support')
        result.update(whole_aoi_mean=weighted('model_mean'),positive_yield_area_ha=pos,positive_yield_percentage=100*pos/common,
            positive_area_mean=sum(u['area_ha']*u['metrics']['model_mean'] for u in units if u['metrics']['positive_yield'])/pos if pos else None,
            positive_area_mean_status='DEFINED' if pos else 'Not applicable: no positive-yield area.',valid_zero_area_ha=zero,valid_zero_percentage=100*zero/common,
            inter_model_cv=weighted('model_coefficient_of_variation'),cv_valid_area_ha=sum(u['area_ha'] for u in units if u['metrics']['model_coefficient_of_variation'] is not None),
            inter_model_cv_status='DEFINED' if pos else 'Not applicable: five-model mean is zero throughout common support.',
            population_sd=weighted('model_standard_deviation'),iqr=weighted('model_iqr'),model_range=weighted('model_range'),
            model_minimum=min(u['metrics']['model_minimum'] for u in units),model_maximum=max(u['metrics']['model_maximum'] for u in units),
            unit='kg dry weight/ha',positive_rule='Per-unit five-model mean > 0; fixed for cards, trends and tables regardless of map diagnostic',
            zero_rule='Per-unit five-model mean = 0; valid model zeros retained. Zero spread is not zero yield.',
            cv_aggregation='Area-weighted mean of defined per-unit CV ratios; denominator is cv_valid_area_ha',
            whole_aoi_coverage_note='Mean over the common-valid portion of the AOI only; uncovered area is not estimated.')
    return result
