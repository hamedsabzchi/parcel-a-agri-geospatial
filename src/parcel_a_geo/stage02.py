"""Single Stage 02 workflow: discovery, FAO verification and one results package."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import folium
import pandas as pd
from stage02_gaez_verification import gaez_complete
from .discovery import DiscoveryRunner
from .fao_priority import PRIORITY_IDS, run_fao_priority, write_table
from .metadata import sha256_file


def check_inventory(frame, registry):
    expected = {r["dataset_id"] for r in registry}
    if len(expected) != 48 or len(frame) != 48 or frame.dataset_id.duplicated().any() or set(frame.dataset_id) != expected:
        raise ValueError("Stage 02 must preserve all 48 registered datasets exactly once")


def strict_inventory(frame, registry):
    check_inventory(frame, registry)
    frame = frame.copy()
    status, action = [], []
    for row in frame.to_dict("records"):
        state, next_action = "AUTOMATED_VERIFICATION_INCONCLUSIVE", "CONFIRM_SOURCE_ENDPOINT_AND_SAMPLE"
        if row.get("sample_verified") is True and row["access_status"] == "AUTOMATED_OPEN":
            state, next_action = "VERIFIED_INSIDE_AOI", row["processing_priority"]
        elif row["access_type"] == "LOCAL_PROJECT_DATA" and row["access_status"] == "UNAVAILABLE":
            state, next_action = "INPUT_NOT_SUPPLIED", "SUPPLY_PROJECT_FILE_IF_AVAILABLE"
        elif row["access_status"] in {"AUTOMATED_AUTHENTICATION_REQUIRED", "ACCESS_RESTRICTED"}:
            state, next_action = "AUTHENTICATION_OR_LICENSE_REQUIRED", "PROVIDE_AUTHORIZED_ACCESS"
        elif row["access_status"] == "VERIFICATION_FAILED":
            state, next_action = "SERVICE_OR_ENDPOINT_FAILED", "RETRY_OR_CONFIRM_SOURCE_ENDPOINT"
        elif row["AOI_coverage_status"] == "NO_COVERAGE":
            state, next_action = "NO_COVERAGE", "RETAIN_COVERAGE_EVIDENCE"
        elif row["access_status"] == "MANUAL_DOWNLOAD_AVAILABLE":
            state, next_action = "MANUAL_DOWNLOAD_REQUIRED", "DOWNLOAD_SOURCE_FILE_THEN_RUN_AOI_TEST"
        elif row["valid_data_status"] == "NO_VALID_DATA":
            state, next_action = "NO_VALID_SAMPLE", "TEST_ANOTHER_DATE_OR_LOCATION"
        elif row.get("sample_kind") in {"CATALOGUE_RECORDS", "BBOX_COUNTS", "RENDERED_MAP"}:
            state, next_action = "METADATA_ONLY", "RUN_AOI_DATA_SAMPLE"
        status.append(state)
        action.append(next_action)
    frame["Stage_02_status"] = status
    frame["FINAL_STATUS"] = status
    frame["FINAL_ACTION"] = action
    frame["FINAL_EVIDENCE"] = frame["notes"] + " | " + frame["failure_reason"]
    return frame


def consolidate(raw, fao, gaez, registry):
    frame = strict_inventory(raw, registry)
    if len(fao) != len(PRIORITY_IDS) or fao.dataset_id.duplicated().any() or set(fao.dataset_id) != set(PRIORITY_IDS):
        raise ValueError("All eight FAO priority rows must be present exactly once")
    frame["Stage_02B_status"] = "NOT_APPLICABLE"
    frame["Stage_02B_evidence_json"] = "NOT_APPLICABLE"
    for row in fao.to_dict("records"):
        mask = frame.dataset_id.eq(row["dataset_id"])
        state, action = row["Stage_02B_status"], row["recommended_action"]
        confirmed = row["pixel_sample_confirmed"] is True
        if row["dataset_id"] == "FAO_GAEZ_V5_CURRENT":
            confirmed = bool(gaez_complete(gaez))
            state = "VERIFIED_INSIDE_AOI" if confirmed else "METADATA_ONLY"
            action = "USE_NEXT" if confirmed else "REVIEW_GAEZ_VERIFICATION_REPORT"
        elif state == "VERIFIED_INSIDE_AOI" and not confirmed:
            state, action = "LAYER_OR_SAMPLE_SELECTION_REQUIRED", "RUN_AOI_DATA_SAMPLE"
        if action in {"USE_NEXT", "USE_LATER"} and not confirmed:
            action = "RUN_AOI_DATA_SAMPLE"
        frame.loc[mask, "Stage_02B_status"] = state
        frame.loc[mask, "Stage_02B_evidence_json"] = json.dumps(row["evidence_json"])
        frame.loc[mask, "FINAL_STATUS"] = state
        frame.loc[mask, "FINAL_ACTION"] = action
        frame.loc[mask, "FINAL_EVIDENCE"] = row["verification_evidence"] + " | " + row["failure_reason"]
    check_inventory(frame, registry)
    if frame.FINAL_STATUS.isna().any() or frame.FINAL_STATUS.eq("").any():
        raise ValueError("Every dataset requires a final decision")
    if (frame.FINAL_ACTION.isin(["USE_NEXT", "USE_LATER"]) & frame.FINAL_STATUS.ne("VERIFIED_INSIDE_AOI")).any():
        raise ValueError("An unverified dataset was incorrectly marked ready")
    return frame


def result_html(frame, aoi, gaez, summary):
    m = folium.Map(location=[aoi.centroid[1], aoi.centroid[0]], tiles=None, height=360)
    folium.TileLayer("CartoDB positron", name="Light map").add_to(m)
    folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                     attr="Esri World Imagery", name="Satellite").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Streets").add_to(m)
    folium.GeoJson(aoi.wgs84.__geo_interface__, name="Parcel A",
                   style_function=lambda _: {"color": "#176b3a", "weight": 3, "fillOpacity": .08}).add_to(m)
    folium.LayerControl().add_to(m)
    x0, y0, x1, y1 = aoi.bounds
    m.fit_bounds([[y0, x0], [y1, x1]])
    ready = frame[frame.FINAL_STATUS.eq("VERIFIED_INSIDE_AOI")]
    cards = "".join(f'<div class="card"><b>{value}</b><br>{label}</div>' for label, value in (
        ("Sources reviewed", len(frame)), ("Sources with valid samples", len(ready)),
        ("GAEZ assets verified", f"{summary['gaez_assets_verified']}/16")))
    cols = ["dataset_name", "agricultural_theme", "spatial_resolution"]
    table = ready[cols].rename(columns=dict(zip(cols, ["Available data sample", "Agricultural use", "Resolution"])))
    pending = len(frame) - len(ready)
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>Stage 02 results</title>"
            "<style>body{font:15px Arial;color:#183d2c;max-width:1150px;margin:20px auto;padding:12px}"
            ".cards{display:flex;gap:12px;flex-wrap:wrap}.card{padding:18px;background:#eff6f1;border-radius:8px;flex:1}"
            ".card b{font-size:28px}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #dde6df}</style>"
            f"<h2>Stage 02 — Available agricultural data</h2>{m._repr_html_()}<div class='cards'>{cards}</div>"
            "<p>Google Earth Engine connected.</p>" + (table.to_html(index=False, escape=True, border=0) if len(ready) else
            "<p>No valid data samples were confirmed in this run.</p>") +
            f"<p>{pending} sources need further checks, access, supplied files, or later selection. Details are in the ZIP.</p>"
            "<p>These are sample checks. GAEZ cells retain their native resolution; a cell touching Parcel A does not provide field-scale detail.</p></html>")


def run_stage02(project_root, output_base=None):
    root = Path(project_root).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = Path(output_base or root / "outputs/stage02_runs") / stamp
    runner = DiscoveryRunner(root, run_directory=run_dir / "stage02a", progress=lambda _: None)
    runner.config["earth_engine_enabled"] = True
    runner.run_all()
    raw = runner.inventory.frame()
    strict = strict_inventory(raw, runner.registry)
    runner.write_outputs()
    write_table(strict, runner.output_dir, "data_inventory_strict")
    fao, gaez = run_fao_priority(runner, run_dir / "stage02b")
    final = consolidate(raw, fao, gaez, runner.registry)
    final_dir = run_dir / "final"
    write_table(final, final_dir, "final_data_inventory")
    summary = dict(registered_datasets=len(final), final_status_counts=final.FINAL_STATUS.value_counts().to_dict(),
                   sources_with_valid_samples=int(final.FINAL_STATUS.eq("VERIFIED_INSIDE_AOI").sum()),
                   ready_for_next_stage=int(final.FINAL_ACTION.eq("USE_NEXT").sum()),
                   gaez_assets_expected=16, gaez_assets_checked=len(gaez),
                   gaez_assets_verified=int(gaez.verification_status.eq("VERIFIED_INSIDE_AOI").sum()),
                   gaez_selection_complete=bool(gaez_complete(gaez)), fao_rows_resolved=len(fao),
                   earth_engine_connected=True, generated_at_utc=stamp, aoi_sha256=runner.aoi.checksum,
                   verification_scope="Minimal samples and metadata; not exhaustive data extraction or agricultural analysis")
    (final_dir / "metadata/final_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    html = result_html(final, runner.aoi, gaez, summary)
    dashboard = final_dir / "results.html"
    dashboard.write_text(html, encoding="utf-8")
    report = html.replace("</html>", "<h2>All source decisions</h2>" + final[[
        "dataset_name", "source_name", "FINAL_STATUS", "FINAL_ACTION", "FINAL_EVIDENCE"
    ]].to_html(index=False, escape=True, border=0) + "</html>")
    (final_dir / "final_stage02_report.html").write_text(report, encoding="utf-8")
    sources = [root / "requirements.txt", root / "requirements-lock.txt", root / "config/datasets.yml",
               root / "config/sources/gaez_v5_source_manifest.yml", root / "src/stage02_gaez_verification.py"]
    provenance = {p.relative_to(root).as_posix(): sha256_file(p) for p in sources}
    bundle_info = root / "bundle_manifest.json"
    if bundle_info.exists():
        provenance["bundle"] = json.loads(bundle_info.read_text())
    (final_dir / "metadata/source_checksums.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (final_dir / "metadata/environment.txt").write_text(subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"], text=True), encoding="utf-8")
    # Each run gets a new directory. Prior clips and reports can never leak into this ZIP.
    members = [p for p in sorted(run_dir.rglob("*")) if p.is_file() and "cache" not in p.relative_to(run_dir).parts]
    checksums = {p.relative_to(run_dir).as_posix(): sha256_file(p) for p in members}
    check_path = final_dir / "metadata/package_checksums.json"
    check_path.write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    archive = run_dir / "stage02_all_in_one_results.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as z:
        for path in members + [check_path]:
            z.write(path, path.relative_to(run_dir))
    return dict(archive=str(archive), dashboard=str(dashboard), summary=summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output-base", required=True)
    parser.add_argument("--result-path", required=True)
    args = parser.parse_args()
    import ee
    ee.Initialize(project=os.environ["EARTH_ENGINE_PROJECT"])
    ee.data.setDeadline(60000)
    if ee.String("Parcel A Stage 02").getInfo() != "Parcel A Stage 02":
        raise RuntimeError("Earth Engine connection could not be verified")
    result = run_stage02(args.root, args.output_base)
    Path(args.result_path).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
