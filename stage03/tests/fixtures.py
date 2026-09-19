"""Explicit synthetic test inputs. Never imported by the runtime package."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import copy
import json
import numpy as np
import rasterio
import yaml
from rasterio.transform import from_origin
from parcel_a_stage03.common import sha256, write_json, write_csv
from parcel_a_stage03.inputs import gaez_assets

ROOT=Path(__file__).resolve().parents[2]


def fixture(directory,optional=False):
    directory=Path(directory);root=directory/"synthetic_stage02";root.mkdir(parents=True)
    original=yaml.safe_load((ROOT/"config/sources/gaez_v5_source_manifest.yml").read_text())
    verified=copy.deepcopy(original)
    for s in verified["sources"]:
        if s.get("url"):s["status"]="VERIFIED_INSIDE_AOI"
        for group in ("historical_assets","primary_assets","assets","selected_assets"):
            for a in s.get(group,[]):a["status"]="VERIFIED_INSIDE_AOI"
    verified["stage_02_gaez_verification"]={"assets_expected":16,"assets_checked":16,"assets_verified":16,"overall_status":"VERIFIED_INSIDE_AOI"}
    assets=gaez_assets(original);reports=[]
    for i,a in enumerate(assets):
        # Real native spacings/origin, synthetic values. Tests do not claim actual GAEZ observations.
        resolution=1/12 if a["map_code"].startswith("RES") else 1/120
        x0=13.8333333333333;y0=6.75
        width=int(np.ceil((14-x0)/resolution));height=int(np.ceil((y0-6.5)/resolution))
        transform=from_origin(x0,y0,resolution,resolution)
        values=np.full((height,width),3,dtype="float32")
        if a["map_code"]=="RES05-YXX":values=np.arange(width*height,dtype="float32").reshape(height,width)*25+i*100
        if a["map_code"]=="LR-IRR":values[:]=0
        path=root/"stage02b/gaez/clips"/(a["asset_key"]+".tif");path.parent.mkdir(parents=True,exist_ok=True)
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(path,"w",driver="GTiff",width=width,height=height,count=1,dtype="float32",crs="EPSG:4326",transform=transform,compress="LZW") as dst:
                dst.write(values,1);dst.write_mask(np.full(values.shape,255,dtype="uint8"))
        reports.append({k:v for k,v in a.items() if k not in {"class_legend","dimension_codes"}}|dict(
            verification_status="VERIFIED_INSIDE_AOI",local_clip="clips/"+path.name,raster_crs="EPSG:4326",
            raster_resolution=[resolution,resolution],raster_width=round(360/resolution),raster_height=round(180/resolution),
            raster_nodata=None,aoi_overlap=True,value_rule_passed=True,synthetic_test_fixture=True))
    write_json(root/"stage02b/gaez/gaez_verification_report.json",reports)
    write_csv(root/"stage02b/gaez/gaez_verification_report.csv",reports)
    (root/"stage02b/gaez/gaez_v5_source_manifest_verified.yml").write_text(yaml.safe_dump(verified))
    registry=yaml.safe_load((ROOT/"config/datasets.yml").read_text())["datasets"]
    rows=[]
    for r in registry:
        row=dict(r,FINAL_STATUS="METADATA_ONLY",FINAL_ACTION="RUN_AOI_DATA_SAMPLE",FINAL_EVIDENCE="SYNTHETIC TEST FIXTURE: no live availability claim")
        if r["dataset_id"]=="FAO_GAEZ_V5_CURRENT" or (optional and r["dataset_id"]=="LC_ESA_WORLDCOVER_2021"):
            row.update(FINAL_STATUS="VERIFIED_INSIDE_AOI",FINAL_ACTION="USE_NEXT")
        rows.append(row)
    write_json(root/"final/metadata/final_data_inventory.json",rows)
    write_csv(root/"final/tables/final_data_inventory.csv",rows)
    write_json(root/"final/metadata/final_summary.json",dict(aoi_sha256=sha256(ROOT/"data/aoi/parcel_a.geojson"),gaez_assets_verified=16,generated_at_utc="SYNTHETIC_TEST_RUN"))
    write_json(root/"final/metadata/source_checksums.json",{p:sha256(ROOT/p) for p in ("config/datasets.yml","config/sources/gaez_v5_source_manifest.yml")})
    log=root/"stage02a/logs/discovery_log.txt";log.parent.mkdir(parents=True);log.write_text("Synthetic test fixture only\n")
    rehash(root)
    archive=directory/"synthetic_stage02_test_fixture.zip"
    with ZipFile(archive,"w",ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            if p.is_file():z.write(p,p.relative_to(root))
    return root,archive


def rehash(root):
    write_json(Path(root)/"final/metadata/package_checksums.json",{p.relative_to(root).as_posix():sha256(p) for p in Path(root).rglob("*") if p.is_file() and p.name!="package_checksums.json"})
