"""Exact native-cell intersections; display grids never enter statistics."""
from __future__ import annotations
import numpy as np
import rasterio
import shapely
from pyproj import Transformer
from shapely.ops import transform as geometry_transform
from shapely.geometry import mapping


def project_geometry(geom, source, target, densify=None):
    if densify:
        geom = shapely.segmentize(geom, densify)
    return geometry_transform(Transformer.from_crs(source, target, always_xy=True).transform, geom)


def area_weights(aoi, transform, crs, height, width, area_crs="EPSG:6933", chunk_size=20000):
    if abs(transform.b) > 1e-12 or abs(transform.d) > 1e-12:
        raise ValueError("Rotated grids require an explicit adapter")
    target = project_geometry(aoi, "EPSG:4326", area_crs, .0005)
    weights = np.zeros(height * width)
    native_to_area = Transformer.from_crs(crs, area_crs, always_xy=True)
    step = min(abs(transform.a), abs(transform.e)) / 8
    for start in range(0, weights.size, chunk_size):
        indices = np.arange(start, min(start + chunk_size, weights.size))
        rows, cols = np.divmod(indices, width)
        x0, y0 = transform * (cols, rows)
        x1, y1 = transform * (cols + 1, rows + 1)
        cells = shapely.box(np.minimum(x0,x1), np.minimum(y0,y1), np.maximum(x0,x1), np.maximum(y0,y1))
        cells = shapely.segmentize(cells, step)
        projected = shapely.transform(cells, native_to_area.transform, interleaved=False)
        weights[indices] = shapely.area(shapely.intersection(projected, target))
    weights[weights < target.area * 1e-14] = 0
    return weights.reshape(height, width), float(target.area)


def weighted_summary(values, weights):
    ok = (weights > 0) & np.isfinite(values)
    x, w = values[ok].astype(float), weights[ok].astype(float)
    fields = ["min", "max", "mean", "std", "p05", "p25", "median", "p75", "p95"]
    if not len(x):
        return {**dict.fromkeys(fields), "quality_flag": "NO_VALID_DATA"}
    mean = float(np.sum(x*w) / w.sum())
    order = np.argsort(x, kind="stable")
    cumulative = np.cumsum(w[order]) / w.sum()
    q = x[order][np.minimum(np.searchsorted(cumulative, [.05,.25,.5,.75,.95], side="left"), len(x)-1)]
    return dict(min=float(x.min()), max=float(x.max()), mean=mean,
                std=float(np.sqrt(np.sum(w*(x-mean)**2)/w.sum())),
                **dict(zip(fields[4:], map(float,q))),
                quality_flag="FEW_NATIVE_CELLS" if len(x)<5 else "OK")


def read_raster(path, aoi, layer, area_crs="EPSG:6933"):
    with rasterio.open(path) as src:
        if src.crs is None or src.count != 1:
            raise ValueError("A single-band georeferenced raster is required")
        raw = src.read(1)
        valid = (src.read_masks(1)>0) & np.isfinite(raw)
        nodata = layer.get("nodata")
        if isinstance(nodata, (int,float)):
            valid &= raw != nodata
        weights, area = area_weights(aoi, src.transform, src.crs, src.height, src.width, area_crs)
        scale = 1 if layer.get("scale_already_applied") else layer.get("scale", 1)
        offset = 0 if layer.get("scale_already_applied") else layer.get("offset", 0)
        values = raw.astype(float)*scale+offset
        if layer.get("valid_range"):
            lo, hi = layer["valid_range"]
            invalid = valid & (weights>0) & ((values<lo) | (values>hi))
            if invalid.any():
                raise ValueError(f"{int(invalid.sum())} values outside the documented range {lo}–{hi}")
        valid &= weights>0
        values[~valid] = np.nan
        valid_area = float(weights[valid].sum())
        masked_area = float(weights[~valid].sum())
        outside = max(0., area-float(weights.sum()))
        if abs(valid_area+masked_area+outside-area) > area*.0001:
            raise ValueError("Native-cell area accounting exceeds 0.01% tolerance")
        stats = dict(aoi_area_ha=area/1e4, valid_area_ha=valid_area/1e4,
            masked_area_ha=masked_area/1e4, outside_footprint_area_ha=outside/1e4,
            valid_area_percentage=100*valid_area/area,
            intersecting_native_cell_count=int((weights>0).sum()), valid_native_cell_count=int(valid.sum()),
            area_method=f"Exact cell intersections in {area_crs}; densified AOI and cell edges",
            unit=layer["unit"], native_crs=str(src.crs), native_resolution=list(src.res),
            native_transform=list(src.transform)[:6], raster_nodata=src.nodata,
            quantile_method="First sorted value at cumulative normalized area weight >= p")
        if layer["data_type"] != "categorical":
            stats.update(weighted_summary(values,weights))
            for long,short in {"minimum":"min","maximum":"max","standard_deviation":"std",
                               "percentile_05":"p05","percentile_25":"p25","percentile_75":"p75","percentile_95":"p95"}.items():
                stats[long]=stats[short]
        stats.update(outside_area_ha=outside/1e4,statistic_method="Intersection-area weighted; population SD")
        cells = []
        features = []
        if (weights>0).sum() <= 1500:
            for row,col in zip(*np.where(weights>0)):
                x0,y0=src.transform*(int(col),int(row));x1,y1=src.transform*(int(col)+1,int(row)+1)
                native = shapely.box(min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1))
                geographic = project_geometry(native, src.crs, "EPSG:4326", min(src.res)/8)
                cell_id = f"{src.crs}:{x0:.10f}:{y0:.10f}:{src.res[0]:.10f}:{src.res[1]:.10f}"
                record = dict(layer_id=layer["layer_id"], cell_id=cell_id, row=int(row), column=int(col),
                    raw_value=float(raw[row,col]) if valid[row,col] else None,
                    value=float(values[row,col]) if valid[row,col] else None, unit=layer["unit"],
                    valid=bool(valid[row,col]), intersection_area_ha=float(weights[row,col]/1e4))
                cells.append(record)
                features.append(dict(type="Feature", properties=record, geometry=mapping(geographic.intersection(aoi))))
        return dict(values=values, raw=raw, valid=valid, weights=weights, stats=stats, cells=cells,
                    features=features, transform=src.transform, crs=src.crs, profile=src.profile)


def categorical_summary(result, layer, legend):
    values,weights = result["values"],result["weights"]
    observed = np.unique(values[np.isfinite(values)])
    captions = {int(e["code"]):e for e in legend["entries"]}
    if any(v != int(v) or int(v) not in captions for v in observed):
        raise ValueError("Observed class code has no authoritative caption")
    valid_area = result["stats"]["valid_area_ha"]
    rows=[]
    for code in observed:
        selected = values==code
        area = float(weights[selected].sum()/1e4)
        e=captions[int(code)]
        rows.append(dict(layer_id=layer["layer_id"],dataset_id=layer["dataset_id"],
            climate_scenario=layer.get("climate_scenario"), management_code=layer.get("management_code"),
            class_code=int(code), class_label=e["caption"], class_colour=e["colour"],
            intersecting_cell_count=int(selected.sum()),fractional_area_ha=area,
            percentage_of_valid_area=100*area/valid_area,
            percentage_of_total_aoi=100*area/result["stats"]["aoi_area_ha"],area_method=result["stats"]["area_method"]))
    if rows and abs(sum(r["percentage_of_valid_area"] for r in rows)-100)>.01:
        raise ValueError("Class-area percentage accounting failed")
    return rows
