"""Resolve and cross-check authoritative contained evidence, never filenames as values."""
from collections import defaultdict
import json
import re
from pathlib import Path
import numpy as np
from shapely.geometry import shape
from shapely.ops import transform,unary_union
from pyproj import Transformer
from .common import relative,csv_read,unique,number,close,sha
from .analysis import MODELS,PERIODS,SSPS,MANAGEMENT,summarize

FILES=dict(layers='metadata/layer_catalog.json',verification='metadata/maize/supplemental_verification.json',
    groups='metadata/maize/five_model_summary.json',units='tables/maize_model_units.csv',support='tables/maize_common_support.csv',
    cells='tables/source_cells.csv',legends='metadata/legends.json',aoi='clipped_data/vectors/parcel_a.geojson',qa='qa/maize_validation_report.json')


def decode(row):
    out={}
    for k,v in row.items():
        if v=='':out[k]=None;continue
        if v in ('True','False'):out[k]=v=='True';continue
        try:out[k]=json.loads(v) if isinstance(v,str) else v
        except (ValueError,TypeError):out[k]=v.strip() if isinstance(v,str) else v
    return out


def embedded(root):
    html=relative(root,'dashboard/parcel_a_data_inventory.html').read_text()
    m=re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>',html,re.S)
    if not m:raise ValueError('Unsupported Stage 03 dashboard: authoritative embedded data not found')
    return json.loads(m[1])


def index_evidence(rows,key):
    """Ambiguous keys are unavailable, without discarding unrelated scenarios."""
    out={};duplicates=set()
    for row in rows:
        k=key(row)
        if k in out:duplicates.add(k)
        out[k]=row
    for k in duplicates:out.pop(k,None)
    return out,duplicates


def resolve(root):
    root=Path(root);d=embedded(root);contract=[];gaps=[];conflicts=[];loaded={}
    for field,path in FILES.items():
        try:
            p=relative(root,path);loaded[field]=[decode(r) for r in csv_read(p)] if p.suffix=='.csv' else json.loads(p.read_text())
            state='RESOLVED'
        except (ValueError,OSError):loaded[field]=None;state='Not available: source not present';gaps.append(dict(field=field,reason=state,source=path))
        contract.append(dict(requested_field=field,source_file=path,selected_property='See per-product field mappings',unit='Source-defined',
            denominator='Product-specific common valid area when applicable',join_keys='group_id; layer_id; unit_id; source_cell_ids',
            validation_rule='Input checksum; unique keys; exact five models; consistency checks',fallback='Disable the affected product; no substitute values',status=state))
    if not loaded['aoi']:raise ValueError('Stage 03 AOI geometry is required')
    aoi=shape(loaded['aoi']['features'][0]['geometry']);project=Transformer.from_crs(4326,6933,always_xy=True).transform
    aoi_area=number(d['summary']['aoi_area_ha'])
    if not close(transform(project,aoi.segmentize(.0005)).area/1e4,aoi_area,rel=.0001):raise ValueError('AOI area conflicts with the Stage 03 geometry')
    # Input Stage 03 QA is authoritative, including unknown/failed flags.
    qa=loaded['qa'];critical=[]
    if qa:
        for k,passed in qa.get('checks',{}).items():
            if not passed and k not in {'required_supplemental_sources_verified','all_supplemental_checks_successful'}:critical.append(k)
    if critical:gaps.append(dict(field='stage03_qa',reason='Blocked by Stage 03 quality flag: '+', '.join(critical)))
    if not qa:gaps.append(dict(field='stage03_qa',reason='Not verified: source present but verification incomplete'))
    layers,dup_layers=index_evidence(loaded['layers'] or [],lambda x:x['layer_id'])
    verification,dup_verification=index_evidence(loaded['verification'] or [],lambda x:x['layer_id'])
    supports,dup_supports=index_evidence(loaded['support'] or [],lambda x:x['group_id'])
    cells,dup_cells=index_evidence(loaded['cells'] or [],lambda x:(x['layer_id'],x['cell_id']))
    for label,keys in [('layers',dup_layers),('verification',dup_verification),('support',dup_supports),('cells',dup_cells)]:
        for key in sorted(keys):conflicts.append(dict(field=label,key=key,status='SOURCE_CONFLICT',reason='Duplicate source key; affected products disabled'))
    unit_groups=defaultdict(list)
    for r in loaded['units'] or []:unit_groups[r['group_id']].append(r)
    embedded_units={};dup_embedded=set()
    for table in d.get('tables',[]):
        if table['id']=='maize_model_units':embedded_units,dup_embedded=index_evidence(table['rows'],lambda x:(x['group_id'],x['unit_id']))
    scenarios={};resolved_groups=[];seen=set();ambiguous_products=set()
    for group in loaded['groups'] or []:
        gid=group['group_id'];product=group.get('map_code')
        if product not in {'RES05-SIX','RES05-YXX'}:continue
        try:
            if gid in seen:raise ValueError('Duplicate group_id')
            seen.add(gid)
            if gid in dup_supports or any(g==gid for g,u in dup_embedded):raise ValueError('Duplicate support or embedded analytical key')
            if critical or not qa:raise ValueError('Blocked by Stage 03 quality flag')
            if group.get('model_count')!=5 or set(group.get('model_set',[]))!=set(MODELS):raise ValueError('Five distinct expected models not verified')
            source=[layers[x] for x in group['layer_ids']]
            if len(source)!=5 or [l['climate_model_code'] for l in source]!=list(MODELS):raise ValueError('Model order or membership conflicts with common-support records')
            dims={(l['crop_code'].strip(),l['period_code'].strip(),l['ssp_code'].strip(),l['management_code'].strip()) for l in source}
            if len(dims)!=1:raise ValueError('Source dimension join mismatch')
            crop,period,ssp,management=next(iter(dims))
            if period not in PERIODS or ssp not in SSPS or management not in MANAGEMENT:raise ValueError('Unsupported documented scenario code')
            if any(group[k]!=v for k,v in [('period_code',period),('ssp_code',ssp),('management_code',management)]):raise ValueError('Group and source dimensions conflict')
            categorical=product=='RES05-SIX';crosswalk={};legend_source=None
            # This adapter implements the accepted Stage 03 mean-positive rule.
            # A later source-defined alternative must be resolved explicitly, never ignored.
            for record in [group,*source]:
                for field in ['positive_yield_rule','positive_yield_definition','positive_rule']:
                    if record.get(field) and record[field] not in {'model_mean > 0','five_model_mean > 0'}:
                        raise ValueError('Source positive-yield criterion needs a documented adapter: '+field)
            for l in source:
                v=verification.get(l['layer_id'],{})
                if l.get('verification_status') not in {'VERIFIED_INSIDE_AOI','VERIFIED_BUT_EMPTY_INSIDE_AOI'} or v.get('verification_status')!=l.get('verification_status'):raise ValueError('Not verified: source verification incomplete or conflicting')
                if l['map_code']!=product or number(l['scale'])!=1 or number(l['offset'])!=0 or number(l['nodata'])!=(0 if categorical else -9):raise ValueError('Product, scale, offset or NoData contract conflict')
                accepted={'class'} if categorical else {'kg (dw)/ha','kg dry weight/ha'}
                if l['unit'].strip().lower() not in accepted:raise ValueError('Source unit contract conflict')
                path=relative(root,l['output_path'])
                if v.get('clip_sha256')!=sha(path):raise ValueError('Source verification clip checksum mismatch')
                if not l.get('mask_rule'):raise ValueError('Source mask rule is missing')
                if categorical:
                    legend=(loaded['legends'] or {}).get(l['layer_id'],{})
                    entries={int(e['code']):{'caption':e['caption'],'colour':e['colour']} for e in legend.get('entries',[])}
                    if not entries or (crosswalk and entries!=crosswalk):raise ValueError('Source class crosswalk conflict')
                    crosswalk=entries;legend_source=FILES['legends']+'#'+l['layer_id']
            support=supports[gid]
            for k in ['common_valid_area_ha','aoi_area_ha','excluded_masked_area_ha','excluded_outside_footprint_area_ha','analytical_unit_count']:
                if not close(support[k],group[k]):raise ValueError('Authoritative common-support sources conflict: '+k)
            if not close(group['aoi_area_ha'],aoi_area,rel=.0001):raise ValueError('AOI denominator conflict')
            common=number(group['common_valid_area_ha'])
            if abs(common+number(group['excluded_masked_area_ha'])+number(group['excluded_outside_footprint_area_ha'])-aoi_area)>aoi_area*.0001:raise ValueError('Support exclusion area closure failed')
            rows=list(unique(unit_groups[gid],lambda x:x['unit_id']).values())
            if len(rows)!=int(group['analytical_unit_count']):raise ValueError('Common-support unit count conflict')
            # Pick a complete-support diagnostic geometry: modal_count or model_mean.
            view='modal_count' if categorical else 'model_mean'
            candidates=[l for l in layers.values() if l.get('group_id')==gid and l.get('view')==view and l.get('analytical_geometry_path')]
            geometries={};geometry_path=None
            if rows:
                if len(candidates)!=1:raise ValueError('Not available: exact native-unit geometry not uniquely resolved')
                geometry_path=candidates[0]['analytical_geometry_path']
                geo=json.loads(relative(root,geometry_path).read_text());geometries=unique(geo['features'],lambda f:f['properties']['cell_id'])
                if set(geometries)!={r['unit_id'] for r in rows}:raise ValueError('Geometry and analytical-unit membership conflict')
            units=[];unit_geometries=[]
            for row in rows:
                values=row['model_values'];ids=row['source_cell_ids']
                if len(ids)!=5 or set(values)!=set(MODELS):raise ValueError('Common support does not contain five model values')
                embedded_row=embedded_units.get((gid,row['unit_id']))
                if embedded_row is not None and (embedded_row.get('model_values')!=values or not close(embedded_row['area_ha'],row['area_ha'])):raise ValueError('Embedded dashboard and authoritative analytical table conflict')
                for l,cell_id in zip(source,ids):
                    if (l['layer_id'],cell_id) in dup_cells:raise ValueError('Duplicate native source-cell key')
                    c=cells[(l['layer_id'],cell_id)]
                    if c['valid'] is not True or c['value'] is None or not close(c['value'],values[l['climate_model_code']]):raise ValueError('Source cell validity or native value conflicts with model unit')
                    if number(row['area_ha'])>number(c['intersection_area_ha'])+aoi_area*.0001:raise ValueError('Common unit exceeds source-cell intersection area')
                feature=geometries[row['unit_id']];props=feature['properties'];geom=shape(feature['geometry'])
                if props['model_values']!=values or not close(props['intersection_area_ha'],row['area_ha']):raise ValueError('Geometry properties and analytical table conflict')
                if not geom.is_valid or not close(transform(project,geom).area/1e4,row['area_ha'],rel=.0001):raise ValueError('Native geometry area conflict')
                if transform(project,geom.difference(aoi)).area/1e4>aoi_area*.0001:raise ValueError('Analytical unit lies outside AOI')
                unit_geometries.append(geom)
                units.append(dict(unit_id=row['unit_id'],area_ha=number(row['area_ha']),model_values=values,source_cell_ids=ids,geometry=feature['geometry']))
            if unit_geometries and abs(sum(g.area for g in unit_geometries)-unary_union(unit_geometries).area)>aoi.area*.0001:raise ValueError('Overlapping analytical units')
            summary=summarize(units,common,aoi_area,categorical,crosswalk)
            for u,row in zip(units,rows):
                for k,expected in u['metrics'].items():
                    if k in row and k not in {'zero_model_count','positive_yield','valid_zero_yield'}:
                        actual=row[k]
                        if isinstance(expected,(dict,list)):
                            if actual!=expected:raise ValueError('Stage 03 diagnostic conflicts with five-model values: '+k)
                        elif expected is None:
                            if actual is not None:raise ValueError('Undefined metric was stored as a number: '+k)
                        elif not close(actual,expected):raise ValueError('Stage 03 diagnostic conflicts with five-model values: '+k)
            if categorical:
                for code,area in summary.get('modal_area_by_class',{}).items():
                    if not close(group['modal_class_area_ha'][str(code)],area):raise ValueError('Stage 03 modal area summary conflict')
                totals=group.get('agreement_areas_ha',{})
                for label,metric in [('5/5 unanimous','full_agreement_area_ha'),('3/5 majority','majority_agreement_area_ha'),('Tied / dispersed','tied_or_dispersed_area_ha')]:
                    if common and not close(totals[label],summary[metric]):raise ValueError('Stage 03 agreement summary conflict')
            elif common:
                aggregates=group.get('area_weighted_spatial_summaries',{})
                for metric,field in [('model_mean','whole_aoi_mean'),('model_standard_deviation','population_sd'),('model_iqr','iqr'),('model_range','model_range'),('model_coefficient_of_variation','inter_model_cv')]:
                    previous=aggregates.get(metric,{}).get('mean');current=summary[field]
                    if (previous is None)!=(current is None) or (previous is not None and not close(previous,current)):raise ValueError('Stage 03 yield aggregate conflict: '+metric)
            flags=list(dict.fromkeys([group['quality_flag'],*(l.get('quality_flag','') for l in source)]));flags=[f for f in flags if f]
            allowed={'OK','FEW_NATIVE_CELLS','NO_VALID_DATA','NO_COMMON_VALID_SUPPORT'}
            if any(f not in allowed for f in flags):raise ValueError('Blocked by Stage 03 quality flag: '+', '.join(flags))
            summary.update(source_quality_flags=flags,quality_flag='ZERO_COMMON_VALID_AREA' if not common else 'FEW_NATIVE_CELLS' if 'FEW_NATIVE_CELLS' in flags else 'PARTIAL_COMMON_SUPPORT' if common<aoi_area*(1-.0001) else 'COMPLETE_VERIFIED',
                excluded_masked_area_ha=group['excluded_masked_area_ha'],excluded_outside_footprint_area_ha=group['excluded_outside_footprint_area_ha'],
                native_cell_counts=group['native_cell_counts'],source_limits=list(dict.fromkeys(l['limitation'] for l in source)),
                source_native_resolution=source[0]['native_resolution'],geometry_source=geometry_path,source_table=FILES['units'],group_id=gid,model_count=len(source),
                source_layers=[l['layer_id'] for l in source],source_downloads=[l['output_path'] for l in source],
                stage03_common_support_source=FILES['support'],class_crosswalk_source=legend_source)
            key='__'.join([crop,period,ssp,management]);kind='suitability' if categorical else 'yield'
            record=scenarios.setdefault(key,dict(key=key,crop_code=crop,crop_label=source[0].get('crop',crop),period_code=period,period_label=PERIODS[period],
                ssp_code=ssp,ssp_label=SSPS[ssp],management_code=management,management_label=MANAGEMENT[management],aoi_area_ha=aoi_area,products={}))
            if (key,kind) in ambiguous_products:raise ValueError('Duplicate scenario/product')
            if kind in record['products']:
                del record['products'][kind];ambiguous_products.add((key,kind))
                raise ValueError('Duplicate scenario/product')
            record['products'][kind]=dict(summary=summary,units=units,crosswalk=crosswalk)
            resolved_groups.append(gid)
            mappings={'model_values':'Source-documented class' if categorical else 'kg dry weight/ha','area_ha':'ha','common_valid_area_ha':'ha','source_cell_ids':'native identifiers','quality_flag':'Stage 03 flags','period_code':'20-year period','ssp_code':'SSP','management_code':'source-defined regime','crop_code':'crop','model_set':'five distinct GCMs','scale':'1','offset':'0','nodata':'0' if categorical else '-9','mask_rule':'source mask AND NoData','geometry':'EPSG:4326 native support','licence':'source licence','verification_status':'Stage 03 status','class_crosswalk':'source code-caption-colour' if categorical else 'not applicable'}
            for field,unit in mappings.items():
                origin=FILES['units'] if field in {'model_values','area_ha','source_cell_ids'} else FILES['support'] if field in {'common_valid_area_ha','quality_flag'} else geometry_path if field=='geometry' else FILES['legends'] if field=='class_crosswalk' else FILES['layers']
                contract.append(dict(requested_field=kind+'.'+field,scenario_key=key,group_id=gid,source_file=origin,selected_property=field,unit=unit,
                    denominator='Product-specific common valid area; CV uses only area where mean > 0',join_keys=['group_id','unit_id','layer_id','source_cell_ids'],
                    validation_rule='Five model membership, decoding, native-cell values, geometry, support and duplicate checks',fallback='Disable affected product on conflict',status='RESOLVED'))
        except (ValueError,KeyError,TypeError) as error:
            reason=str(error);conflicts.append(dict(group_id=gid,product=product,status='SOURCE_CONFLICT' if 'conflict' in reason.lower() or 'Duplicate' in reason else 'MISSING_REQUIRED_METRIC',reason=reason))
            contract.append(dict(requested_field=product,group_id=gid,source_file=FILES['groups'],status='DISABLED',warning=reason,fallback='No values or maps displayed'))
            # A late duplicate must disable the earlier instance too.
            for record in scenarios.values():
                for kind in list(record['products']):
                    if record['products'][kind]['summary']['group_id']==gid:del record['products'][kind]
    records=[r for r in scenarios.values() if r['products']]
    for r in records:
        r['missing_products']=[k for k in ['suitability','yield'] if k not in r['products']]
        for k in r['missing_products']:gaps.append(dict(scenario_key=r['key'],field=k,reason='Not available or not verified; see source contract'))
    records.sort(key=lambda r:(r['crop_code'],r['period_code'],r['ssp_code'],r['management_code']))
    blocked_path=root/'metadata/maize/blocked_future_continuous.json'
    blocked=json.loads(blocked_path.read_text()) if blocked_path.is_file() else None
    return dict(scenarios=records,contract=contract,gaps=gaps,conflicts=conflicts,aoi=loaded['aoi'],aoi_area_ha=aoi_area,
        bounds=d['bounds'],blocked=blocked,stage03_summary=d['summary'],method='Stage 03 fractional native-unit areas in EPSG:6933',
        discovery_inventory={k:v for k,v in FILES.items()},resolved_groups=resolved_groups)
