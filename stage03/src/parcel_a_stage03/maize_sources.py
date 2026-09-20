"""Exact supplemental GAEZ objects, bounded range reads, and reusable verified clips."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit
import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds
import requests
import yaml
from .common import sha256, write_json, utcnow, clean
from .spatial import area_weights, project_geometry, read_raster

VERIFIED={'VERIFIED_INSIDE_AOI','VERIFIED_BUT_EMPTY_INSIDE_AOI','NO_COVERAGE'}
ALGORITHM_VERSION='maize-native-1'


class VerificationError(ValueError):
    def __init__(self,status,message):super().__init__(message);self.status=status


def configuration(project):
    root=Path(project)
    config=yaml.safe_load((root/'config/stage03/maize_extension.yml').read_text())
    manifest=json.loads((root/config['manifest']).read_text())
    return config,manifest


def validate_identity(asset):
    expected='.'.join(['GAEZ-V5',asset['map_code'],asset['period_code'],asset['climate_model_code'],
                       asset['ssp_code'],'MZE',asset['management_code']])
    for key,suffix in [('tiff_url','tif'),('json_url','json')]:
        url=asset[key];parts=urlsplit(url)
        exact=f'https://storage.googleapis.com/fao-gismgr-gaez-v5-data/DATA/GAEZ-V5/MAPSET/{asset["map_code"]}/{expected}.{suffix}'
        if url!=exact or parts.query or parts.fragment:
            raise VerificationError('FAILED_METADATA_VALIDATION','Source URL or filename dimensions differ from the approved exact object')
    if asset['period_code'].startswith('FP') and asset['management_code'] not in {'HRLM','HILM'}:
        raise VerificationError('FAILED_METADATA_VALIDATION','Future low-input assets are outside the supplied inventory')
    if asset['map_code']=='RES05-SXX30AS' and asset['period_code']!='HP0120':
        raise VerificationError('FAILED_METADATA_VALIDATION','Future continuous suitability is blocked')


def header_evidence(response):
    allowed=['Content-Type','Content-Length','Content-Range','ETag','Last-Modified','x-goog-hash','x-goog-generation']
    return {k:response.headers[k] for k in allowed if k in response.headers}


def bounded_get(url,path,config):
    """Download small supporting metadata only; never called for analytical TIFFs."""
    if urlsplit(url).path.lower().endswith(('.tif','.tiff')):raise ValueError('Global raster downloads are prohibited')
    maximum=config['maximum_json_bytes'];error=None
    for _ in range(config['retry_limit']+1):
        try:
            with requests.get(url,stream=True,timeout=config['request_timeout_seconds']) as response:
                response.raise_for_status()
                if urlsplit(response.url).path.rsplit('/',1)[-1]!=urlsplit(url).path.rsplit('/',1)[-1]:
                    raise ValueError('Metadata response filename changed')
                data=bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>maximum:raise ValueError('Supporting metadata exceeds the configured byte budget')
                Path(path).write_bytes(data)
                return header_evidence(response)
        except (requests.RequestException,ValueError) as exc:error=exc
    raise VerificationError('FAILED_REMOTE_ACCESS',str(error))


def validate_sidecar(asset,data):
    expected={'PERIOD':asset['period_code'],'CLIM':asset['climate_model_code'],'SSP':asset['ssp_code'],
              'CROP-RES05':'MZE','WSIM-RES05':asset['management_code']}
    actual={m.get('dimensionCode'):m.get('code') for m in data.get('dimensionMembers',[])}
    if len(data.get('dimensionMembers',[]))!=5 or data.get('workspaceCode')!='GAEZ-V5' or data.get('mapsetCode')!=asset['map_code'] or data.get('code')!=asset['object_name'][:-4] or actual!=expected:
        raise VerificationError('FAILED_METADATA_VALIDATION','Source JSON identity or dimensions differ from the exact analytical asset')


def range_probe(url,config):
    error=None
    for _ in range(config['retry_limit']+1):
        try:
            with requests.get(url,headers={'Range':'bytes=0-16383','Accept-Encoding':'identity'},stream=True,timeout=config['request_timeout_seconds']) as response:
                response.raise_for_status()
                if response.status_code!=206 or not re.match(r'bytes 0-\d+/\d+',response.headers.get('Content-Range','')):
                    raise VerificationError('FAILED_REMOTE_ACCESS','Source did not honor bounded HTTP byte ranges; full download refused')
                if urlsplit(response.url).path.rsplit('/',1)[-1]!=urlsplit(url).path.rsplit('/',1)[-1]:
                    raise VerificationError('FAILED_METADATA_VALIDATION','Raster response filename changed')
                first=next(response.iter_content(16),b'')
                if first[:2] not in {b'II',b'MM'}:raise VerificationError('FAILED_METADATA_VALIDATION','Response is not a TIFF header')
                return header_evidence(response)
        except requests.RequestException as exc:error=exc
    raise VerificationError('FAILED_REMOTE_ACCESS',str(error))


def validate_grid(asset,source):
    if source.count!=1 or source.crs is None or str(source.crs)!=asset['expected_crs']:
        raise VerificationError('FAILED_METADATA_VALIDATION','Expected a single-band WGS84 source raster')
    expected=asset['expected_resolution_degrees']
    if not np.allclose(source.res,[expected,expected],rtol=0,atol=1e-10) or source.transform.b or source.transform.d:
        raise VerificationError('FAILED_METADATA_VALIDATION','Source pixel size or orientation differs from product metadata')
    expected_transform=[expected,0.,-180.,0.,-expected,90.]
    if not np.allclose(list(source.transform)[:6],expected_transform,rtol=0,atol=1e-9):
        raise VerificationError('FAILED_METADATA_VALIDATION','Source grid origin differs from the official global grid')
    if source.width!=asset['expected_width'] or source.height!=asset['expected_height']:
        raise VerificationError('FAILED_METADATA_VALIDATION','Source dimensions differ from documented global grid')
    if asset.get('expected_dtype') and source.dtypes[0]!=asset['expected_dtype']:
        raise VerificationError('FAILED_METADATA_VALIDATION','Source data type differs from official mapset metadata')
    if source.nodata is not None and source.nodata!=asset['nodata']:
        raise VerificationError('FAILED_METADATA_VALIDATION','Source NoData differs from official product metadata')
    if not np.allclose(source.scales,[asset['scale']]) or not np.allclose(source.offsets,[asset['offset']]):
        raise VerificationError('FAILED_METADATA_VALIDATION','Source scale/offset differs from the documented decoding rule')
    if source.units[0] and source.units[0].casefold()!=asset['unit'].casefold():
        raise VerificationError('FAILED_METADATA_VALIDATION','Source unit conflicts with product metadata')


def read_result(path,aoi,asset,area_crs):
    spec=dict(asset)
    if spec.get('valid_range') and spec['valid_range'][1] is None:spec.pop('valid_range')
    result=read_raster(path,aoi,spec,area_crs)
    count=result['stats']['valid_native_cell_count']
    result['stats'].setdefault('quality_flag','NO_VALID_DATA' if not count else 'FEW_NATIVE_CELLS' if count<5 else 'OK')
    return result


def extract(asset,aoi,directory,config,opener=None):
    """Create one native clip and its receipt. An injected opener is for tests only."""
    validate_identity(asset);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    clip=directory/'clip.tif';sidecar=directory/'source.json'
    report=dict(layer_id=asset['layer_id'],map_code=asset['map_code'],period_code=asset['period_code'],
        ssp_code=asset['ssp_code'],management_code=asset['management_code'],climate_model_code=asset['climate_model_code'],
        source_url=asset['tiff_url'],json_url=asset['json_url'],retrieved_at_utc=utcnow(),
        source_unit=asset['unit'],scale=asset['scale'],offset=asset['offset'],source_nodata=asset['nodata'],
        verification_status='FAILED_REMOTE_ACCESS',json_status='NOT_YET_VERIFIED',algorithm_version=ALGORITHM_VERSION)
    try:
        report['json_http']=bounded_get(asset['json_url'],sidecar,config)
        validate_sidecar(asset,json.loads(sidecar.read_text()))
        report.update(json_status='VERIFIED',json_sha256=sha256(sidecar))
        report['raster_http']=range_probe(asset['tiff_url'],config)
        report['remote_checksum']=report['raster_http'].get('x-goog-hash','REMOTE_CHECKSUM_NOT_AVAILABLE')
        environment=dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
            GDAL_HTTP_TIMEOUT=str(config['request_timeout_seconds']),GDAL_HTTP_MAX_RETRY=str(config['retry_limit']),
            CPL_VSIL_CURL_CHUNK_SIZE='16384',VSI_CACHE=False,GDAL_TIFF_INTERNAL_MASK=True)
        with rasterio.Env(**environment), (opener or rasterio.open)(asset['tiff_url']) as source:
            validate_grid(asset,source)
            report['source_raster']=dict(crs=str(source.crs),transform=list(source.transform)[:6],bounds=list(source.bounds),
                width=source.width,height=source.height,resolution=list(source.res),dtype=source.dtypes[0],nodata=source.nodata,
                scales=list(source.scales),offsets=list(source.offsets),units=list(source.units),
                mask_flags=[[v.name for v in f] for f in source.mask_flag_enums],count=source.count)
            geom=project_geometry(aoi,4326,source.crs,.0005)
            bounds=geom.bounds;sb=source.bounds
            x0,y0,x1,y1=max(bounds[0],sb.left),max(bounds[1],sb.bottom),min(bounds[2],sb.right),min(bounds[3],sb.top)
            if x0>=x1 or y0>=y1:
                area=project_geometry(aoi,4326,config['area_crs'],.0005).area/1e4
                report.update(verification_status='NO_COVERAGE',aoi_overlap=False,valid_area_ha=0,masked_area_ha=0,
                    outside_footprint_area_ha=area,valid_area_percentage=0,valid_native_cell_count=0,intersecting_native_cell_count=0)
                return report
            window=from_bounds(x0,y0,x1,y1,source.transform)
            col0,row0=np.floor([window.col_off,window.row_off]).astype(int)
            col1,row1=np.ceil([window.col_off+window.width,window.row_off+window.height]).astype(int)
            window=Window(max(0,col0),max(0,row0),min(source.width,col1)-max(0,col0),min(source.height,row1)-max(0,row0))
            cells=int(window.width*window.height)
            if cells>config['maximum_window_cells'] or cells*np.dtype(source.dtypes[0]).itemsize>config['maximum_window_bytes']:
                raise VerificationError('FAILED_CLIP_VALIDATION','Native AOI window exceeds the configured budget')
            raw=source.read(1,window=window);source_mask=source.read_masks(1,window=window)>0
            transform=source.window_transform(window)
            weights,_=area_weights(aoi,transform,source.crs,*raw.shape,config['area_crs'])
            valid=source_mask & (raw!=asset['nodata']);in_aoi=valid & (weights>0)
            values=raw.astype(float)*asset['scale']+asset['offset']
            low,high=asset['valid_range'];bad=~np.isfinite(values)|(values<low)
            if high is not None:bad|=values>high
            if asset['data_type']=='categorical':bad|=values!=np.floor(values)
            if (in_aoi&bad).any():raise VerificationError('FAILED_RANGE_VALIDATION','Observed valid source values violate the documented range/classes')
            valid&=np.isfinite(values)
            profile=dict(driver='GTiff',height=raw.shape[0],width=raw.shape[1],count=1,dtype=raw.dtype,
                crs=source.crs,transform=transform,nodata=asset['nodata'],compress='LZW')
            with rasterio.open(clip,'w',**profile) as out:
                out.write(raw,1);out.write_mask(valid.astype('uint8')*255)
                out.scales=source.scales;out.offsets=source.offsets
                out.update_tags(source_url=asset['tiff_url'],source_unit=asset['unit'],scale_applied='false')
            report.update(window=dict(column=int(window.col_off),row=int(window.row_off),width=int(window.width),height=int(window.height)),
                          masking='Internal source validity AND documented NoData; fractional AOI intersections used in statistics')
        with rasterio.open(clip) as reopened:
            same=(reopened.crs==profile['crs'] and reopened.transform==transform and reopened.shape==raw.shape
                  and reopened.dtypes[0]==raw.dtype.name and np.array_equal(reopened.read(1),raw,equal_nan=True)
                  and np.array_equal(reopened.read_masks(1)>0,valid) and reopened.nodata==asset['nodata'])
            if not same:raise VerificationError('FAILED_CLIP_VALIDATION','Reopened native-grid clip differs from the source window')
        result=read_result(clip,aoi,asset,config['area_crs'])
        report.update(result['stats'])
        report.update(verification_status='VERIFIED_INSIDE_AOI' if result['valid'].any() else 'VERIFIED_BUT_EMPTY_INSIDE_AOI',
                      aoi_overlap=True,clip_sha256=sha256(clip),clip_reopened=True)
        area=result['stats']['aoi_area_ha']
        report['area_closure_passed']=abs(report['valid_area_ha']+report['masked_area_ha']+report['outside_footprint_area_ha']-area)<=area*config['area_tolerance_fraction']
        if not report['area_closure_passed']:raise VerificationError('FAILED_CLIP_VALIDATION','AOI area accounting did not close')
    except Exception as error:
        report.update(verification_status=getattr(error,'status','FAILED_REMOTE_ACCESS' if isinstance(error,(requests.RequestException,rasterio.errors.RasterioIOError)) else 'FAILED_METADATA_VALIDATION'),error=str(error))
    finally:write_json(directory/'verification.json',report)
    return report


def cached_extract(asset,aoi,aoi_hash,cache,config,extractor=None):
    key=hashlib.sha256(json.dumps(dict(asset=asset,aoi=aoi_hash,algorithm=ALGORITHM_VERSION),sort_keys=True).encode()).hexdigest()
    folder=Path(cache)/'maize'/key;marker=folder/'complete.json'
    if marker.exists():
        try:
            hashes=json.loads(marker.read_text())
            if hashes and all((folder/name).is_file() and sha256(folder/name)==digest for name,digest in hashes.items()):
                report=json.loads((folder/'verification.json').read_text())
                if report['verification_status'] in VERIFIED:return folder,report,True
        except (ValueError,OSError):pass
    if folder.exists():shutil.rmtree(folder)
    report=(extractor or extract)(asset,aoi,folder,config)
    if report['verification_status'] in VERIFIED:
        write_json(marker,{p.name:sha256(p) for p in folder.iterdir() if p.is_file() and p.name!='complete.json'})
    return folder,report,False
