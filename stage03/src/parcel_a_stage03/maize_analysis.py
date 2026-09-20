"""Native-cell geometric support and descriptive maize comparisons.

No display resampling, class-code arithmetic, model probabilities or crop ranking.
"""
from __future__ import annotations
from collections import Counter
from itertools import combinations
import math
import numpy as np
from shapely.geometry import box, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .spatial import project_geometry, weighted_summary

MODELS=('GFDL-ESM4','IPSL-CM6A-LR','MPI-ESM1-2-HR','MRI-ESM2-0','UKESM1-0-LL')
CLASS_LABELS={1:'SI > 85: Very high',2:'SI > 70: High',3:'SI > 55: Good',4:'SI > 40: Medium',5:'SI > 25: Moderate',6:'SI > 10: Marginal',7:'SI > 0: Very marginal',8:'Not suitable',9:'Water'}
CLASS_COLOURS=['#1A9850','#66BD63','#A6D96A','#D9EF8B','#FEE08B','#FDAE61','#F46D43','#D73027','#2C7BB6']
AREA_CRS='EPSG:6933'


def native_cells(result,aoi):
    if '_support_cells' in result:return result['_support_cells']
    target=project_geometry(aoi,4326,AREA_CRS,.0005)
    t=result['transform'];step=min(abs(t.a),abs(t.e))/8
    cells=[]
    for row,col in zip(*np.where(result['weights']>0)):
        x0,y0=t*(int(col),int(row));x1,y1=t*(int(col)+1,int(row)+1)
        geom=project_geometry(box(min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1)),result['crs'],AREA_CRS,step).intersection(target)
        if geom.area<=target.area*1e-14:continue
        cells.append(dict(geometry=geom,row=int(row),column=int(col),value=float(result['values'][row,col]) if result['valid'][row,col] else None,
                          cell_id=f'{result["crs"]}:{x0:.10f}:{y0:.10f}:{abs(t.a):.10f}:{abs(t.e):.10f}'))
    result['_support_cells']=cells
    return cells


def same_grid(results):
    first=results[0]
    return all(r['crs']==first['crs'] and r['values'].shape==first['values'].shape and r['transform'].almost_equals(first['transform'],1e-10) for r in results)


def common_support(items,aoi):
    """Intersect exact native valid cells. Return a disjoint support partition."""
    if not items:raise ValueError('At least one verified source is required')
    ids=[l['layer_id'] for l,r in items]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate analytical layer in common support')
    target=project_geometry(aoi,4326,AREA_CRS,.0005);minimum=target.area*1e-14
    all_cells=[native_cells(r,aoi) for l,r in items]
    footprints=[unary_union([c['geometry'] for c in cells]) for cells in all_cells]
    footprint=target
    for g in footprints:footprint=footprint.intersection(g)
    if same_grid([r for l,r in items]):
        by_position=[{(c['row'],c['column']):c for c in cells} for cells in all_cells]
        units=[]
        for pos,cell in by_position[0].items():
            members=[d.get(pos) for d in by_position]
            if any(c is None or c['value'] is None for c in members):continue
            units.append(dict(geometry=cell['geometry'],values=[c['value'] for c in members],cell_ids=[c['cell_id'] for c in members]))
    else:
        units=[dict(geometry=c['geometry'],values=[c['value']],cell_ids=[c['cell_id']]) for c in all_cells[0] if c['value'] is not None]
        for cells in all_cells[1:]:
            valid=[c for c in cells if c['value'] is not None]
            if not valid:units=[];break
            tree=STRtree([c['geometry'] for c in valid]);next_units=[]
            for u in units:
                for index in tree.query(u['geometry'],predicate='intersects'):
                    c=valid[index];geom=u['geometry'].intersection(c['geometry'])
                    if geom.area>minimum:next_units.append(dict(geometry=geom,values=u['values']+[c['value']],cell_ids=u['cell_ids']+[c['cell_id']]))
            units=next_units
    for i,u in enumerate(units):u.update(unit_id=f'u{i+1:05d}',area_ha=u['geometry'].area/1e4)
    common=sum(u['area_ha'] for u in units);total=target.area/1e4
    outside=max(0.,(target.area-footprint.area)/1e4);masked=max(0.,footprint.area/1e4-common)
    if abs(common+masked+outside-total)>total*.0001:raise ValueError('Common-support area accounting failed')
    support=dict(layer_ids=ids,common_valid_area_ha=common,aoi_area_ha=total,common_valid_percentage=100*common/total,
        excluded_masked_area_ha=masked,excluded_outside_footprint_area_ha=outside,excluded_area_ha=masked+outside,
        analytical_unit_count=len(units),quality_flag='NO_COMMON_VALID_SUPPORT' if not units else 'FEW_NATIVE_CELLS' if len(units)<5 else 'OK',
        support_method='Exact native-cell intersections in EPSG:6933; no statistical resampling',same_native_grid=same_grid([r for l,r in items]),
        source_valid_area_ha={l['layer_id']:r['stats']['valid_area_ha'] for l,r in items},
        native_cell_counts={l['layer_id']:len({u['cell_ids'][i] for u in units}) for i,(l,r) in enumerate(items)})
    return units,support


def numeric(values):
    x=np.asarray(values,dtype=float);mean=float(x.mean());std=float(x.std(ddof=0))
    p25,p75=np.percentile(x,[25,75],method='linear')
    return dict(model_mean=mean,model_median=float(np.median(x)),model_minimum=float(x.min()),model_maximum=float(x.max()),
        model_standard_deviation=std,model_iqr=float(p75-p25),model_range=float(x.max()-x.min()),
        model_coefficient_of_variation=std/mean if mean>0 else None,cv_status='DEFINED' if mean>0 else 'UNDEFINED_NONPOSITIVE_MEAN')


def five_models(items,aoi):
    if len(items)!=5 or {l.get('climate_model_code') for l,r in items}!=set(MODELS):
        raise ValueError('Five distinct verified individual GCMs are required; ENSEMBLE is excluded')
    dimensions={(l['map_code'],l['period_code'],l['ssp_code'],l['management_code']) for l,r in items}
    if len(dimensions)!=1:raise ValueError('Product, period, SSP and management must match')
    items=sorted(items,key=lambda p:MODELS.index(p[0]['climate_model_code']))
    units,support=common_support(items,aoi);categorical=items[0][0]['data_type']=='categorical'
    rows=[];pairs=[];model_summary=[];frequencies=[];common=support['common_valid_area_ha']
    for u in units:
        row=dict(unit_id=u['unit_id'],area_ha=u['area_ha'],source_cell_ids=u['cell_ids'],model_values=dict(zip(MODELS,u['values'])))
        if categorical:
            counts=Counter(map(int,u['values']));count=max(counts.values());winners=sorted(k for k,v in counts.items() if v==count)
            unique=len(winners)==1;ordered=[v for v in counts if v!=9]
            row.update(class_frequencies={str(c):counts[c] for c in range(1,10)},modal_class=winners[0] if unique else None,
                tied_modal_classes=winners if not unique else [],modal_count=count,unique_mode=unique,full_agreement=int(count==5),
                strong_agreement=int(count>=4),majority_agreement=int(unique and count==3),
                agreement_group='5/5 unanimous' if count==5 else '4/5 strong' if count==4 else '3/5 majority' if unique and count==3 else 'Tied / dispersed',
                unique_class_count=len(counts),tie_flag=int(not unique),tied_or_dispersed=int(count<3),
                highest_suitability_label=CLASS_LABELS[min(ordered)] if ordered else None,
                lowest_suitability_label=CLASS_LABELS[max(ordered)] if ordered else None,
                water_present=9 in counts,ordered_range_rule='Labels 1–8 only; Water excluded; no numeric class range')
            for c in range(1,10):frequencies.append(dict(unit_id=u['unit_id'],area_ha=u['area_ha'],class_code=c,class_label=CLASS_LABELS[c],model_count=counts[c],model_fraction=counts[c]/5,interpretation='Descriptive model frequency, not a probability'))
        else:row.update(numeric(u['values']))
        u['derived']=row;rows.append(row)
    weights=np.array([u['area_ha'] for u in units])
    for i,model in enumerate(MODELS):
        values=np.array([u['values'][i] for u in units])
        if categorical:
            for c in range(1,10):
                area=float(weights[values==c].sum())
                model_summary.append(dict(model=model,class_code=c,class_label=CLASS_LABELS[c],area_ha=area,percentage_of_common_valid_area=100*area/common if common else None))
        else:model_summary.append(dict(model=model,**weighted_summary(values,weights)))
    for i,j in combinations(range(5),2):
        left=np.array([u['values'][i] for u in units]);right=np.array([u['values'][j] for u in units]);pair=dict(model_a=MODELS[i],model_b=MODELS[j],common_valid_area_ha=common)
        if categorical:
            area=float(weights[left==right].sum());pair.update(agreement_area_ha=area,agreement_percentage=100*area/common if common else None)
        else:
            diff=right-left;pair.update(difference_definition='model_b minus model_a',**weighted_summary(diff,weights))
            for row,u,value in zip(rows,units,diff):row.setdefault('pairwise_differences',{})[MODELS[j]+' minus '+MODELS[i]]=float(value)
        pairs.append(pair)
    summary=dict(support,model_count=5,model_set=list(MODELS),project_derived=True)
    if categorical:
        summary['agreement_areas_ha']={label:sum(r['area_ha'] for r in rows if r['agreement_group']==label) for label in ['5/5 unanimous','4/5 strong','3/5 majority','Tied / dispersed']}
        summary['modal_class_area_ha']={str(c):sum(r['area_ha'] for r in rows if r['modal_class']==c) for c in range(1,10)}
        summary['unanimous_class_area_ha']={str(c):sum(r['area_ha'] for r in rows if r['modal_class']==c and r['full_agreement']) for c in range(1,10)}
        summary['tied_mode_area_ha']=sum(r['area_ha'] for r in rows if not r['unique_mode'])
    else:
        keys=['model_mean','model_median','model_minimum','model_maximum','model_standard_deviation','model_iqr','model_range','model_coefficient_of_variation']
        summary['area_weighted_spatial_summaries']={key:weighted_summary(np.array([r[key] if r[key] is not None else np.nan for r in rows]),weights) for key in keys}
        means=[r['mean'] for r in model_summary if r['mean'] is not None]
        summary['across_five_aoi_model_means']=numeric(means) if len(means)==5 else None
        summary['formula']='Per unit: equal-weight five-model population SD, linear quartiles, CV=SD/positive mean. AOI: intersection-area weighted on common support; across-model AOI means reported separately.'
    return dict(items=items,units=units,support=support,rows=rows,model_summary=model_summary,pairwise=pairs,class_frequencies=frequencies,summary=summary)


def compare(items,aoi,kind):
    """Two matched source layers; differences use exactly the same valid support."""
    if len(items)!=2:raise ValueError('A comparison requires two sources')
    a,b=[x[0] for x in items]
    if a['map_code']!=b['map_code'] or a['management_code']!=b['management_code']:raise ValueError('Cross-product or cross-management arithmetic is prohibited')
    if kind=='cross_ssp' and (a['period_code'],a['climate_model_code'])!=(b['period_code'],b['climate_model_code']):raise ValueError('SSP comparison requires matching period and GCM')
    if kind=='cross_period' and (a['ssp_code'],a['climate_model_code'])!=(b['ssp_code'],b['climate_model_code']):raise ValueError('Period comparison requires matching SSP and GCM')
    if kind=='historical_future' and (a['period_code']!='HP0120' or not b['period_code'].startswith('FP')):raise ValueError('Historical/future order is required')
    units,support=common_support(items,aoi);categorical=a['data_type']=='categorical';rows=[]
    for u in units:
        left,right=u['values'];row=dict(unit_id=u['unit_id'],area_ha=u['area_ha'],source_cell_ids=u['cell_ids'],value_a=left,value_b=right)
        if categorical:row.update(class_a=int(left),class_b=int(right),label_a=CLASS_LABELS[int(left)],label_b=CLASS_LABELS[int(right)],class_match=left==right)
        else:row.update(absolute_difference=right-left,percentage_difference=100*(right-left)/left if left!=0 else None,
            percentage_status='DEFINED' if left!=0 else 'UNDEFINED_ZERO_BASELINE')
        rows.append(row)
    summary=dict(support,comparison_kind=kind,layer_a=a['layer_id'],layer_b=b['layer_id'],difference_definition='Class transitions; source codes are never subtracted' if categorical else 'B minus A on shared valid support',
        baseline_context='Different climate sources and periods; descriptive model comparison, not attributable climate-only change' if kind=='historical_future' else 'Matched product, management and remaining scenario dimensions')
    weights=np.array([u['area_ha'] for u in units]);area=support['common_valid_area_ha']
    if categorical:
        summary['transitions']=[dict(class_a=i,class_b=j,label_a=CLASS_LABELS[i],label_b=CLASS_LABELS[j],area_ha=sum(r['area_ha'] for r in rows if r['class_a']==i and r['class_b']==j)) for i,j in sorted({(r['class_a'],r['class_b']) for r in rows})]
        summary['unchanged_area_ha']=sum(r['area_ha'] for r in rows if r['class_match'])
        summary['agreement_percentage']=100*summary['unchanged_area_ha']/area if area else None
    else:
        for key in ['value_a','value_b','absolute_difference','percentage_difference']:
            summary[key]=weighted_summary(np.array([r[key] if r[key] is not None else np.nan for r in rows]),weights)
        summary['percentage_defined_area_ha']=sum(r['area_ha'] for r in rows if r['percentage_difference'] is not None)
        ma,mb=summary['value_a']['mean'],summary['value_b']['mean']
        summary['percentage_change_of_aoi_means']=100*(mb-ma)/ma if ma not in {None,0} else None
    return dict(rows=rows,units=units,summary=summary,support=support)


def matched_group_comparison(left,right,aoi,kind):
    """Compare derived five-GCM metrics on the intersection of all ten inputs."""
    la,lb=left['items'][0][0],right['items'][0][0]
    if la['map_code']!=lb['map_code'] or la['management_code']!=lb['management_code']:raise ValueError('Derived groups must match product and management')
    if kind=='cross_ssp' and la['period_code']!=lb['period_code']:raise ValueError('Derived SSP groups must match period')
    if kind=='cross_period' and la['ssp_code']!=lb['ssp_code']:raise ValueError('Derived period groups must match SSP')
    units,support=common_support(left['items']+right['items'],aoi);rows=[];categorical=la['data_type']=='categorical'
    for u in units:
        row=dict(unit_id=u['unit_id'],area_ha=u['area_ha'])
        if categorical:
            for side,values in [('a',u['values'][:5]),('b',u['values'][5:])]:
                c=Counter(map(int,values));m=max(c.values());w=[k for k,v in c.items() if v==m]
                row.update({f'modal_class_{side}':w[0] if len(w)==1 else None,f'modal_count_{side}':m,f'unique_class_count_{side}':len(c),f'unanimity_{side}':int(m==5),f'strong_agreement_{side}':int(m>=4)})
            row['modal_comparison_status']='DEFINED' if row['modal_class_a'] is not None and row['modal_class_b'] is not None else 'EXCLUDED_TIED_MODE'
        else:
            a,b=numeric(u['values'][:5]),numeric(u['values'][5:])
            row.update({k+'_a':v for k,v in a.items()});row.update({k+'_b':v for k,v in b.items()})
            for key in ['model_mean','model_median','model_standard_deviation','model_iqr','model_range','model_coefficient_of_variation']:
                row[key+'_difference']=b[key]-a[key] if a[key] is not None and b[key] is not None else None
        rows.append(row)
    summary=dict(support,comparison_kind=kind,project_derived=True)
    if categorical:
        summary['modal_comparable_area_ha']=sum(r['area_ha'] for r in rows if r['modal_comparison_status']=='DEFINED')
        summary['tied_mode_excluded_area_ha']=support['common_valid_area_ha']-summary['modal_comparable_area_ha']
        summary['modal_transitions']=[dict(class_a=i,class_b=j,area_ha=sum(r['area_ha'] for r in rows if r['modal_class_a']==i and r['modal_class_b']==j)) for i,j in sorted({(r['modal_class_a'],r['modal_class_b']) for r in rows if r['modal_comparison_status']=='DEFINED'})]
        for key in ['unanimity','strong_agreement']:
            for side in ['a','b']:summary[key+'_'+side+'_area_ha']=sum(r['area_ha'] for r in rows if r[key+'_'+side])
        summary['spread_transitions']=[dict(classes_a=i,classes_b=j,area_ha=sum(r['area_ha'] for r in rows if r['unique_class_count_a']==i and r['unique_class_count_b']==j)) for i,j in sorted({(r['unique_class_count_a'],r['unique_class_count_b']) for r in rows})]
    else:
        weights=np.array([r['area_ha'] for r in rows])
        summary['metric_differences']={k:weighted_summary(np.array([r[k] if r[k] is not None else np.nan for r in rows]),weights) for k in ['model_mean_difference','model_standard_deviation_difference','model_iqr_difference','model_range_difference','model_coefficient_of_variation_difference']}
    return dict(rows=rows,summary=summary,units=units,support=support)


def ensemble_diagnostic(group,ensemble,aoi):
    source=ensemble[0];first=group['items'][0][0]
    if source['climate_model_code']!='ENSEMBLE' or any(source[k]!=first[k] for k in ['map_code','period_code','ssp_code','management_code']):raise ValueError('ENSEMBLE diagnostic dimensions do not match')
    units,support=common_support(group['items']+[ensemble],aoi);rows=[];categorical=first['data_type']=='categorical'
    for u in units:
        vals=u['values'];row=dict(unit_id=u['unit_id'],area_ha=u['area_ha'],ensemble_value=vals[5])
        if categorical:
            counts=Counter(map(int,vals[:5]));m=max(counts.values());w=[k for k,v in counts.items() if v==m]
            row.update(unique_modal_class=w[0] if len(w)==1 else None,modal_count=m,tied_mode=len(w)>1,
                       match_unique_mode=vals[5]==w[0] if len(w)==1 else None)
        else:row.update(derived_five_model_mean=float(np.mean(vals[:5])),ensemble_minus_derived_mean=vals[5]-float(np.mean(vals[:5])))
        rows.append(row)
    summary=dict(support,interpretation='Diagnostic only. The source ENSEMBLE aggregation is not inferred; it is never a sixth GCM.')
    if categorical:
        comparable=sum(r['area_ha'] for r in rows if not r['tied_mode']);match=sum(r['area_ha'] for r in rows if r['match_unique_mode'])
        summary.update(unique_mode_comparable_area_ha=comparable,tied_mode_excluded_area_ha=support['common_valid_area_ha']-comparable,
                       matching_area_ha=match,matching_percentage=100*match/comparable if comparable else None)
    else:summary['ensemble_minus_derived_mean']=weighted_summary(np.array([r['ensemble_minus_derived_mean'] for r in rows]),np.array([r['area_ha'] for r in rows]))
    return dict(rows=rows,summary=summary,units=units,support=support)
