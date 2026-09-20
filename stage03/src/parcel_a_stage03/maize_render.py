"""Additive maize map exports using the accepted Stage 03 renderer."""
from __future__ import annotations
import base64
import copy
import io
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import mapping
from PIL import Image
from . import render
from .common import write_json
from .spatial import project_geometry
from .maize_analysis import CLASS_LABELS,CLASS_COLOURS,AREA_CRS


def suitability_legend():
    return dict(legend_id='GAEZ_MZE_SIX',title='Maize suitability class',type='categorical',unit='Class',
        entries=[dict(code=c,caption=CLASS_LABELS[c],colour=CLASS_COLOURS[c-1],present=True) for c in range(1,10)],
        palette_origin='Existing Stage 03 GAEZ suitability legend; unchanged',validation_status='SOURCE_CLASSES_VERIFIED',nodata='No data (transparent)')


def continuous_legend(title,unit,domain,method):
    lo,hi=map(float,domain)
    return dict(title=title,type='continuous',unit=unit,palette='viridis',palette_origin='Project Viridis; not an official FAO style',
        validation_status='SOURCE_UNITS_VERIFIED',domain=[lo,hi],display_domain=[lo-.5,hi+.5] if lo==hi else [lo,hi],
        constant=lo==hi,domain_method=method,nodata='No data (transparent)')


def discrete_legend(title,entries,unit='Count'):
    return dict(title=title,type='categorical',unit=unit,entries=[dict(code=code,caption=caption,colour=colour,present=True) for code,caption,colour in entries],
        palette_origin='Project-derived symbols; not FAO confidence',validation_status='PROJECT_DERIVED',nodata='No data (transparent)')


def record(payload,layer,result,legend,aoi,maximum):
    ident=layer['layer_id'];display=render.overlay(result,legend,aoi,maximum)
    return save_display(payload,layer,display,legend,result.get('features',[]),aoi)


def save_display(payload,layer,display,legend,features,aoi):
    ident=layer['layer_id'];overlay='dashboard/assets/'+ident+'.png';static='maps/'+ident+'.png'
    (payload/overlay).write_bytes(display['png']);render.static_map(payload/static,layer,legend,display,aoi)
    return dict(layer_id=ident,title=layer['display_name'],group=layer['theme'],type='raster',visualization_path='../'+overlay,
        image='data:image/png;base64,'+base64.b64encode(display['png']).decode(),download_path='../'+layer['output_path'],
        static_map_path='../'+static,bounds=display['bounds'],default_visibility=False,default_opacity=.85,z_index=150,
        legend_id=layer.get('legend_id',ident),metadata_id=ident,legend=legend,metadata=layer,
        click_rule='native-cell value' if features else 'not supported',cells=features,comparison_group=layer.get('map_code'),
        attribution=layer['attribution'],display_projection=display['display_projection'],display_resampling=display['display_resampling'])


def derived(payload,ident,title,group,metric,legend,aoi,maximum,unit,config):
    """Native aligned grids -> GeoTIFF. Nonaligned partitions -> exact GeoJSON."""
    first=group['items'][0][0];units=group['units'];support=group['support'];features=[]
    for u in units:
        value=u['derived'].get(metric)
        if value is None:continue
        features.append(dict(type='Feature',geometry=mapping(project_geometry(u['geometry'],AREA_CRS,4326)),
            properties=dict(layer_id=ident,cell_id=u['unit_id'],value=value,unit=unit,valid=True,intersection_area_ha=u['area_ha'],
                            source_cell_ids=u['cell_ids'],model_values=u['derived']['model_values'])))
    if not features:return None
    if legend['type']=='categorical':
        present={f['properties']['value'] for f in features}
        for entry in legend['entries']:entry['present']=entry['code'] in present
    geojson='clipped_data/vectors/'+ident+'.geojson';write_json(payload/geojson,dict(type='FeatureCollection',features=features))
    valid_area=sum(f['properties']['intersection_area_ha'] for f in features)
    layer=dict(layer_id=ident,dataset_id='PROJECT_MAIZE_FIVE_MODELS',display_name=title,theme='Project-derived five-model maize comparison',
        variable=metric,view=metric,group_id=ident.removesuffix('_'+metric),map_code=first['map_code'],period_code=first['period_code'],period=first['period'],
        ssp_code=first['ssp_code'],climate_model_code='FIVE_MODELS',management_code=first['management_code'],
        unit=unit,data_type='categorical' if legend['type']=='categorical' else 'continuous',project_derived=True,
        source_id=[l['layer_id'] for l,r in group['items']],source_url='Project-derived from verified GAEZ v5 native cells',
        metadata_url='metadata/maize/five_model_summary.json',attribution='Project-derived from FAO / IIASA GAEZ v5 · CC-BY-4.0',
        licence='CC-BY-4.0 (source attribution retained)',processing='Exact common native-cell support; five equally weighted distinct models',
        mask_rule='All five inputs valid; undefined metric cells also masked',output_path=geojson,
        native_crs=str(group['items'][0][1]['crs']),native_resolution=group['items'][0][1]['stats']['native_resolution'],
        extraction_status='EXTRACTED',valid_area_ha=valid_area,valid_area_percentage=100*valid_area/support['aoi_area_ha'],
        valid_native_cell_count=len(features),quality_flag=support['quality_flag'],common_valid_area_ha=support['common_valid_area_ha'],
        limitation='Project-derived descriptive agreement/spread, not official FAO uncertainty, probability or confidence. '+
            ('Tied modes are transparent and retained in the tie layer. ' if metric=='modal_class' else '')+
            ('CV is unavailable when the five-model mean is zero. ' if metric=='model_coefficient_of_variation' else '')+
            'Few coarse native cells do not support parcel-scale forecasts.')
    if support['same_native_grid']:
        reference=group['items'][0][1];values=np.full(reference['values'].shape,np.nan,dtype='float32')
        for u in units:
            if u['derived'].get(metric) is None:continue
            point=project_geometry(u['geometry'].representative_point(),AREA_CRS,reference['crs'])
            col,row=(~reference['transform'])*(point.x,point.y);values[int(np.floor(row)),int(np.floor(col))]=u['derived'][metric]
        path='clipped_data/rasters/'+ident+'.tif';profile=dict(reference['profile']);profile.update(dtype='float32',nodata=-9999,count=1,compress='LZW')
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True),rasterio.open(payload/path,'w',**profile) as dst:
            dst.write(np.where(np.isfinite(values),values,-9999).astype('float32'),1);dst.write_mask(np.isfinite(values).astype('uint8')*255)
            dst.update_tags(project_derived='true',method=layer['processing'],source_layers=';'.join(layer['source_id']))
        layer['output_path']=path
        display=render.overlay(dict(reference,values=values),legend,aoi,maximum)
    else:
        target=project_geometry(aoi,4326,3857,.0005);x0,y0,x1,y1=target.bounds;w=maximum;h=max(1,round(w*(y1-y0)/(x1-x0)))
        if h>maximum:w=max(1,round(w*maximum/h));h=maximum
        transform=from_bounds(x0,y0,x1,y1,w,h)
        values=rasterize([(project_geometry(u['geometry'],AREA_CRS,3857),u['derived'][metric]) for u in units if u['derived'].get(metric) is not None],out_shape=(h,w),transform=transform,fill=np.nan,dtype='float32')
        pixels=render.rgba(values,legend);buf=io.BytesIO();Image.fromarray(pixels).save(buf,format='PNG')
        display=dict(png=buf.getvalue(),image=pixels,bounds=[[aoi.bounds[1],aoi.bounds[0]],[aoi.bounds[3],aoi.bounds[2]]],extent=target.bounds,aoi=target,
            display_projection='EPSG:3857',display_resampling='Geometric partition rasterized for display only; exact vector statistics')
        layer['native_resolution']='Exact geometric overlay of source grids; no derived analytical raster'
    layer['analytical_geometry_path']=geojson
    return layer,save_display(payload,layer,display,legend,features,aoi)
