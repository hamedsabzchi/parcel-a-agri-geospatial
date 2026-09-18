# ============================================================================
# STAGE 02 ADDITION: GAEZ v5 SOURCE VERIFICATION FOR THE MAIZE PROTOTYPE
# Manifest: config/sources/gaez_v5_source_manifest.yml
# Scope: current/historical maize prototype only; other crops and CMIP6 deferred.
# ============================================================================

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
import yaml
from rasterio.features import geometry_mask
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_geom

GAEZ_MANIFEST_PATH = Path("config/sources/gaez_v5_source_manifest.yml")
GAEZ_OUTPUT_DIR = Path("outputs/stage02/gaez")
GAEZ_CLIP_DIR = GAEZ_OUTPUT_DIR / "clips"
GAEZ_REPORT_CSV = GAEZ_OUTPUT_DIR / "gaez_verification_report.csv"
GAEZ_REPORT_JSON = GAEZ_OUTPUT_DIR / "gaez_verification_report.json"
GAEZ_UPDATED_MANIFEST = GAEZ_OUTPUT_DIR / "gaez_v5_source_manifest_verified.yml"

# Set to False if Stage 02 should verify sources without retaining AOI GeoTIFFs.
GAEZ_SAVE_AOI_CLIPS = True
GAEZ_ALL_TOUCHED = True
GAEZ_HTTP_TIMEOUT = 120


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_yaml(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _head_ok(url: str) -> Tuple[bool, Optional[int], str]:
    """Check that an official object is reachable without downloading it."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=GAEZ_HTTP_TIMEOUT)
        if r.status_code == 405:
            r = requests.get(
                url,
                headers={"Range": "bytes=0-0"},
                stream=True,
                timeout=GAEZ_HTTP_TIMEOUT,
            )
        size = r.headers.get("Content-Length")
        return r.ok, int(size) if size and size.isdigit() else None, str(r.status_code)
    except Exception as exc:
        return False, None, f"ERROR: {exc}"


def _fetch_json(url: Optional[str]) -> Optional[Dict[str, Any]]:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=GAEZ_HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _asset_records(manifest: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Flatten every raster selected in manifest v2.5 without dropping any source."""
    for source in manifest.get("sources", []):
        base = {
            "dataset_id": source["dataset_id"],
            "map_code": source.get("map_code"),
            "title": source.get("title"),
            "declared_resolution": source.get("resolution"),
            "declared_nodata": source.get("nodata"),
            "declared_unit": source.get("unit"),
        }

        if source.get("url"):
            yield {
                **base,
                "asset_key": source["dataset_id"],
                "url": source["url"],
                "json_url": source.get("json_url"),
                "asset_ref": source,
            }

        for list_name in ("historical_assets", "primary_assets", "assets", "selected_assets"):
            for i, asset in enumerate(source.get(list_name, []) or []):
                url = asset.get("geotiff_url") or asset.get("url")
                if not url:
                    continue
                suffix = (
                    asset.get("input_code")
                    or asset.get("management")
                    or asset.get("code")
                    or asset.get("dimension")
                    or str(i + 1)
                )
                yield {
                    **base,
                    "asset_key": f"{source['dataset_id']}__{suffix}",
                    "url": url,
                    "json_url": asset.get("json_url"),
                    "asset_ref": asset,
                    "period": asset.get("period"),
                    "crop": asset.get("crop"),
                    "crop_code": asset.get("crop_code"),
                    "water_supply": asset.get("water_supply"),
                    "input_level": asset.get("input_level"),
                    "input_code": asset.get("input_code"),
                    "management": asset.get("management"),
                    "dimension": asset.get("dimension"),
                }


def _safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)


def _open_remote_or_temp(url: str):
    """
    Prefer GDAL virtual HTTP access. If unsupported, download temporarily.
    Returns (dataset, temporary_path_or_none).
    """
    vsi_url = "/vsicurl/" + url
    try:
        return rasterio.open(vsi_url), None
    except Exception:
        suffix = Path(url.split("?", 1)[0]).suffix or ".tif"
        fd, temp_name = tempfile.mkstemp(prefix="gaez_", suffix=suffix)
        os.close(fd)
        with requests.get(url, stream=True, timeout=GAEZ_HTTP_TIMEOUT) as r:
            r.raise_for_status()
            with open(temp_name, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return rasterio.open(temp_name), Path(temp_name)


def _resolve_nodata(source_nodata: Any, raster_nodata: Any) -> Any:
    if source_nodata == "READ_FROM_RASTER_METADATA":
        return raster_nodata
    return raster_nodata if raster_nodata is not None else source_nodata


def _valid_values(data: np.ndarray, nodata: Any) -> np.ndarray:
    values = data.astype("float64", copy=False).ravel()
    values = values[np.isfinite(values)]
    if nodata is not None:
        try:
            if not math.isnan(float(nodata)):
                values = values[values != float(nodata)]
        except (TypeError, ValueError):
            pass
    return values


def _categorical_summary(values: np.ndarray) -> Dict[str, Any]:
    if values.size == 0:
        return {"observed_classes": {}, "dominant_class": None}
    unique, counts = np.unique(values.astype("int64"), return_counts=True)
    classes = {str(int(k)): int(v) for k, v in zip(unique, counts)}
    dominant = int(unique[np.argmax(counts)])
    return {"observed_classes": classes, "dominant_class": dominant}


def _continuous_summary(values: np.ndarray) -> Dict[str, Any]:
    if values.size == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None,
        }
    return {
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values)),
    }


def _save_clip(
    data: np.ndarray,
    transform,
    src,
    destination: Path,
    nodata: Any,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    profile = src.profile.copy()
    profile.update(
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        transform=transform,
        count=data.shape[0],
        compress="LZW",
        tiled=True,
        nodata=nodata,
    )
    with rasterio.open(destination, "w", **profile) as dst:
        dst.write(data)


def verify_gaez_asset(asset: Dict[str, Any], aoi_wgs84: gpd.GeoDataFrame) -> Dict[str, Any]:
    url = asset["url"]
    http_ok, content_length, http_status = _head_ok(url)
    result: Dict[str, Any] = {
        k: v for k, v in asset.items() if k not in {"asset_ref"}
    }
    result.update(
        http_ok=http_ok,
        http_status=http_status,
        content_length_bytes=content_length,
        json_metadata_available=_fetch_json(asset.get("json_url")) is not None,
        verification_status="FAILED_ACCESS" if not http_ok else "OPEN_PENDING",
    )
    if not http_ok:
        return result

    src = None
    temp_path: Optional[Path] = None
    try:
        src, temp_path = _open_remote_or_temp(url)
        with src:
            if src.crs is None:
                raise ValueError("Raster CRS is missing")

            aoi = aoi_wgs84.to_crs(src.crs)
            geoms = [g.__geo_interface__ for g in aoi.geometry if g is not None and not g.is_empty]
            if not geoms:
                raise ValueError("AOI has no valid geometry")

            try:
                clipped, clip_transform = rio_mask(src, geoms, crop=True, filled=True, all_touched=GAEZ_ALL_TOUCHED)
                overlaps = True
            except ValueError as exc:
                if "do not overlap" in str(exc).lower():
                    result.update(
                        raster_crs=str(src.crs),
                        raster_width=src.width,
                        raster_height=src.height,
                        raster_bounds=list(src.bounds),
                        raster_resolution=[abs(src.transform.a), abs(src.transform.e)],
                        raster_dtype=src.dtypes[0],
                        raster_nodata=src.nodata,
                        aoi_overlap=False,
                        valid_pixel_count=0,
                        verification_status="FAILED_NO_AOI_OVERLAP",
                    )
                    return result
                raise

            effective_nodata = _resolve_nodata(asset.get("declared_nodata"), src.nodata)
            values = _valid_values(clipped[0], effective_nodata)
            total_pixels = int(clipped[0].size)
            valid_pixels = int(values.size)
            coverage_pct = (100.0 * valid_pixels / total_pixels) if total_pixels else 0.0

            result.update(
                raster_crs=str(src.crs),
                raster_width=int(src.width),
                raster_height=int(src.height),
                raster_bounds=[float(x) for x in src.bounds],
                raster_resolution=[abs(float(src.transform.a)), abs(float(src.transform.e))],
                raster_dtype=src.dtypes[0],
                raster_nodata=src.nodata,
                effective_nodata=effective_nodata,
                aoi_overlap=overlaps,
                clipped_pixel_count=total_pixels,
                valid_pixel_count=valid_pixels,
                valid_coverage_percent=float(coverage_pct),
            )

            is_categorical = str(asset.get("declared_unit", "")).lower() in {"class", "classes"}
            if is_categorical:
                result.update(_categorical_summary(values))
            else:
                result.update(_continuous_summary(values))

            # Dataset-specific sanity checks from manifest v2.5.
            code = asset.get("map_code")
            if code == "RES05-SIX" and values.size:
                result["value_rule_passed"] = bool(np.isin(values.astype(int), np.arange(1, 10)).all())
            elif code == "RES05-YXX" and values.size:
                result["value_rule_passed"] = bool((values >= 0).all())
            elif code == "LR-IRR" and values.size:
                result["value_rule_passed"] = bool(((values >= 0) & (values <= 100)).all())
            else:
                result["value_rule_passed"] = True

            if valid_pixels == 0:
                result["verification_status"] = "FAILED_NO_VALID_AOI_PIXELS"
            elif not result["value_rule_passed"]:
                result["verification_status"] = "FAILED_VALUE_RULE"
            else:
                result["verification_status"] = "VERIFIED_INSIDE_AOI"

            if GAEZ_SAVE_AOI_CLIPS and valid_pixels > 0:
                clip_path = GAEZ_CLIP_DIR / f"{_safe_name(asset['asset_key'])}.tif"
                _save_clip(clipped, clip_transform, src, clip_path, effective_nodata)
                result["local_clip"] = str(clip_path)

    except Exception as exc:
        result["verification_status"] = "FAILED_PROCESSING"
        result["error"] = str(exc)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()

    return result


def _apply_results_to_manifest(
    manifest: Dict[str, Any],
    asset_rows: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result_by_key = {r["asset_key"]: r for r in results}
    for asset in asset_rows:
        r = result_by_key[asset["asset_key"]]
        ref = asset["asset_ref"]
        ref["status"] = r["verification_status"]
        ref["verification_evidence"] = {
            "http_status": r.get("http_status"),
            "raster_crs": r.get("raster_crs"),
            "raster_resolution": r.get("raster_resolution"),
            "raster_dtype": r.get("raster_dtype"),
            "raster_nodata": r.get("raster_nodata"),
            "aoi_overlap": r.get("aoi_overlap"),
            "valid_pixel_count": r.get("valid_pixel_count"),
            "valid_coverage_percent": r.get("valid_coverage_percent"),
            "observed_classes": r.get("observed_classes"),
            "min": r.get("min"),
            "max": r.get("max"),
            "mean": r.get("mean"),
            "median": r.get("median"),
            "std": r.get("std"),
            "local_clip": r.get("local_clip"),
        }

    statuses = [r["verification_status"] for r in results]
    manifest["stage_02_gaez_verification"] = {
        "prototype_crop": "Maize",
        "prototype_crop_code": "MZE",
        "historical_period": "2001-2020",
        "period_code": "HP0120",
        "other_crops": "DEFERRED_UNTIL_PROTOTYPE_APPROVAL",
        "future_cmip6": "DEFERRED_UNTIL_CURRENT_PROTOTYPE_APPROVAL",
        "assets_checked": len(results),
        "assets_verified": int(sum(s == "VERIFIED_INSIDE_AOI" for s in statuses)),
        "assets_failed": int(sum(s != "VERIFIED_INSIDE_AOI" for s in statuses)),
        "overall_status": (
            "VERIFIED_INSIDE_AOI"
            if statuses and all(s == "VERIFIED_INSIDE_AOI" for s in statuses)
            else "REVIEW_REQUIRED"
        ),
    }
    return manifest


def run_gaez_stage02_verification(
    aoi: gpd.GeoDataFrame,
    manifest_path: Path = GAEZ_MANIFEST_PATH,
) -> pd.DataFrame:
    """
    Main Stage 02 entry point.

    Parameters
    ----------
    aoi:
        Parcel A GeoDataFrame. Any CRS is accepted, but CRS must be defined.
    manifest_path:
        Consolidated GAEZ v5 manifest v2.5 placed in config/sources.
    """
    if aoi.crs is None:
        raise ValueError("Parcel A AOI CRS is undefined")
    if aoi.empty:
        raise ValueError("Parcel A AOI is empty")

    GAEZ_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GAEZ_CLIP_DIR.mkdir(parents=True, exist_ok=True)

    manifest = _load_yaml(manifest_path)
    if str(manifest.get("manifest_version")) != "2.5":
        raise ValueError(
            f"Expected GAEZ manifest version 2.5, found {manifest.get('manifest_version')}"
        )

    aoi_wgs84 = aoi.to_crs("EPSG:4326")
    asset_rows = list(_asset_records(manifest))
    results = [verify_gaez_asset(asset, aoi_wgs84) for asset in asset_rows]

    report = pd.DataFrame([{k: v for k, v in r.items() if k != "asset_ref"} for r in results])
    report.to_csv(GAEZ_REPORT_CSV, index=False)
    with GAEZ_REPORT_JSON.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    updated_manifest = _apply_results_to_manifest(manifest, asset_rows, results)
    _write_yaml(updated_manifest, GAEZ_UPDATED_MANIFEST)

    print("\nGAEZ Stage 02 verification summary")
    print(report[["dataset_id", "asset_key", "verification_status", "valid_pixel_count"]].to_string(index=False))
    print(f"\nCSV report: {GAEZ_REPORT_CSV}")
    print(f"JSON report: {GAEZ_REPORT_JSON}")
    print(f"Evidence-updated manifest: {GAEZ_UPDATED_MANIFEST}")
    return report


# ---------------------------------------------------------------------------
# INTEGRATION IN THE EXISTING STAGE 02 NOTEBOOK/SCRIPT
# ---------------------------------------------------------------------------
# After Parcel A has been loaded as a GeoDataFrame named `parcel_a_gdf`, run:
#
# gaez_verification_df = run_gaez_stage02_verification(parcel_a_gdf)
#
# Do not run Stage 03 GAEZ analysis unless every required source has either:
#   1) verification_status == VERIFIED_INSIDE_AOI, or
#   2) a documented, explicitly accepted exception.
# ---------------------------------------------------------------------------
