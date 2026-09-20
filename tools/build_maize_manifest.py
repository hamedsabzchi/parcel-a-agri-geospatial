#!/usr/bin/env python3
"""Register exact objects supplied in the approved 03.1–03.23 guide.

This builds an inventory, not an assertion that any remote raster was processed.
Stage 02's pinned registry and manifest are deliberately untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
GUIDE=ROOT/'docs/source_guides/stage03_maize_03_1_to_03_23.txt'
BASE='https://storage.googleapis.com/fao-gismgr-gaez-v5-data/DATA/GAEZ-V5/MAPSET/'
MODELS=['GFDL-ESM4','IPSL-CM6A-LR','MPI-ESM1-2-HR','MRI-ESM2-0','UKESM1-0-LL']
PERIODS={'HP0120':[2001,2020],'FP2140':[2021,2040],'FP4160':[2041,2060],'FP6180':[2061,2080],'FP8100':[2081,2100]}
SSPS={'HIST':'Historical','SSP126':'SSP1-2.6','SSP370':'SSP3-7.0','SSP585':'SSP5-8.5'}
MANAGEMENT={'HRLM':'Rainfed high-input','LRLM':'Rainfed low-input','HILM':'Irrigated high-input','LILM':'Irrigated low-input'}
NAME=r'GAEZ-V5\.(RES05-[A-Z0-9]+)\.(HP0120|FP2140|FP4160|FP6180|FP8100)\.([A-Z0-9-]+)\.(HIST|SSP126|SSP370|SSP585)\.MZE\.(HRLM|HILM|LRLM|LILM)\.(tif|json)'


def build():
    text=GUIDE.read_text();lines=text.splitlines()
    starts=list(re.finditer(r'^STAGE 03\.(\d+) (?:IMPLEMENTATION GUIDE|ADDENDUM)$',text,re.M))
    sections=[];references={};evidence={};supplied_urls={}
    for index,start in enumerate(starts):
        stage=int(start.group(1));end=starts[index+1].start() if index+1<len(starts) else len(text)
        body=text[start.start():end];first=text[:start.start()].count('\n')+1
        names=sorted(set(m.group(0) for m in re.finditer(NAME,body)))
        statuses=list(dict.fromkeys(re.findall(r'^([A-Z][A-Z0-9_]{15,})\s*$',body,re.M)))
        sections.append(dict(stage=f'03.{stage}',title=body.splitlines()[1],guide_line=first,
            source_list_status_history=statuses,evidence_role='User-supplied official bucket-list transcript; not live verification',
            exact_named_tiffs=sum(n.endswith('.tif') for n in names),current_status_superseded=stage in {5,9,21}))
        urls=re.findall(r'https://storage\.googleapis\.com/[^\s]+\.(?:tif|json)',body)
        for url in urls:
            name=url.rsplit('/',1)[-1]
            if re.fullmatch(NAME,name):
                supplied_urls[name]=url
                references.setdefault(name,[]).append(dict(stage=f'03.{stage}',line=first+body[:body.index(url)].count('\n')))
        # Stage 03.2 explicitly authorizes resolving four exact ENSEMBLE names
        # against its official bucket folder; all other URLs are supplied verbatim.
        if stage==2:
            for name in names:
                supplied_urls.setdefault(name,BASE+'RES05-SIX/'+name)
                references.setdefault(name,[]).append(dict(stage='03.2',line=first+body[:body.index(name)].count('\n'),url_resolution='Official bucket plus exact supplied name'))
        if stage in {1,2,3}:
            product={1:'RES05-SXX30AS',2:'RES05-SIX',3:'RES05-YXX'}[stage]
            links=re.findall(r'https://[^\s]+',body)
            references[product]=dict(metadata_url=next(u for u in links if '/catalog/iso/' in u),
                readme_url=next(u for u in links if u.endswith('.xlsx')),
                dimensions_json_url=next(u for u in links if '/catalog/dataset/' in u and u.endswith('.json')),
                sld_url=next(u for u in links if u.endswith('/sld')))
        if not names:continue
        matches=[re.fullmatch(NAME,n) for n in names]
        products={m[1] for m in matches};periods={m[2] for m in matches};scenarios={m[4] for m in matches}
        product=next(iter(products)) if len(products)==1 else None
        period=next(iter(periods)) if len(periods)==1 else None
        ssp=next(iter(scenarios)) if len(scenarios)==1 else None
        model='ENSEMBLE' if stage in {2,3} else None
        in_evidence=False
        for offset,line in enumerate(body.splitlines()):
            if 'BUCKET-LIST EVIDENCE' in line or 'CONFIRMED OBJECT EVIDENCE' in line:in_evidence=True;continue
            if not in_evidence:continue
            if re.fullmatch(r'SSP(?:126|370|585):',line.strip()):ssp=line.strip()[:-1]
            if line.strip().rstrip(':') in MODELS:model=line.strip().rstrip(':')
            match=re.match(r'- (?:(SSP\d+) )?(HRLM|HILM|LRLM|LILM) (JSON|TIFF): (.+)',line)
            if not match or not product or not period or not model:continue
            scenario=match[1] or ssp
            if not scenario:continue
            suffix='json' if match[3]=='JSON' else 'tif'
            name=f'GAEZ-V5.{product}.{period}.{model}.{scenario}.MZE.{match[2]}.{suffix}'
            if name in supplied_urls:
                detail=match[4]
                evidence.setdefault(name,[]).append(dict(stage=f'03.{stage}',guide_line=first+offset,
                    displayed_size=detail.split(';')[0],mime_type='application/json' if suffix=='json' else 'image/tiff',
                    timestamp_evidence=detail,not_an_observation_date=True))
    assets=[]
    for name,url in sorted(supplied_urls.items()):
        if not name.endswith('.tif'):continue
        m=re.fullmatch(NAME,name);product,period,model,ssp,management=m.groups()[:5]
        sidecar=name[:-4]+'.json'
        if sidecar not in supplied_urls:raise ValueError('Missing exact supplied sidecar: '+name)
        future=period.startswith('FP');categorical=product=='RES05-SIX';sxx=product=='RES05-SXX30AS'
        key='GAEZ_V5_'+product.replace('-','_')+'__'+(management if sxx else '__'.join([period,model.replace('-','_'),ssp,'MZE',management]))
        caption='Continuous maize suitability index' if sxx else 'Maize suitability class' if categorical else 'Maize attainable yield'
        dates=PERIODS[period];unit='Index' if sxx else 'Class' if categorical else 'Kg (DW)/ha'
        note=('Source cells are contextual model outputs, not field measurements. '
              'RES05-SXX30AS (~1 km) and RES05-SIX (~10 km) are complementary products, with no inferred class conversion.' if sxx else
              'Approximately 10 km source cells are contextual model outputs, not parcel forecasts. '+
              ('Class codes are categorical labels.' if categorical else 'Source-defined yield of the best occurring suitability class; not observed parcel yield or production.'))
        if sxx and management in {'HILM','LILM'}:
            note+=' Irrigated results are limited by the GAEZ 2020 existing-cropland mask. Missing or limited coverage does not demonstrate that irrigation development is infeasible.'
        if model=='ENSEMBLE':note+=' ENSEMBLE is the source label; its aggregation method is not inferred.'
        assets.append(dict(layer_id=key,asset_key=key,dataset_id='GAEZ_V5_'+product.replace('-','_')+('_FUTURE_MAIZE' if future else ''),
            map_code=product,crop='Maize',crop_code='MZE',period_code=period,period=f'{dates[0]}-{dates[1]}',
            period_start=f'{dates[0]}-01-01',period_end=f'{dates[1]}-12-31',climate_model_code=model,climate_source=model,
            ssp_code=ssp,ssp_caption=SSPS[ssp],climate_scenario=ssp,management_code=management,management_caption=MANAGEMENT[management],
            display_name=f'{caption} · {MANAGEMENT[management]} · {dates[0]}-{dates[1]}'+(f' · {ssp} · {model}' if future else ''),
            theme='Historical continuous maize suitability (~1 km)' if sxx else 'Future maize suitability classes' if categorical else 'Future maize attainable yield',
            variable=caption,data_type='categorical' if categorical else 'continuous',unit=unit,source_unit=unit,decoded_unit=unit,
            scale=1.,offset=0.,scale_already_applied=False,nodata=0 if categorical else -9,valid_range=[1,9] if categorical else [0,10000] if sxx else [0,None],
            expected_resolution_degrees=1/120 if sxx else 1/12,expected_crs='EPSG:4326',expected_dtype='uint8' if categorical else 'int16' if sxx else 'float32',
            expected_width=43200 if sxx else 4320,expected_height=21600 if sxx else 2160,
            source_id=url,source_url=url,tiff_url=url,json_url=supplied_urls[sidecar],object_name=name,json_object_name=sidecar,
            source_version='GAEZ v5',provider='FAO and IIASA',licence='CC-BY-4.0',attribution='FAO / IIASA · GAEZ v5 · CC-BY-4.0',
            mask_rule='Source validity mask AND documented NoData exclusion; valid zero retained for continuous products',
            processing='Bounded HTTP-range read; native-grid clip; fractional native-cell area weighting',
            adapter='gaez_supplemental',required=not(sxx and management in {'HILM','LILM'}),supplemental=True,
            conditional_cropland_mask=sxx and management in {'HILM','LILM'},limitation=note,
            listing_status='SUPPLIED_OBJECT_LISTING',verification_status='NOT_YET_VERIFIED',extraction_status='PENDING',
            stage03_disposition='SUPPLEMENTAL_SELECTED',stage02_status='SUPPLEMENTAL_NOT_IN_STAGE02',
            guide_references=references[name],listing_evidence=evidence.get(name,[]),json_listing_evidence=evidence.get(sidecar,[]),
            official_resources=references[product],**references[product]))
    counts={p:sum(a['map_code']==p for a in assets) for p in ['RES05-SXX30AS','RES05-SIX','RES05-YXX']}
    if counts!={'RES05-SXX30AS':4,'RES05-SIX':124,'RES05-YXX':126}:raise ValueError(f'Unexpected exact source inventory: {counts}')
    return dict(schema_version='3.23',guide_sha256=hashlib.sha256(GUIDE.read_bytes()).hexdigest(),
        guide_path=GUIDE.relative_to(ROOT).as_posix(),baseline_git_commit='ef2d47c1c0dc039f389540d8a2c33af773b1ea11',
        models=MODELS,periods=PERIODS,ssps=SSPS,managements=MANAGEMENT,analytical_asset_count=len(assets),sidecar_count=len(assets),
        original_required_gaez_count=16,original_stage02_source_count=48,
        current_listing_status='MAIZE_GAEZ_SUITABILITY_AND_ATTAINABLE_YIELD_BUCKET_LIST_INVENTORY_COMPLETE_WITH_FUTURE_SXX30AS_TRANSPARENTLY_BLOCKED',
        processing_status='NOT_YET_EXECUTED',assets=assets,addenda=sections,
        audit_events=[dict(stage='03.5',event='Two-model SIX FP2140 SSP126 listing',superseded_by='03.6'),
            dict(stage='03.9',event='Four-model SIX FP4160 SSP126 listing; repeated GFDL listing deduplicated',superseded_by='03.10'),
            dict(stage='03.10',event='Exact MRI-ESM2-0 objects resolve SIX FP4160 SSP126 listing gap'),
            dict(stage='03.21',event='YXX FP6180 SSP126 IPSL-CM6A-LR and MPI-ESM1-2-HR listings pending',superseded_by='03.23'),
            dict(stage='03.23',event='Eight exact objects resolve both YXX FP6180 SSP126 listing gaps'),
            dict(stage='03.21/03.22',event='Narrative counts 13/15 conflict with 26/30 exact TIFF names; current counts use distinct exact objects, as confirmed in 03.23')],
        blocked=dict(dataset_id='GAEZ_V5_RES05_SXX30AS_FUTURE_MAIZE',map_code='RES05-SXX30AS',
            availability_status='BLOCKED_BY_PUBLIC_SOURCE_AVAILABILITY',verified_analytical_count=0,verified_json_count=0,
            evidence_source='Approved guide 03.4; supplied observation date unspecified',recorded_at_utc=None,
            tested_prefixes=['GAEZ-V5.RES05-SXX30AS.FP2140.ENSEMBLE.SSP126.MZE.','GAEZ-V5.RES05-SXX30AS.FP2140'],
            observed_results=['NO_ROWS_RETURNED','NO_ROWS_RETURNED'],substitution_allowed=False,retry_required=True,
            note='Source-availability block from supplied evidence, not a fresh bucket search. No future raster URLs or values inferred.',
            official_resources=references['RES05-SXX30AS']),
        deferred=[dict(product='Crop Water Indicators',status='DEDICATED_METADATA_REVIEW_REQUIRED')])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    value=json.dumps(build(),indent=2,ensure_ascii=False)+'\n';path=ROOT/'config/stage03/maize_sources.json'
    if args.check:
        if path.read_text()!=value:raise SystemExit('Maize manifest is stale')
    else:path.write_text(value,encoding='utf-8')
    print('254 exact supplemental rasters and sidecars; original 16/48 contracts preserved.')


if __name__=='__main__':main()
