"""Strict read-only adapter for the completed Stage 02 v2.5 package."""
from __future__ import annotations
import csv
import json
import math
import shutil
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import numpy as np
import rasterio
import yaml
from shapely.geometry import shape
from .common import relative_file, sha256

REQUIRED = [
    "final/tables/final_data_inventory.csv", "final/metadata/final_data_inventory.json",
    "final/metadata/final_summary.json", "final/metadata/source_checksums.json",
    "final/metadata/package_checksums.json", "stage02a/logs/discovery_log.txt",
    "stage02b/gaez/gaez_verification_report.csv", "stage02b/gaez/gaez_verification_report.json",
    "stage02b/gaez/gaez_v5_source_manifest_verified.yml",
]
MAX_MEMBER_BYTES = 500_000_000


def read_csv(path):
    """Read complete evidence cells within the existing input member budget."""
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_MEMBER_BYTES:
        raise ValueError("Stage 02 CSV exceeds the input member budget")
    previous = csv.field_size_limit()
    try:
        # CSV's default 128 Ki-character limit is smaller than valid Stage 02
        # metadata fields. A UTF-8 field cannot contain more characters than the
        # file has bytes; this bound retains the full evidence without truncation.
        csv.field_size_limit(max(previous, size))
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    finally:
        csv.field_size_limit(previous)


def gaez_assets(manifest):
    assets = []
    for source in manifest["sources"]:
        base = {k: v for k, v in source.items() if k not in {"historical_assets", "primary_assets", "assets", "selected_assets"}}
        if source.get("url"):
            assets.append({**base, "asset_key": source["dataset_id"]})
        for group in ("historical_assets", "primary_assets", "assets", "selected_assets"):
            for item in source.get(group, []):
                suffix = next(item[k] for k in ("input_code", "management", "code", "dimension") if item.get(k))
                assets.append({**base, **item, "url": item.get("geotiff_url", item.get("url")),
                               "asset_key": source["dataset_id"] + "__" + suffix})
    return assets


def unpack(source, destination, max_bytes=2_000_000_000):
    source, destination = Path(source), Path(destination)
    if source.is_dir():
        return source.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with ZipFile(source) as z:
        names = set()
        if len(z.infolist()) > 10000 or sum(i.file_size for i in z.infolist()) > max_bytes:
            raise ValueError("Stage 02 archive exceeds the configured input budget")
        for i in z.infolist():
            p = PurePosixPath(i.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in i.filename or ":" in i.filename or not p.parts:
                raise ValueError("Unsafe archive path")
            if i.filename in names or stat.S_ISLNK(i.external_attr >> 16):
                raise ValueError("Duplicate or symlink archive member")
            names.add(i.filename)
            if i.is_dir():
                continue
            if i.file_size > MAX_MEMBER_BYTES or (i.file_size > 10_000_000 and i.file_size / max(1, i.compress_size) > 2000):
                raise ValueError("Unsafe archive expansion")
            target = destination.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    return destination


def unique(rows, key, expected):
    ids = [r.get(key) for r in rows]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError(f"Incompatible Stage 02 input: exact unique {key} set required")


def validate(root, project):
    root, project = Path(root), Path(project)
    for name in REQUIRED:
        relative_file(root, name)
    checks = json.loads((root / REQUIRED[4]).read_text())
    if not isinstance(checks, dict) or set(REQUIRED) - {REQUIRED[4]} - set(checks):
        raise ValueError("Required Stage 02 evidence is not checksum-covered")
    for name, digest in checks.items():
        if sha256(relative_file(root, name)) != digest:
            raise ValueError(f"Stage 02 checksum mismatch: {name}")
    aoi_path = project / "data/aoi/parcel_a.geojson"
    aoi_json = json.loads(aoi_path.read_text())
    summary = json.loads((root / REQUIRED[2]).read_text())
    if sha256(aoi_path) != summary.get("aoi_sha256"):
        raise ValueError("Stage 02 AOI checksum differs from the pinned Stage 01 AOI")
    crs = aoi_json.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
    if crs not in {"EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84"} or len(aoi_json["features"]) != 1:
        raise ValueError("Expected the pinned WGS84 Parcel A polygon")
    aoi = shape(aoi_json["features"][0]["geometry"])
    if not aoi.is_valid or aoi.is_empty or aoi.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Invalid AOI geometry")
    sources = json.loads((root / REQUIRED[1]).read_text())
    registry = yaml.safe_load((project / "config/datasets.yml").read_text())["datasets"]
    expected = {r["dataset_id"] for r in registry}
    if len(expected) != 48:
        raise ValueError("Unsupported source registry")
    unique(sources, "dataset_id", expected)
    csv_rows = read_csv(root / REQUIRED[0])
    unique(csv_rows, "dataset_id", expected)
    csv_rows = {r["dataset_id"]: r for r in csv_rows}
    for r in sources:
        for field in ("FINAL_STATUS", "FINAL_ACTION", "FINAL_EVIDENCE"):
            if not r.get(field) or str(r[field]) != csv_rows[r["dataset_id"]].get(field):
                raise ValueError("Final inventory CSV/JSON disagreement")
    source_hashes = json.loads((root / REQUIRED[3]).read_text())
    for name in ("config/datasets.yml", "config/sources/gaez_v5_source_manifest.yml"):
        if source_hashes.get(name) != sha256(project / name):
            raise ValueError(f"Incompatible Stage 02 source snapshot: {name}")
    manifest = yaml.safe_load((root / REQUIRED[8]).read_text())
    original = yaml.safe_load((project / "config/sources/gaez_v5_source_manifest.yml").read_text())
    if str(manifest.get("manifest_version")) != "2.5":
        raise ValueError("Only the explicit Stage 02 manifest v2.5 adapter is supported")
    approved = {a["asset_key"]: a for a in gaez_assets(original)}
    verified = gaez_assets(manifest)
    report = json.loads((root / REQUIRED[7]).read_text())
    unique(verified, "asset_key", approved)
    unique(report, "asset_key", approved)
    csv_gaez = read_csv(root / REQUIRED[6])
    unique(csv_gaez, "asset_key", approved)
    csv_gaez = {r["asset_key"]: r for r in csv_gaez}
    final_gaez = next(r for r in sources if r["dataset_id"] == "FAO_GAEZ_V5_CURRENT")
    if (final_gaez["FINAL_STATUS"], final_gaez["FINAL_ACTION"]) != ("VERIFIED_INSIDE_AOI", "USE_NEXT"):
        raise ValueError("Final GAEZ source decision is not verified USE_NEXT")
    verified = {a["asset_key"]: a for a in verified}
    for row in report:
        key = row["asset_key"]
        a, v = approved[key], verified[key]
        if row.get("verification_status") != "VERIFIED_INSIDE_AOI" or v.get("status") != "VERIFIED_INSIDE_AOI":
            raise ValueError(f"Unverified required GAEZ asset: {key}")
        for field in ("verification_status", "url", "local_clip"):
            if str(row.get(field)) != csv_gaez[key].get(field):
                raise ValueError(f"GAEZ report CSV/JSON mismatch: {key}")
        if row.get("url") != a["url"] or v.get("url") != a["url"]:
            raise ValueError(f"GAEZ asset identity mismatch: {key}")
        for field in ("crop_code", "period_code", "climate_source", "scenario", "input_code", "management", "dimension", "code"):
            if field in a and (v.get(field) != a[field] or row.get(field) != a[field]):
                raise ValueError(f"GAEZ scope mismatch: {key}/{field}")
        name = "stage02b/gaez/" + str(row.get("local_clip", ""))
        if name != f"stage02b/gaez/clips/{key}.tif" or name not in checks:
            raise ValueError(f"GAEZ clip is missing or untracked: {key}")
        clip = relative_file(root, name)
        with rasterio.open(clip) as src:
            if src.count != 1 or src.crs is None or src.width * src.height > 2_000_000:
                raise ValueError(f"Invalid GAEZ clip: {key}")
            if str(src.crs) != row.get("raster_crs") or not np.allclose(src.res, row["raster_resolution"], atol=1e-12):
                raise ValueError(f"Native grid changed: {key}")
            if not src.read_masks(1).any() or not all(math.isfinite(x) for x in src.transform):
                raise ValueError(f"Empty or invalid GAEZ clip: {key}")
        row["clip_path"] = str(clip)
    return dict(sources=sources, registry=registry, gaez=report, assets=approved, aoi=aoi,
                aoi_json=aoi_json, aoi_sha256=sha256(aoi_path), summary=summary, checksums=checks)
