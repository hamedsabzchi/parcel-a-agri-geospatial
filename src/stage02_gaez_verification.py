"""Verify the 16 selected GAEZ v5 assets using native-grid AOI windows only."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
import yaml
from rasterio.features import geometry_mask, geometry_window
from rasterio.mask import mask as rio_mask
from rasterio.errors import WindowError

GAEZ_MANIFEST_PATH = Path("config/sources/gaez_v5_source_manifest.yml")
GAEZ_OUTPUT_DIR = Path("outputs/stage02/gaez")
GAEZ_ALL_TOUCHED = True
GAEZ_SAVE_AOI_CLIPS = True
GAEZ_HTTP_TIMEOUT = 30
MAX_WINDOW_BYTES = 10 * 1024 * 1024
EXPECTED_ASSET_KEYS = frozenset(
    ["GAEZ_V5_AEZ57", "GAEZ_V5_LR_IRR"]
    + [f"GAEZ_V5_RES01_LGP__{x}" for x in ("HP0120", "HP8100")]
    + [f"GAEZ_V5_{code}__{x}" for code in ("SQX", "SQ_IDX") for x in ("HIM", "LIM")]
    + [f"GAEZ_V5_RES05_{code}__{x}" for code in ("SIX", "YXX")
       for x in ("HRLM", "LRLM", "HILM", "LILM")]
)


def _asset_records(manifest):
    for source in manifest.get("sources", []):
        base = {k: source.get(k) for k in ("dataset_id", "map_code", "title", "period", "metadata_url", "scale_factor")}
        base.update(declared_resolution=source.get("resolution"),
                    declared_nodata=source.get("nodata"), declared_unit=source.get("unit"))
        if source.get("url"):
            yield {**base, "asset_key": source["dataset_id"], "url": source["url"],
                   "json_url": source.get("json_url"), "asset_ref": source}
        for name in ("historical_assets", "primary_assets", "assets", "selected_assets"):
            for i, asset in enumerate(source.get(name, [])):
                suffix = next((asset[k] for k in ("input_code", "management", "code", "dimension") if asset.get(k)), str(i + 1))
                yield {**base, **asset, "asset_key": f"{source['dataset_id']}__{suffix}",
                       "url": asset.get("geotiff_url", asset.get("url")), "asset_ref": asset}


def gaez_complete(frame):
    """Missing, duplicated or partially successful selections never pass."""
    if "asset_key" not in frame or "verification_status" not in frame:
        return False
    return (len(frame) == 16 and not frame.asset_key.duplicated().any()
            and set(frame.asset_key) == EXPECTED_ASSET_KEYS
            and frame.verification_status.eq("VERIFIED_INSIDE_AOI").all())


def _remote_probe(url):
    # Refuse servers that ignore Range; never fall back to a full global download.
    with requests.get(url, headers={"Range": "bytes=0-0"}, stream=True,
                      timeout=GAEZ_HTTP_TIMEOUT) as response:
        response.raise_for_status()
        if response.status_code != 206 or not response.headers.get("Content-Range", "").startswith("bytes 0-0/"):
            raise ValueError("HTTP byte ranges unavailable; global download refused")
        return {"http_status": 206, "range_supported": True,
                "content_length_bytes": int(response.headers["Content-Range"].split("/")[-1])}


def _sidecar(url):
    if not url:
        return None
    with requests.get(url, stream=True, timeout=GAEZ_HTTP_TIMEOUT) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 2 * 1024 * 1024:
                raise ValueError("GAEZ JSON exceeds metadata size limit")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))


def verify_gaez_asset(asset, aoi_wgs84, output_dir=None):
    output_dir = Path(output_dir or GAEZ_OUTPUT_DIR)
    result = {k: v for k, v in asset.items() if k != "asset_ref"}
    result.update(verification_status="FAILED_ACCESS", valid_pixel_count=0,
                  checked_at_utc=datetime.now(timezone.utc).isoformat(), all_touched=GAEZ_ALL_TOUCHED,
                  sampling_note="Native cells touching the AOI; sample availability, not parcel-scale resolution or area coverage.")
    try:
        url = str(asset["url"])
        remote = url.startswith("https://")
        if remote:
            result.update(_remote_probe(url))
        result["verification_status"] = "FAILED_PROCESSING"
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT=30,
                          GDAL_HTTP_MAX_RETRY=1, CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff", VSI_CACHE=False):
            with rasterio.open("/vsicurl/" + url if remote else url) as src:
                if src.crs is None or src.count != 1:
                    raise ValueError("Expected a georeferenced, single-band GAEZ raster")
                geoms = [g.__geo_interface__ for g in aoi_wgs84.to_crs(src.crs).geometry]
                result.update(raster_crs=str(src.crs), raster_width=src.width, raster_height=src.height,
                              raster_bounds=list(src.bounds), raster_resolution=list(src.res),
                              raster_dtype=src.dtypes[0], raster_nodata=src.nodata)
                try:
                    window = geometry_window(src, geoms)
                except WindowError:
                    result.update(verification_status="FAILED_NO_AOI_OVERLAP", aoi_overlap=False)
                    return result
                itemsize = np.dtype(src.dtypes[0]).itemsize
                # Account for the native blocks needed by this window, not just the cropped array.
                bh, bw = src.block_shapes[0]
                blocks = ((int((window.row_off + window.height - 1) // bh) - int(window.row_off // bh) + 1)
                          * (int((window.col_off + window.width - 1) // bw) - int(window.col_off // bw) + 1))
                if max(window.width * window.height, blocks * bh * bw) * itemsize > MAX_WINDOW_BYTES:
                    raise ValueError("Native AOI read exceeds the 10 MB raster sample limit")
                clipped, transform = rio_mask(src, geoms, crop=True, filled=False,
                                             all_touched=GAEZ_ALL_TOUCHED, indexes=1)
                touched = geometry_mask(geoms, clipped.shape, transform,
                                        all_touched=GAEZ_ALL_TOUCHED, invert=True)
                valid = touched & ~np.ma.getmaskarray(clipped) & np.isfinite(clipped.data)
                # Both documented and intrinsic NoData are excluded. Zero remains valid for yield/irrigation.
                for nd in (src.nodata, asset.get("declared_nodata")):
                    if isinstance(nd, (int, float)) and np.isfinite(nd):
                        valid &= clipped.data != nd
                values = clipped.data[valid].astype(float)
                selected = int(touched.sum())
                result.update(aoi_overlap=True, clipped_pixel_count=int(clipped.size),
                              intersecting_pixel_count=selected, valid_pixel_count=int(values.size),
                              valid_selected_pixel_percent=100 * values.size / selected if selected else 0.0,
                              coverage_metric="Fraction of intersecting native cells with valid values; not AOI area percent")
                code = asset.get("map_code")
                categorical = str(asset.get("declared_unit", "")).lower() in {"class", "classes"}
                rule = bool(values.size)
                if categorical:
                    rule &= bool(np.equal(values, np.floor(values)).all())
                if code == "RES05-SIX":
                    rule &= bool(np.isin(values, np.arange(1, 10)).all())
                elif code == "RES05-YXX":
                    rule &= bool((values >= 0).all())
                elif code == "LR-IRR":
                    rule &= bool(((values >= 0) & (values <= 100)).all())
                result["value_rule_passed"] = rule
                if values.size:
                    if categorical and rule:
                        keys, counts = np.unique(values.astype(int), return_counts=True)
                        result.update(observed_classes={str(k): int(c) for k, c in zip(keys, counts)},
                                      dominant_class=int(keys[counts.argmax()]))
                    else:
                        result.update(min=float(values.min()), max=float(values.max()),
                                      mean=float(values.mean()), median=float(np.median(values)), std=float(values.std()))
                result["verification_status"] = ("FAILED_NO_VALID_AOI_PIXELS" if not values.size
                    else "VERIFIED_INSIDE_AOI" if rule else "FAILED_VALUE_RULE")
                if GAEZ_SAVE_AOI_CLIPS and rule:
                    path = output_dir / "clips" / f"{asset['asset_key']}.tif"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    # An explicit internal mask preserves valid zero and excludes pixels outside the AOI.
                    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
                        with rasterio.open(path, "w", driver="GTiff", height=clipped.shape[0],
                                           width=clipped.shape[1], count=1, dtype=src.dtypes[0],
                                           crs=src.crs, transform=transform, compress="LZW") as dst:
                            dst.write(clipped.data, 1)
                            dst.write_mask(valid.astype("uint8") * 255)
                    result["local_clip"] = "clips/" + path.name
        try:
            metadata = _sidecar(asset.get("json_url")) if remote else None
            result["json_metadata_available"] = metadata is not None
            if metadata is not None:
                path = output_dir / "metadata" / f"{asset['asset_key']}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        except Exception as error:
            result.update(json_metadata_available=False, json_metadata_error=str(error))
    except Exception as error:
        if result["verification_status"] == "VERIFIED_INSIDE_AOI":
            result["verification_status"] = "FAILED_PROCESSING"
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def run_gaez_stage02_verification(aoi: gpd.GeoDataFrame, manifest_path=GAEZ_MANIFEST_PATH, output_dir=None):
    if aoi.empty or aoi.crs is None or aoi.geometry.is_empty.any() or not aoi.geometry.is_valid.all():
        raise ValueError("A valid AOI with a defined CRS is required")
    manifest = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
    assets = list(_asset_records(manifest))
    keys = [a["asset_key"] for a in assets]
    if str(manifest.get("manifest_version")) != "2.5" or len(keys) != 16 or set(keys) != EXPECTED_ASSET_KEYS:
        raise ValueError("Manifest v2.5 must contain exactly the 16 selected, unique GAEZ assets")
    out = Path(output_dir or GAEZ_OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    rows = [verify_gaez_asset(a, aoi.to_crs(4326), out) for a in assets]
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "gaez_verification_report.csv", index=False)
    (out / "gaez_verification_report.json").write_text(frame.to_json(orient="records", indent=2), encoding="utf-8")
    verified = copy.deepcopy(manifest)
    for asset, result in zip(_asset_records(verified), rows):
        asset["asset_ref"].update(status=result["verification_status"], verification_evidence={
            k: v for k, v in result.items() if k not in asset})
    verified["stage_02_gaez_verification"] = {
        "assets_expected": 16, "assets_checked": len(frame),
        "assets_verified": int(frame.verification_status.eq("VERIFIED_INSIDE_AOI").sum()),
        "overall_status": "VERIFIED_INSIDE_AOI" if gaez_complete(frame) else "REVIEW_REQUIRED",
        "all_touched": True, "future_cmip6": "DEFERRED_UNTIL_CURRENT_PROTOTYPE_APPROVAL",
        "other_crops": "DEFERRED_UNTIL_PROTOTYPE_APPROVAL"}
    (out / "gaez_v5_source_manifest_verified.yml").write_text(yaml.safe_dump(verified, sort_keys=False), encoding="utf-8")
    return frame
