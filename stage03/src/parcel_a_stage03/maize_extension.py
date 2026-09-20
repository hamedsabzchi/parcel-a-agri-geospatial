"""Preserve the accepted Stage 03 package and add the complete 03.1–03.23 scope."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import copy
import json
import re
import shutil
import numpy as np
import yaml
from shapely.geometry import shape
from .common import sha256,write_json,write_csv,utcnow,code_hash,clean
from .dashboard import write_dashboard
from .spatial import categorical_summary
from . import render,maize_analysis as analysis,maize_render as maps,maize_sources as sources


def embedded_dashboard(root):
    text=(Path(root)/'dashboard/parcel_a_data_inventory.html').read_text()
    match=re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>',text,re.S)
    if not match:raise ValueError('Accepted Stage 03 dashboard data is missing')
    return json.loads(match[1])


def add_table(dashboard,payload,name,rows,fields=(),append=False):
    old=next((t for t in dashboard['tables'] if t['id']==name),None)
    if old:
        if not append:raise ValueError('Refusing to replace an existing table: '+name)
        rows=old['rows']+rows;fields=list(dict.fromkeys(old['columns']+list(fields)))
    columns=list(dict.fromkeys([*fields,*(k for row in rows for k in row)]))
    write_csv(payload/'tables'/(name+'.csv'),rows,columns)
    table=dict(id=name,title=name.replace('_',' ').title(),columns=columns,rows=rows,path='../tables/'+name+'.csv',layer_ids=sorted({r['layer_id'] for r in rows if r.get('layer_id')}))
    if old:dashboard['tables'][dashboard['tables'].index(old)]=table
    else:dashboard['tables'].append(table)


def chart(dashboard,payload,ident,title,unit,rows,table,layer_ids=(),note=''):
    rows=[r for r in rows if r.get('value') is not None and np.isfinite(r['value'])]
    if not rows:return
    spec=dict(id=ident,title=title,type='bars',unit=unit,data=rows,table_path='../tables/'+table+'.csv',
        layer_ids=list(layer_ids),note=note or 'Descriptive comparison on exact common valid native-cell support. Models are not independent observations.',path='../charts/'+ident+'.png')
    render.static_chart(payload/'charts'/(ident+'.png'),spec);dashboard['charts'].append(spec)


def historical_items(dashboard,payload,aoi):
    result=[]
    for source in dashboard['layers']:
        product=source.get('comparison_group')
        if product not in {'RES05-SIX','RES05-YXX'} or source.get('extraction_status')!='EXTRACTED':continue
        layer=dict(source,map_code=product,period_code='HP0120',climate_model_code='AGERA5',ssp_code='HIST',view='source')
        result.append((layer,sources.read_result(payload/layer['output_path'],aoi,layer,'EPSG:6933')))
    return result


def context(layer):return {k:layer.get(k) for k in ['map_code','period_code','period','ssp_code','management_code','climate_model_code']}
def group_id(key):return 'MZE_'+'_'.join(key).replace('-','_')


def extend(project,baseline,output_base=None,cache=None,progress=print,extractor=None):
    project,baseline=Path(project),Path(baseline);cfg,manifest=sources.configuration(project)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'_maize'
    run_dir=Path(output_base or project/'outputs/stage03_runs')/stamp;payload=run_dir/'package'
    shutil.copytree(baseline,payload)
    # This immutable copy includes the original dashboard, every table, every map,
    # every native output and the original self-contained checksum list.
    shutil.copytree(baseline,payload/'metadata/core_baseline')
    d=embedded_dashboard(baseline);original=copy.deepcopy(d);area=d['summary']['aoi_area_ha']
    aoi=shape(d['aoi']['features'][0]['geometry']);aoi_hash=sha256(project/'data/aoi/parcel_a.geojson')
    meta=payload/'metadata/maize';meta.mkdir(parents=True)
    shutil.copyfile(project/manifest['guide_path'],meta/'approved_guide_03_1_to_03_23.txt')
    shutil.copyfile(project/'docs/stage03_maize_methodology.md',meta/'methodology.md')
    shutil.copyfile(project/'docs/stage03_maize_traceability.md',meta/'requirements_traceability.md')
    shutil.copytree(project/'config/stage03/source_metadata',meta/'source_metadata')
    write_json(meta/'exact_source_manifest.json',manifest)
    write_json(meta/'baseline_receipt.json',dict(baseline_input=str(baseline.name),original_run_id=d['run_id'],
        original_checksum_manifest_sha256=sha256(baseline/'metadata/package_checksums.json'),original_required_gaez_count=16,original_source_count=48))
    cache=Path(cache or project/'outputs/stage03_cache');assets=copy.deepcopy(manifest['assets'])
    verified=[];reports=[];history=[];readable=[];empty=[];failures=[]
    for i,asset in enumerate(assets,1):
        progress(f'Verifying maize source {i}/{len(assets)}')
        folder,report,cached=sources.cached_extract(asset,aoi,aoi_hash,cache,cfg,extractor)
        target=payload/'clipped_data/rasters'/asset['layer_id'];shutil.copytree(folder,target,ignore=shutil.ignore_patterns('complete.json'))
        report.update(aoi_sha256=aoi_hash,code_sha256=code_hash(),licence=asset['licence'],guide_references=asset['guide_references'],cache_reused=cached)
        reports.append(report);status=report['verification_status']
        history.append(dict(layer_id=asset['layer_id'],finished=utcnow(),cached=cached,status=status))
        asset.update(verification_status=status,extraction_status='EXTRACTED' if status=='VERIFIED_INSIDE_AOI' else 'EMPTY' if status in sources.VERIFIED else 'FAILED',view='source')
        asset.update({k:v for k,v in report.items() if k not in {'source_raster','raster_http','json_http','error','guide_references'}})
        asset['reason']=report.get('error',status)
        if (target/'clip.tif').exists() and status in sources.VERIFIED:
            asset['output_path']=(target/'clip.tif').relative_to(payload).as_posix()
            result=sources.read_result(target/'clip.tif',aoi,asset,cfg['area_crs']);asset.update(result['stats']);readable.append((asset,result))
            if result['valid'].any():verified.append((asset,result))
            else:empty.append(asset)
        elif status in sources.VERIFIED:empty.append(asset)
        else:failures.append(asset)
        write_json(target/'verification.json',report)
    history_items=historical_items(original,payload,aoi)
    six_legend=copy.deepcopy(yaml.safe_load((project/'config/stage03/symbology.yml').read_text())['legends']['RES05-SIX'])
    # Pool only comparable yield units for each management; old static maps stay byte-identical.
    yield_domains={}
    for management in ['HRLM','HILM','LRLM','LILM']:
        values=[r['values'][r['valid']] for l,r in verified+history_items if l['map_code']=='RES05-YXX' and l['management_code']==management]
        if values:
            pooled=np.concatenate(values);yield_domains[management]=[float(pooled.min()),float(pooled.max())]
    categories=[];continuous=[];cells=[];new_maps=[];derived_layers=[]
    for layer,result in readable:
        cells.extend(result['cells'])
        if layer['data_type']=='categorical':
            result['categories']=categorical_summary(result,layer,six_legend);categories.extend([dict(row,**context(layer)) for row in result['categories']])
        else:continuous.append(dict(layer_id=layer['layer_id'],dataset_id=layer['dataset_id'],variable=layer['variable'],**context(layer),**result['stats']))
    for layer,result in verified:
        if layer['map_code']=='RES05-SIX':
            legend=copy.deepcopy(six_legend);present=set(map(int,np.unique(result['values'][result['valid']])))
            for entry in legend['entries']:entry['present']=entry['code'] in present
        else:
            domain=[0,10000] if layer['map_code']=='RES05-SXX30AS' else yield_domains[layer['management_code']]
            legend=maps.continuous_legend(layer['variable'],layer['unit'],domain,'Fixed 0–10000 across historical managements' if layer['map_code']=='RES05-SXX30AS' else 'Pooled historical and future valid min/max for this management')
        record=maps.record(payload,layer,result,legend,aoi,cfg['preview_max_dimension']);new_maps.append(record)
        if result.get('categories'):
            chart(d,payload,layer['layer_id']+'_area',layer['display_name']+' · class areas','ha',
                [dict(label=r['class_label'],value=r['fractional_area_ha'],colour=r['class_colour']) for r in result['categories']],
                'categorical_summary',[layer['layer_id']],layer['limitation']+' Areas use this layer’s own valid support.')
    # Add comparable historical yield previews without replacing the accepted ones.
    for old,result in history_items:
        if old['map_code']!='RES05-YXX':continue
        layer=dict(old,layer_id=old['layer_id']+'_MAIZE_SHARED_SCALE',display_name=old['display_name']+' · shared future scale',view='source',
                   theme='Historical maize yield · shared future scale',original_layer_id=old['layer_id'])
        legend=maps.continuous_legend(layer['variable'],layer['unit'],yield_domains[layer['management_code']],'Pooled historical and future valid min/max for this management')
        new_maps.append(maps.record(payload,layer,result,legend,aoi,cfg['preview_max_dimension']));derived_layers.append(layer)
    sxx=[(l,r) for l,r in verified if l['map_code']=='RES05-SXX30AS']
    chart(d,payload,'maize_historical_continuous','Historical continuous maize suitability · management alternatives','Index',
        [dict(label=l['management_code'],value=r['stats']['mean'],valid_area_percentage=r['stats']['valid_area_percentage'],cells=r['cells']) for l,r in sxx],
        'raster_summary',[l['layer_id'] for l,r in sxx],'Each management retains its own valid support; not a recommendation. Irrigated data are conditional on the source cropland mask.')
    groups=defaultdict(list);expected=defaultdict(list)
    for l in assets:
        if l['climate_model_code'] in analysis.MODELS:expected[(l['map_code'],l['period_code'],l['ssp_code'],l['management_code'])].append(l)
    for item in readable:
        l=item[0]
        if l['climate_model_code'] in analysis.MODELS:groups[(l['map_code'],l['period_code'],l['ssp_code'],l['management_code'])].append(item)
    group_results={};group_status=[];tables=defaultdict(list);summaries=[];supports=[]
    for key,planned in sorted(expected.items()):
        ident=group_id(key);items=groups[key]
        if len(items)!=5 or {l['climate_model_code'] for l,r in items}!=set(analysis.MODELS):
            group_status.append(dict(group_id=ident,product=key[0],period_code=key[1],ssp_code=key[2],management_code=key[3],status='PENDING_FIVE_VERIFIED_MODELS',verified_model_count=len(items),missing_models=sorted(set(analysis.MODELS)-{l['climate_model_code'] for l,r in items})));continue
        result=analysis.five_models(items,aoi);group_results[key]=result;ctx=dict(group_id=ident,**context(items[0][0]));ctx['climate_model_code']='FIVE_MODELS'
        support=dict(ctx,**result['support']);supports.append(support);summaries.append(dict(ctx,**result['summary']))
        group_status.append(dict(ctx,status='COMPLETE_ON_COMMON_SUPPORT' if result['units'] else 'NO_COMMON_VALID_SUPPORT',verified_model_count=5))
        for dest,source_name in [('maize_model_units','rows'),('maize_model_summary','model_summary'),('maize_pairwise','pairwise'),('maize_class_frequencies','class_frequencies')]:tables[dest].extend(dict(ctx,**row) for row in result[source_name])
        tables['maize_common_support'].append(support)
        if not result['units']:continue
        caption=' · '.join([key[0],items[0][0]['period'],key[2],key[3]])
        if key[0]=='RES05-SIX':
            metrics=[('modal_class','Unique modal class',six_legend,'Class'),
                ('modal_count','Modal agreement count',maps.discrete_legend('Models in largest class group',[(n,str(n)+'/5',c) for n,c in zip(range(1,6),['#d73027','#fc8d59','#fee08b','#91cf60','#1a9850'])]),'models'),
                ('full_agreement','Full agreement',maps.discrete_legend('All five models agree',[(0,'No','#eeeeee'),(1,'Yes · 5/5','#1a9850')]),'indicator'),
                ('strong_agreement','Strong agreement',maps.discrete_legend('At least four models agree',[(0,'No','#eeeeee'),(1,'Yes · ≥4/5','#1a9850')]),'indicator'),
                ('unique_class_count','Class-count spread',maps.discrete_legend('Distinct source categories',[(n,str(n)+' classes',c) for n,c in zip(range(1,6),['#1a9850','#91cf60','#fee08b','#fc8d59','#d73027'])]),'classes'),
                ('tied_or_dispersed','Tied or dispersed',maps.discrete_legend('No three-model majority',[(0,'Majority','#eeeeee'),(1,'Tied / dispersed','#9e62af')]),'indicator'),
                ('tie_flag','Modal ties',maps.discrete_legend('Equal maximum class frequencies',[(0,'Unique mode','#eeeeee'),(1,'Tied mode','#9e62af')]),'indicator')]
            chart(d,payload,ident+'_agreement',caption+' · model agreement','ha',[dict(label=k,value=v) for k,v in result['summary']['agreement_areas_ha'].items()],
                  'maize_model_units',[l['layer_id'] for l,r in items])
            chart(d,payload,ident+'_pairwise',caption+' · pairwise agreement','%',
                  [dict(label=r['model_a']+' / '+r['model_b'],value=r['agreement_percentage']) for r in result['pairwise']], 'maize_pairwise')
            for management_model in analysis.MODELS:
                chart(d,payload,ident+'_'+management_model.replace('-','_')+'_composition',caption+' · '+management_model+' · common-support classes','ha',
                    [dict(label=r['class_label'],value=r['area_ha'],colour=analysis.CLASS_COLOURS[r['class_code']-1]) for r in result['model_summary'] if r['model']==management_model], 'maize_model_summary')
        else:
            metrics=[]
            for metric,title in [('model_mean','Five-model mean'),('model_median','Five-model median'),('model_minimum','Five-model minimum'),('model_maximum','Five-model maximum'),('model_standard_deviation','Five-model population SD'),('model_iqr','Five-model IQR'),('model_range','Five-model range'),('model_coefficient_of_variation','Five-model coefficient of variation')]:
                vals=[r[metric] for r in result['rows'] if r[metric] is not None]
                if not vals:continue
                unit='ratio' if metric=='model_coefficient_of_variation' else 'Kg (DW)/ha'
                domain=yield_domains[key[3]] if metric in {'model_mean','model_median','model_minimum','model_maximum'} else [0,max(vals)]
                metrics.append((metric,title,maps.continuous_legend(title,unit,domain,'Common-support project metric; read units before comparing'),unit))
            chart(d,payload,ident+'_yield_models',caption+' · five-model yield','Kg (DW)/ha',[dict(label=r['model'],value=r['mean']) for r in result['model_summary']], 'maize_model_summary',[l['layer_id'] for l,r in items])
            chart(d,payload,ident+'_yield_spread',caption+' · five-model spread','Kg (DW)/ha',
                [dict(label=k.replace('model_','').replace('_',' '),value=result['summary']['area_weighted_spatial_summaries'][k]['mean']) for k in ['model_standard_deviation','model_iqr','model_range']], 'maize_five_model_summary')
        for metric,title,legend,unit in metrics:
            produced=maps.derived(payload,ident+'_'+metric,'Project-derived '+title+' · '+caption,result,metric,copy.deepcopy(legend),aoi,cfg['preview_max_dimension'],unit,cfg)
            if produced:layer,record=produced;derived_layers.append(layer);new_maps.append(record)
    # Individual model comparisons: exact pairs, separated by product and management.
    futures=[item for item in readable if item[0]['climate_model_code'] in analysis.MODELS]
    comparisons=[];comparison_units=[];transitions=[];chart_groups=defaultdict(list)
    pairs=[]
    for future in [item for item in readable if item[0]['period_code'].startswith('FP')]:
        l=future[0];historic=next((h for h in history_items if h[0]['map_code']==l['map_code'] and h[0]['management_code']==l['management_code']),None)
        if historic:pairs.append(('historical_future',historic,future))
    for a,b in combinations(futures,2):
        x,y=a[0],b[0]
        if (x['map_code'],x['management_code'],x['climate_model_code'])!=(y['map_code'],y['management_code'],y['climate_model_code']):continue
        if x['period_code']==y['period_code'] and x['ssp_code']!=y['ssp_code']:
            a,b=sorted([a,b],key=lambda p:p[0]['ssp_code']);pairs.append(('cross_ssp',a,b))
        elif x['ssp_code']==y['ssp_code'] and x['period_code']!=y['period_code']:
            a,b=sorted([a,b],key=lambda p:p[0]['period_code']);pairs.append(('cross_period',a,b))
    for index,(kind,a,b) in enumerate(pairs):
        r=analysis.compare([a,b],aoi,kind);ident=f'MZE_COMPARE_{index+1:04d}';ctx=dict(comparison_id=ident,**context(b[0]))
        summary=dict(ctx,**r['summary']);comparisons.append(summary)
        comparison_units.extend(dict(ctx,comparison_kind=kind,layer_a=a[0]['layer_id'],layer_b=b[0]['layer_id'],**row) for row in r['rows'])
        transitions.extend(dict(ctx,comparison_kind=kind,layer_a=a[0]['layer_id'],layer_b=b[0]['layer_id'],**row) for row in summary.get('transitions',[]))
        value=summary.get('agreement_percentage') if b[0]['data_type']=='categorical' else summary['absolute_difference']['mean']
        groupkey=(kind,b[0]['map_code'],b[0]['management_code'],b[0]['climate_model_code'])
        chart_groups[groupkey].append(dict(label=a[0]['period_code']+' '+a[0]['ssp_code']+' → '+b[0]['period_code']+' '+b[0]['ssp_code'],value=value,common_valid_area_ha=r['support']['common_valid_area_ha']))
    for key,rows in chart_groups.items():
        chart(d,payload,group_id(key),' · '.join(key),'% matching classes' if key[1]=='RES05-SIX' else 'Kg (DW)/ha · B minus A',rows,'maize_source_comparisons')
    tables['maize_source_comparisons']=comparisons;tables['maize_comparison_units']=comparison_units;tables['maize_class_transitions']=transitions
    # Matched common support across both complete five-model groups.
    for (ka,ga),(kb,gb) in combinations(sorted(group_results.items()),2):
        if ka[0]!=kb[0] or ka[3]!=kb[3]:continue
        kind='cross_ssp' if ka[1]==kb[1] and ka[2]!=kb[2] else 'cross_period' if ka[2]==kb[2] and ka[1]!=kb[1] else None
        if not kind:continue
        r=analysis.matched_group_comparison(ga,gb,aoi,kind);ctx=dict(group_a=group_id(ka),group_b=group_id(kb),map_code=ka[0],management_code=ka[3])
        tables['maize_derived_comparisons'].append(dict(ctx,**r['summary']))
        tables['maize_derived_comparison_units'].extend(dict(ctx,comparison_kind=kind,**row) for row in r['rows'])
        if ka[0]=='RES05-SIX':
            rows=[dict(label=metric+' '+side,value=r['summary'][metric+'_'+side+'_area_ha']) for metric in ['unanimity','strong_agreement'] for side in ['a','b']];unit='ha'
        else:
            rows=[dict(label=k.replace('model_','').replace('_difference',''),value=v['mean']) for k,v in r['summary']['metric_differences'].items() if 'coefficient' not in k];unit='Kg (DW)/ha · B minus A'
        chart(d,payload,group_id(ka)+'_vs_'+group_id(kb),kind+' · '+group_id(ka)+' → '+group_id(kb),unit,rows,'maize_derived_comparisons')
    for item in readable:
        l=item[0]
        if l['climate_model_code']!='ENSEMBLE':continue
        key=(l['map_code'],l['period_code'],l['ssp_code'],l['management_code'])
        if key not in group_results:continue
        r=analysis.ensemble_diagnostic(group_results[key],item,aoi);ctx=dict(ensemble_layer_id=l['layer_id'],group_id=group_id(key),**context(l))
        tables['maize_ensemble_diagnostics'].append(dict(ctx,**r['summary']))
        tables['maize_ensemble_units'].extend(dict(ctx,**row) for row in r['rows'])
        if l['map_code']=='RES05-SIX':rows=[dict(label='Matches unique mode',value=r['summary']['matching_percentage'])];unit='% of unique-mode comparable area'
        else:rows=[dict(label='ENSEMBLE minus five-model mean',value=r['summary']['ensemble_minus_derived_mean']['mean'])];unit='Kg (DW)/ha'
        chart(d,payload,l['layer_id']+'_diagnostic',l['display_name']+' · ENSEMBLE diagnostic',unit,rows,'maize_ensemble_diagnostics',note=r['summary']['interpretation'])
    tables['maize_five_model_summary']=summaries;tables['maize_group_status']=group_status
    # Dataset-level block only: no invented future SXX layer or empty selector entry.
    blocked=dict(manifest['blocked'],report_generated_at_utc=utcnow())
    add_table(d,payload,'maize_source_inventory',[dict(context(a),layer_id=a['layer_id'],dataset_id=a['dataset_id'],source_url=a['tiff_url'],json_url=a['json_url'],required=a['required'],verification_status=a['verification_status'],output_path=a.get('output_path'),reason=a['reason']) for a in assets]+[blocked])
    add_table(d,payload,'maize_verification',reports)
    add_table(d,payload,'data_inventory',assets+derived_layers,append=True)
    add_table(d,payload,'raster_summary',continuous,append=True);add_table(d,payload,'categorical_summary',categories,append=True)
    add_table(d,payload,'source_cells',cells,append=True)
    limitations=[dict(dataset_id=a['dataset_id'],layer_id=a['layer_id'],limitation_type='maize_source_support',text=a['limitation'],severity='NOTE',display_rule='Map details and methods') for a in assets]
    limitations.append(dict(dataset_id=blocked['dataset_id'],layer_id=None,limitation_type='availability',text=blocked['note'],severity='BLOCKED',display_rule='Dataset inventory only'))
    add_table(d,payload,'source_limitations',limitations,append=True)
    for name,rows in tables.items():add_table(d,payload,name,rows)
    write_json(meta/'supplemental_verification.json',reports);write_json(meta/'five_model_summary.json',summaries)
    write_json(meta/'common_support.json',supports);write_json(meta/'blocked_future_continuous.json',blocked)
    write_json(meta/'processing_history.json',history)
    for addendum in manifest['addenda']:
        subset=[r for r,a in zip(reports,assets) if any(g['stage']==addendum['stage'] for g in a['guide_references'])]
        report=dict(addendum=addendum,run_generated_at_utc=utcnow(),verification_records=subset,
            block=blocked if addendum['stage']=='03.4' else None,current_listing_status=manifest['current_listing_status'],
            note='Earlier partial listing states are retained as audit history; runtime verification is reported separately.')
        write_json(meta/('stage_'+addendum['stage'].replace('.','_')+'_verification.json'),report)
        write_csv(meta/('stage_'+addendum['stage'].replace('.','_')+'_verification.csv'),subset,['layer_id','verification_status'])
    for product in ['RES05-SIX','RES05-YXX']:
        for period in ['FP2140','FP4160','FP6180','FP8100']:
            subset=[r for r in reports if r['map_code']==product and r['period_code']==period]
            write_json(meta/(product+'_'+period+'_verification.json'),subset);write_csv(meta/(product+'_'+period+'_verification.csv'),subset)
    d['maps'].extend(new_maps);d['layers'].extend(assets+derived_layers)
    failed_required=[a['layer_id'] for a in failures if a['required']]
    outcome='INCOMPLETE' if failures else 'COMPLETE_WITH_COVERAGE_GAPS' if empty or failures or any(not g['units'] for g in group_results.values()) else 'COMPLETE'
    extension_summary=dict(outcome=outcome,planned_assets=len(assets),verified_assets=sum(r['verification_status'] in sources.VERIFIED for r in reports),
        available_layers=len(verified),empty_or_outside_layers=len(empty),failed_layers=len(failures),failed_required=failed_required,
        complete_five_model_groups=len(group_results),groups_with_common_support=sum(bool(g['units']) for g in group_results.values()),
        planned_five_model_groups=len(expected),original_required_gaez='16/16',original_sources=48,blocked_future_continuous=blocked['availability_status'],
        source_listing_status=manifest['current_listing_status'],run_id=stamp)
    d['run_id']=stamp;d['maize']=dict(summary=extension_summary,blocked=blocked,yield_domains=yield_domains,
        note='Maize model scenarios are contextual. Agreement and spread are project-derived descriptions, not probability or official FAO confidence.',
        filters=['map_code','period_code','ssp_code','climate_model_code','management_code','view'])
    if outcome=='COMPLETE' and original['summary'].get('gaps'):outcome='COMPLETE_WITH_OPTIONAL_GAPS'
    d['summary']['outcome']=outcome;d['summary']['maize_extension']=extension_summary
    d['methods']['maize_extension']=dict(version='3.23',code_sha256=code_hash(),configuration=cfg,guide_sha256=manifest['guide_sha256'],
        source_listing_vs_verification='254 exact listed objects are not 254 verified AOI outputs until this run passes each source check',
        methods='../metadata/maize/methodology.md',traceability='../metadata/maize/requirements_traceability.md',original_core='../metadata/core_baseline/')
    # All pre-existing download records and paths remain valid.
    additions=[dict(id=t['id'],path=t['path'],title=t['title']) for t in d['tables'] if t['id'] not in {x['id'] for x in original['tables']}]
    additions += [dict(id=m['layer_id'],path=m['download_path'],title=m['title']) for m in new_maps]
    additions += [dict(id=c['id'],path=c['path'],title=c['title']+' PNG') for c in d['charts'][len(original['charts']):]]
    d['downloads'].extend(additions)
    # Stable layer links from every map to its exact relevant table/chart records.
    for m in new_maps:
        m['table_ids']=[t['id'] for t in d['tables'] if m['layer_id'] in t['layer_ids']]
        related={m['layer_id'],m['metadata'].get('original_layer_id')}
        if m['metadata'].get('project_derived'):related.update(m['metadata']['source_id'])
        group=m['metadata'].get('group_id')
        m['chart_ids']=list(dict.fromkeys([c['id'] for c in d['charts'] if group and c['id'].startswith(group+'_')]+[c['id'] for c in d['charts'] if related.intersection(c['layer_ids'])]))
        if m['metadata'].get('project_derived'):
            m['table_ids']+=['maize_model_units','maize_five_model_summary','maize_common_support']
    write_json(meta/'run_summary.json',extension_summary)
    write_json(meta/'layer_catalog.json',assets+derived_layers)
    write_json(meta/'legends.json',{m['layer_id']:m['legend'] for m in new_maps})
    write_json(meta/'provenance.json',dict(aoi_sha256=aoi_hash,code_sha256=code_hash(),guide_sha256=manifest['guide_sha256'],sources=reports,baseline=original['run_id'],methods=d['methods']['maize_extension']))
    write_json(payload/'metadata/run_summary.json',d['summary'])
    write_json(payload/'metadata/layer_catalog.json',d['layers'])
    original_supplemental=json.loads((baseline/'metadata/supplemental_verification.json').read_text())
    write_json(payload/'metadata/supplemental_verification.json',original_supplemental+reports)
    provenance=json.loads((baseline/'metadata/provenance.json').read_text())
    provenance['maize_extension']=dict(provenance_path='maize/provenance.json',aoi_sha256=aoi_hash,code_sha256=code_hash(),source_count=len(reports),guide_sha256=manifest['guide_sha256'])
    write_json(payload/'metadata/provenance.json',provenance)
    completeness_path=payload/'metadata/metadata_completeness.csv'
    from .inputs import read_csv
    completeness=read_csv(completeness_path)
    completeness.extend(dict(layer_id=l['layer_id'],field=k,status='RESOLVED' if l.get(k) is not None else 'NOT_APPLICABLE',reason='Supplemental source dimension or explicitly inapplicable field') for l in assets for k in ['source_id','unit','mask_rule','licence','climate_model_code','ssp_code','period_code','management_code'])
    write_csv(completeness_path,completeness)
    schemas=json.loads((baseline/'metadata/table_schemas.json').read_text())
    schemas['maize_extension_version']='3.23';schemas['fields'].update({t['id']:t['columns'] for t in d['tables']})
    schemas['maize_status_enums']=sorted(sources.VERIFIED|{'FAILED_REMOTE_ACCESS','FAILED_METADATA_VALIDATION','FAILED_RANGE_VALIDATION','FAILED_CLIP_VALIDATION','BLOCKED_BY_PUBLIC_SOURCE_AVAILABILITY'})
    write_json(payload/'metadata/table_schemas.json',schemas)
    old_legends=json.loads((baseline/'metadata/legends.json').read_text());old_legends.update({m['layer_id']:m['legend'] for m in new_maps});write_json(payload/'metadata/legends.json',old_legends)
    write_dashboard(payload/'dashboard/parcel_a_data_inventory.html',d,cfg['max_dashboard_bytes'])
    output_manifest={k:v for k,v in d.items() if k not in {'maps','tables'}}
    output_manifest['maps']=[{k:v for k,v in m.items() if k not in {'image','cells'}} for m in d['maps']]
    output_manifest['tables']=[{k:v for k,v in t.items() if k!='rows'} for t in d['tables']]
    write_json(payload/'metadata/dashboard_manifest.json',output_manifest)
    original_checks=json.loads((baseline/'metadata/package_checksums.json').read_text())
    preserved=all(sha256(payload/'metadata/core_baseline'/name)==digest for name,digest in original_checks.items())
    unchanged_original_assets=all(sha256(payload/name)==digest for name,digest in original_checks.items() if name.startswith(('maps/','charts/','clipped_data/','dashboard/assets/')))
    missing=[item['path'] for item in d['downloads'] if not (payload/'dashboard'/item['path']).is_file()]
    checks=dict(original_package_preserved=preserved,original_maps_charts_native_data_unchanged=unchanged_original_assets,
        original_48_sources_retained=len(next(t for t in d['tables'] if t['id']=='source_inventory')['rows'])==48,
        original_16_required_gaez_retained=d['summary']['gaez_extracted']==16,unique_layer_ids=len({m['layer_id'] for m in d['maps']})==len(d['maps']),
        all_downloads_exist=not missing,no_future_sxx_layers=not any(l.get('map_code')=='RES05-SXX30AS' and l.get('period_code','').startswith('FP') for l in d['layers']),
        required_supplemental_sources_verified=not failed_required,all_supplemental_checks_successful=not failures,all_254_assets_accounted_for=len(reports)==254,
        common_support_closure=all(abs(s['common_valid_area_ha']+s['excluded_area_ha']-s['aoi_area_ha'])<=s['aoi_area_ha']*.0001 for s in supports))
    if not all(checks.values()):
        outcome='INCOMPLETE';extension_summary['outcome']=outcome;d['summary']['outcome']=outcome
        write_json(meta/'run_summary.json',extension_summary);write_json(payload/'metadata/run_summary.json',d['summary'])
        write_dashboard(payload/'dashboard/parcel_a_data_inventory.html',d,cfg['max_dashboard_bytes'])
        output_manifest['summary']=d['summary'];write_json(payload/'metadata/dashboard_manifest.json',output_manifest)
    write_json(payload/'qa/maize_validation_report.json',dict(outcome=outcome,checks=checks,missing_paths=missing,group_status=group_status,
        limitations=['Future 1 km continuous suitability remains blocked by supplied source-availability evidence.','Crop Water Indicators need a separate metadata review.','Coarse-cell results are descriptive model scenarios, not parcel forecasts.']))
    write_json(payload/'qa/stage03_validation_report.json',dict(outcome=outcome,checks=checks,core_report='metadata/core_baseline/qa/stage03_validation_report.json'))
    (payload/'README.txt').write_text('Parcel A — Stage 03 with maize scenarios\n\nExtract this ZIP and open dashboard/parcel_a_data_inventory.html.\nMaps, tables and charts work offline. Background tiles need internet.\nThe accepted Stage 03 package is preserved in metadata/core_baseline/.\nNew maize evidence and methods: metadata/maize/. Native outputs: clipped_data/.\nOriginal required GAEZ layers: 16/16. Original sources: 48. Supplemental rasters planned: 254.\nStatus: '+outcome+'\n',encoding='utf-8')
    (payload/'logs/maize_extension.log').write_text('\n'.join(json.dumps(clean(row)) for row in history)+'\n')
    excluded={'qa/stage03_output_manifest.json','metadata/package_checksums.json'}
    files=[p for p in sorted(payload.rglob('*')) if p.is_file() and p.relative_to(payload).as_posix() not in excluded]
    total=sum(p.stat().st_size for p in files)
    if total>cfg['max_working_bytes']:raise ValueError('Stage 03 output exceeds the configured portable-package budget')
    write_json(payload/'qa/stage03_output_manifest.json',[dict(path=p.relative_to(payload).as_posix(),size=p.stat().st_size,sha256=sha256(p),exists=True,validation='PRESENT_AND_HASHED') for p in files])
    files.append(payload/'qa/stage03_output_manifest.json');write_json(payload/'metadata/package_checksums.json',{p.relative_to(payload).as_posix():sha256(p) for p in files})
    files.append(payload/'metadata/package_checksums.json');archive=run_dir/('stage03_maize_inventory_package.zip' if outcome!='INCOMPLETE' else 'stage03_maize_diagnostics.zip')
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for path in sorted(files):z.write(path,path.relative_to(payload))
    return dict(outcome=outcome,archive=str(archive),dashboard=str(payload/'dashboard/parcel_a_data_inventory.html'),summary=d['summary'])
