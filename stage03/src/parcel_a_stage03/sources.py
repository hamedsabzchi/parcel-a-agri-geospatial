"""Bounded extraction from exact verified collections; no source discovery."""
from __future__ import annotations
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import rasterio
import requests
from affine import Affine
from rasterio.warp import reproject, Resampling, calculate_default_transform
from shapely.geometry import mapping
from .common import sha256, write_json, utcnow, code_hash
from .spatial import project_geometry, area_weights
from .temporal import date, interval_end, next_month, expected_count, aggregate_month

SENTINEL=-999999.0


def connect(project):
    import ee
    ee.Initialize(project=project)
    ee.data.setDeadline(90000)
    if ee.String("parcel-a-stage03").getInfo()!="parcel-a-stage03":
        raise RuntimeError("Earth Engine connection check failed")


def download(url,path,limit,timeout,retries):
    error=None
    for attempt in range(retries+1):
        try:
            size=0
            with requests.get(url,stream=True,timeout=(15,timeout)) as response:
                response.raise_for_status()
                with Path(path).open("wb") as f:
                    for block in response.iter_content(128*1024):
                        size+=len(block)
                        if size>limit: raise ValueError("AOI download exceeds configured byte budget")
                        f.write(block)
            return
        except (requests.RequestException,ValueError) as exc:
            error=exc
            Path(path).unlink(missing_ok=True)
    # Do not persist an expiring signed download URL in logs or provenance.
    raise RuntimeError(f"Bounded download failed after {retries+1} attempts: {type(error).__name__}") from None


def window(aoi,projection,buffer_metres=0):
    if buffer_metres:
        aoi=project_geometry(project_geometry(aoi,"EPSG:4326","EPSG:32633").buffer(buffer_metres),"EPSG:32633","EPSG:4326")
    native=project_geometry(aoi,"EPSG:4326",projection["crs"],.0005)
    t=Affine(*projection["transform"])
    if t.b or t.d: raise ValueError("Unsupported rotated Earth Engine native grid")
    x0,y0,x1,y1=native.bounds
    pixels=[(~t)*(x,y) for x in (x0,x1) for y in (y0,y1)]
    c0=math.floor(min(p[0] for p in pixels)); c1=math.ceil(max(p[0] for p in pixels))
    r0=math.floor(min(p[1] for p in pixels)); r1=math.ceil(max(p[1] for p in pixels))
    return t*Affine.translation(c0,r0), c1-c0,r1-r0


def ee_download(image,projection,aoi,path,config,bands=1,buffer=0):
    transform,width,height=window(aoi,projection,buffer)
    budget=config["max_download_bytes"]
    if width>10000 or height>10000 or width*height*bands*4>min(budget,30_000_000):
        raise ValueError("Native AOI request exceeds the download budget; no coarsening or global fallback")
    image=image.toFloat().unmask(SENTINEL,False)
    url=image.getDownloadURL(dict(crs=projection["crs"],crs_transform=list(transform)[:6],
                                dimensions=f"{width}x{height}",format="GEO_TIFF",filePerBand=False))
    download(url,path,budget,config["request_timeout_seconds"],config["retry_limit"])
    with rasterio.open(path) as src:
        if src.count!=bands or (src.width,src.height)!=(width,height) or not src.transform.almost_equals(transform):
            raise ValueError("Earth Engine returned an unexpected analytical grid")
        data=src.read();profile=src.profile
    profile.update(nodata=SENTINEL,compress="LZW")
    temp=Path(str(path)+".validated.tif")
    with rasterio.open(temp,"w",**profile) as dst:dst.write(data)
    temp.replace(path)
    return dict(crs=projection["crs"],transform=list(transform)[:6],width=width,height=height,
                original_projection=projection,download_sha256=sha256(path))


def cached_job(layer,aoi_hash,cache,producer):
    key=hashlib.sha256(json.dumps(dict(layer=layer,aoi=aoi_hash,adapter_code_sha256=code_hash()),sort_keys=True).encode()).hexdigest()
    folder=Path(cache)/key
    marker=folder/"complete.json"
    if marker.exists():
        data=json.loads(marker.read_text())
        if all((folder/p).is_file() and sha256(folder/p)==h for p,h in data["checksums"].items()):
            return folder,data["result"],True
    if folder.exists():shutil.rmtree(folder)
    folder.mkdir(parents=True)
    result=producer(folder)
    checksums={p.relative_to(folder).as_posix():sha256(p) for p in sorted(folder.rglob("*")) if p.is_file()}
    write_json(marker,dict(result=result,checksums=checksums))
    return folder,result,False


def static_ee(layer,aoi,folder,config):
    import ee
    geometry=ee.Geometry(mapping(aoi))
    collection=None
    if layer["collection_kind"]=="IMAGE":
        image=ee.Image(layer["source_id"])
    else:
        collection=ee.ImageCollection(layer["source_id"]).filterBounds(geometry.buffer(layer.get("buffer_metres",0)))
        if layer.get("period_start") and layer.get("period_end"):
            collection=collection.filterDate(layer["period_start"],layer["period_end"])
        count=int(collection.size().getInfo())
        if not count: raise ValueError("No images for the exact selected period")
        image=ee.Image(collection.sort("system:index").first())
    projection=image.select(layer["variable"]).projection().getInfo()
    image_ids=[layer["source_id"]+"/"+index for index in collection.aggregate_array("system:index").getInfo()] if collection is not None else [layer["source_id"]]
    details={"image_ids":image_ids,"retrieved_at_utc":utcnow(),"remote_checksum":"NOT_AVAILABLE",
             "selected_band_metadata":image.select(layer["variable"]).getInfo()}
    if layer.get("processing")=="dynamic_world_mode":
        probabilities=["water","trees","grass","flooded_vegetation","crops","shrub_and_scrub","built","bare","snow_and_ice"]
        minimum=layer["minimum_probability"]
        def labels(im):
            return im.select("label").updateMask(im.select(probabilities).reduce(ee.Reducer.max()).gte(minimum))
        labels_collection=collection.map(labels)
        counts=ee.Image.cat([labels_collection.map(lambda im,c=c:im.eq(c)).sum().rename("c"+str(c)) for c in range(9)])
        # arrayArgmax returns the first maximum; ascending classes give a documented lowest-code tie.
        image=counts.toArray().arrayArgmax().arrayGet([0]).rename("label")
        image=image.updateMask(labels_collection.count().gte(layer["minimum_observations"]))
        details.update(composite="Modal confident labels; lowest code on ties",minimum_probability=minimum,
            minimum_observations=layer["minimum_observations"],scene_count=count,
            observation_timestamps=collection.aggregate_array("system:time_start").getInfo())
    elif collection is not None:
        image=collection.sort("system:index").select(layer["variable"]).mosaic()
    else:image=image.select(layer["variable"])
    details["grid"]=ee_download(image,projection,aoi,folder/"raw.tif",config,buffer=layer.get("buffer_metres",0))
    return {"raster":"raw.tif","metadata":details}


def slope(dem_path,path,buffer_aoi,metric_crs="EPSG:32633",resolution=30):
    with rasterio.open(dem_path) as src:
        raw=src.read(1,masked=True).filled(np.nan)
        transform,width,height=calculate_default_transform(src.crs,metric_crs,src.width,src.height,*src.bounds,resolution=resolution)
        destination=np.full((height,width),np.nan,dtype="float32")
        reproject(raw,destination,src_transform=src.transform,src_crs=src.crs,src_nodata=np.nan,
            dst_transform=transform,dst_crs=metric_crs,dst_nodata=np.nan,resampling=Resampling.bilinear)
    dy,dx=np.gradient(destination,resolution,resolution)
    degrees=np.rad2deg(np.arctan(np.sqrt(dx*dx+dy*dy))).astype("float32")
    weights,_=area_weights(buffer_aoi,transform,metric_crs,height,width)
    degrees[weights<=0]=np.nan
    with rasterio.open(path,"w",driver="GTiff",height=height,width=width,count=1,dtype="float32",
                       crs=metric_crs,transform=transform,nodata=np.nan,compress="LZW") as dst:dst.write(degrees,1)
    return dict(method="Buffered mosaic -> 30 m metric grid, bilinear DEM -> central differences -> degrees -> AOI mask",
                horizontal_unit="m",vertical_unit="m",crs=metric_crs,resolution=resolution)


def series_ee(layer,aoi,folder,config):
    import ee
    geometry=ee.Geometry(mapping(aoi))
    # Include the previous interval for composites that straddle the first month.
    fetch_start=(date(layer["start"])-timedelta(days=17)).date().isoformat() if layer["cadence"]=="16day" else layer["start"]
    collection=ee.ImageCollection(layer["source_id"]).filterBounds(geometry).filterDate(fetch_start,layer["end"]).sort("system:time_start")
    count=int(collection.size().getInfo())
    if not count:return {"empty":True,"series":[],"metadata":{"reason":"No observations in the selected period"}}
    if count>config["max_observations"]:raise ValueError("Observation budget exceeded")
    first=ee.Image(collection.first())
    projection=first.select(layer["variable"]).projection().getInfo()
    times=collection.aggregate_array("system:time_start").getInfo()
    ids=collection.aggregate_array("system:index").getInfo()
    if len(times)!=len(set(times)):raise ValueError("Duplicate native timestamps require an explicit mosaic rule")
    starts=[datetime.fromtimestamp(t/1000,tz=timezone.utc) for t in times]
    ends=[interval_end(s,layer["cadence"]) for s in starts]
    arrays=[]; raw_records=[];grid=None
    listing=collection.toList(count)
    projections=ee.List.sequence(0,count-1).map(
        lambda i:ee.Image(listing.get(i)).select(layer["variable"]).projection()).getInfo()
    if any(p!=projection for p in projections):
        raise ValueError("Time-series native grid changed; an explicit alignment plan is required")
    if count*window(aoi,projection)[1]*window(aoi,projection)[2]*8>config["max_working_bytes"]:
        raise ValueError("Native time-series stack exceeds the working-memory budget")
    for offset in range(0,count,config["temporal_chunk_images"]):
        size=min(config["temporal_chunk_images"],count-offset)
        images=[]
        for index in range(offset,offset+size):
            original=ee.Image(listing.get(index))
            band=original.select(layer["variable"])
            if layer.get("qa_band"):
                band=band.updateMask(original.select(layer["qa_band"]).lte(layer["qa_max"]))
            images.append(band.rename("obs_"+str(index)))
        filename=f"native_{offset:04d}.tif"
        grid=ee_download(ee.Image.cat(images),projection,aoi,folder/filename,config,bands=size)
        with rasterio.open(folder/filename) as src:
            raw=src.read(masked=True).astype(float).filled(np.nan)
            if grid is not None:weights,area=area_weights(aoi,src.transform,src.crs,src.height,src.width)
        decoded=raw*layer.get("scale",1)+layer.get("offset",0)
        arrays.append(decoded)
        for local,index in enumerate(range(offset,offset+size)):
            raw_records.append(dict(image_id=layer["source_id"]+"/"+ids[index],timestamp=starts[index].isoformat(),
                interval_end=ends[index].isoformat(),file=filename,band=local+1,scale_applied=False))
    values=np.concatenate(arrays)
    anomalies=int(np.sum((values<0)&np.isfinite(values))) if layer.get("nonnegative") else 0
    # Negative packing artifacts remain in native audit files but are rejected, never clamped.
    if layer.get("nonnegative"):values[values<0]=np.nan
    rows=[];monthly=[];current=date(layer["start"])
    while current<date(layer["end"]):
        finish=min(next_month(current),date(layer["end"]))
        raster,stats=aggregate_month(values,starts,ends,weights,area,current,finish,layer["aggregation"],
                                     layer["minimum_temporal_coverage"],layer["minimum_spatial_coverage"])
        rows.append(dict(layer_id=layer["layer_id"],dataset_id=layer["dataset_id"],variable=layer["variable"],
            interval_start=current.isoformat(),interval_end=finish.isoformat(),spatial_statistic="area_weighted_mean",
            temporal_aggregation=layer["aggregation"],unit=layer["unit"],native_interval=layer["cadence"],
            expected_observation_count=expected_count(current,finish,layer["cadence"]),
            count_definition="Native intervals with at least one valid intersecting cell",**stats))
        monthly.append(raster);current=finish
    write_json(folder/"native_observations.json",raw_records)
    # Monthly native-grid summaries are decoded once and kept separate from raw stacks.
    with rasterio.open(folder/"native_0000.tif") as src:profile=src.profile
    profile.update(count=len(monthly),dtype="float32",nodata=np.nan)
    with rasterio.open(folder/"monthly.tif","w",**profile) as dst:dst.write(np.stack(monthly).astype("float32"))
    return dict(series=rows,metadata=dict(grid=grid,observations=raw_records,retrieved_at_utc=utcnow(),
        remote_checksum="NOT_AVAILABLE",negative_values_rejected=anomalies,
        allocation="Constant decoded rate/state within each native interval; amounts allocated by duration",
        processing_order="Decode and QA each cell, aggregate time, apply per-cell completeness, area-weight AOI"))


def power(layer,aoi,folder,config):
    point=aoi.centroid
    params=dict(parameters=layer["variable"],community="AG",longitude=point.x,latitude=point.y,
        start=layer["start"].replace("-",""),end=(date(layer["end"])-timedelta(days=1)).strftime("%Y%m%d"),
        format="JSON",**{"time-standard":"UTC"})
    response=requests.get(layer["source_id"],params=params,timeout=config["request_timeout_seconds"])
    response.raise_for_status()
    if len(response.content)>config["max_download_bytes"]:raise ValueError("POWER response exceeds budget")
    data=response.json();write_json(folder/"native_power.json",data)
    info=data["parameters"][layer["variable"]]
    if info["units"] not in layer["accepted_source_units"]:raise ValueError("POWER units changed")
    records=data["properties"]["parameter"][layer["variable"]]
    starts=[datetime.strptime(k,"%Y%m%d").replace(tzinfo=timezone.utc) for k in sorted(records)]
    fill=data.get("header",{}).get("fill_value",-999)
    values=np.array([records[s.strftime("%Y%m%d")] for s in starts],float)[:,None,None]
    values[values==fill]=np.nan
    rows=[];current=date(layer["start"])
    while current<date(layer["end"]):
        end=min(next_month(current),date(layer["end"]))
        _,stats=aggregate_month(values,starts,[s+timedelta(days=1) for s in starts],np.ones((1,1)),1,
            current,end,layer["aggregation"],layer["minimum_temporal_coverage"],1)
        stats["spatial_coverage_percentage"]=None
        rows.append(dict(layer_id=layer["layer_id"],dataset_id=layer["dataset_id"],variable=layer["variable"],
            interval_start=current.isoformat(),interval_end=end.isoformat(),spatial_statistic="gridded_point_query",
            temporal_aggregation=layer["aggregation"],unit=layer["unit"],longitude=point.x,latitude=point.y,
            coordinate_crs="EPSG:4326",query_method="NASA POWER daily point API, UTC",
            spatial_coverage_reason="NOT_APPLICABLE: gridded point, not parcel coverage",
            expected_observation_count=(end-current).days,count_definition="Valid daily records",**stats))
        current=end
    return dict(series=rows,metadata=dict(parameters=params,product_header=data.get("header"),
        observations=[dict(timestamp=s.isoformat(),source_id=layer["source_id"],query_coordinates=[point.x,point.y]) for s in starts],
                                         retrieved_at_utc=utcnow(),remote_checksum="NOT_AVAILABLE"))


def local_vector(layer,aoi,folder,config):
    import geopandas as gpd
    path=Path(layer["local_path"])
    if sha256(path)!=layer["expected_sha256"]:raise ValueError("Supplemental file checksum mismatch")
    frame=gpd.read_file(path)
    if frame.crs is None or not frame.geometry.is_valid.all():raise ValueError("Vector CRS/geometry invalid; no silent repair")
    source_crs=str(frame.crs)
    if len(frame)>config["max_vector_features"]:raise ValueError("Vector feature budget exceeded")
    frame=frame.to_crs(4326)
    frame["source_feature_id"]=frame.index.astype(str)
    inside=gpd.clip(frame,gpd.GeoDataFrame(geometry=[aoi],crs=4326),keep_geom_type=True)
    inside.to_file(folder/"features.gpkg",driver="GPKG")
    geo=json.loads(inside.to_json())
    write_json(folder/"features.geojson",geo)
    if layer.get("context_buffer_metres"):
        context=project_geometry(project_geometry(aoi,4326,32633).buffer(layer["context_buffer_metres"]),32633,4326)
        gpd.clip(frame,gpd.GeoDataFrame(geometry=[context],crs=4326)).to_file(folder/"context.gpkg",driver="GPKG")
    return dict(vector="features.geojson",feature_count=len(inside),metadata=dict(source_sha256=sha256(path),source_crs=source_crs,output_crs="EPSG:4326",
        verification="Supplemental CRS, geometry, checksum and AOI intersection check",checked_at_utc=utcnow()))


def local_raster(layer,aoi,folder,config):
    from rasterio.mask import mask
    from rasterio.features import geometry_window
    path=Path(layer["local_path"])
    if sha256(path)!=layer["expected_sha256"]:raise ValueError("Supplemental file checksum mismatch")
    with rasterio.open(path) as src:
        if src.crs is None or src.count!=1:raise ValueError("Supply a georeferenced single-band raster with explicit units and mask")
        geom=project_geometry(aoi,4326,src.crs,.0005)
        bounds=geometry_window(src,[mapping(geom)])
        if bounds.width*bounds.height*16>config["max_working_bytes"]:raise ValueError("Supplemental raster AOI window exceeds memory budget")
        values,transform=mask(src,[mapping(geom)],crop=True,all_touched=True,indexes=1,filled=False)
        profile=src.profile;profile.update(width=values.shape[1],height=values.shape[0],transform=transform,compress="LZW")
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(folder/"raw.tif","w",**profile) as dst:
                dst.write(values.data,1);dst.write_mask((~np.ma.getmaskarray(values)).astype("uint8")*255)
    return dict(raster="raw.tif",metadata=dict(source_sha256=sha256(path),
        verification="Supplemental CRS, checksum, native grid and AOI intersection check",checked_at_utc=utcnow()))
