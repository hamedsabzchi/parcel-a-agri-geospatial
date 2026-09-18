"""Additional FAO discovery; metadata and data evidence remain separate."""
from __future__ import annotations

import json
import math
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
from stage02_gaez_verification import gaez_complete, run_gaez_stage02_verification
from .metadata import utc_now

PRIORITY_IDS = (
    "FAO_GAEZ_V5_CURRENT", "FAO_GAEZ_V5_FUTURE", "FAO_WAPOR_V3_L2", "FAO_WAPOR_V3_L3",
    "FAO_SOILFER", "FAO_CROPSUIT", "FAO_CAVA", "FAO_ASIS",
)


def _record(dataset_id):
    return dict(dataset_id=dataset_id, Stage_02B_status="METADATA_ONLY",
                pixel_sample_confirmed=False, catalogue_verified=False,
                verification_evidence="No AOI data sample confirmed", evidence_json={},
                failure_reason="NONE", recommended_action="SELECT_LAYER_THEN_PIXEL_TEST",
                verified_at_utc=utc_now())


def _ckan(client, identifier):
    errors = []
    for prefix in ("https://data.apps.fao.org/catalog/api/3/action", "https://data.apps.fao.org/api/3/action"):
        try:
            url = prefix + "/package_show"
            payload = client.request("GET", url, params={"id": identifier}).json()
            if payload.get("success") and isinstance(payload.get("result"), dict):
                return payload["result"], url
            errors.append(str(payload.get("error", "Record unavailable")))
        except Exception as error:
            errors.append(str(error))
    raise RuntimeError("; ".join(errors))


def _wapor_sample(aoi):
    import ee
    geometry = ee.Geometry(aoi.geometry.__geo_interface__)
    attempts = []
    for cid in ("projects/UNFAO/wapor/v3/L2-AETI-D", "projects/UNFAO/wapor/v3/L2-NPP-D", "projects/UNFAO/wapor/v3/L2-T-D"):
        try:
            collection = ee.ImageCollection(cid).filterBounds(geometry)
            count = int(collection.size().getInfo())
            if not count:
                attempts.append({"collection": cid, "image_count": 0})
                continue
            image = ee.Image(collection.sort("system:time_start", False).first())
            scale = image.select(0).projection().nominalScale().getInfo()
            sample = image.reduceRegion(reducer=ee.Reducer.first(), geometry=geometry,
                                        scale=scale, maxPixels=1000000).getInfo() or {}
            valid = {k: v for k, v in sample.items() if isinstance(v, (int, float)) and math.isfinite(v)}
            evidence = {"collection": cid, "image_count": count, "image_id": image.id().getInfo(),
                        "sample": sample, "native_scale_metres": scale}
            attempts.append(evidence)
            if valid:
                return True, attempts
        except Exception as error:
            attempts.append({"collection": cid, "error": str(error)})
    return False, attempts


def run_fao_priority(runner, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = runner.project_root / "config/sources/gaez_v5_source_manifest.yml"
    gaez = run_gaez_stage02_verification(runner.aoi.wgs84, manifest, out / "gaez")
    complete = bool(gaez_complete(gaez))
    verified = int(gaez.verification_status.eq("VERIFIED_INSIDE_AOI").sum())
    current = _record("FAO_GAEZ_V5_CURRENT")
    current.update(catalogue_verified=True, pixel_sample_confirmed=complete,
                   Stage_02B_status="VERIFIED_INSIDE_AOI" if complete else "METADATA_ONLY",
                   recommended_action="USE_NEXT" if complete else "REVIEW_GAEZ_VERIFICATION_REPORT",
                   verification_evidence=f"{verified}/16 selected assets passed native-grid AOI tests (all_touched=True).",
                   evidence_json={"assets_expected": 16, "assets_checked": len(gaez), "assets_verified": verified,
                                  "report": "gaez/gaez_verification_report.json", "all_touched": True})
    future = _record("FAO_GAEZ_V5_FUTURE")
    future.update(catalogue_verified=True, Stage_02B_status="DEFERRED",
                  recommended_action="DEFER_UNTIL_CURRENT_MAIZE_PROTOTYPE_APPROVAL",
                  verification_evidence="GAEZ CMIP6 assets and other crops remain deferred; this prototype verifies current maize only.")
    rows = [current, future]
    for ident in PRIORITY_IDS[2:]:
        row = _record(ident)
        try:
            if ident == "FAO_WAPOR_V3_L2":
                ok, attempts = _wapor_sample(runner.aoi)
                row.update(pixel_sample_confirmed=ok, catalogue_verified=True, evidence_json=attempts,
                           Stage_02B_status="VERIFIED_INSIDE_AOI" if ok else "AUTOMATED_VERIFICATION_INCONCLUSIVE",
                           recommended_action="USE_NEXT" if ok else "CONFIRM_WAPOR_L2_COLLECTION",
                           verification_evidence="Valid WaPOR L2 AOI sample; see recorded product and date." if ok else
                           "No valid sample from the three configured Level 2 candidates; this does not prove no coverage.")
            elif ident == "FAO_WAPOR_V3_L3":
                package, url = _ckan(runner.client, "wapor-v-3")
                row.update(catalogue_verified=True, evidence_json={"endpoint": url, "resources": package.get("resources", [])},
                           recommended_action="CONFIRM_LEVEL_3_PROJECT_FOOTPRINT",
                           verification_evidence="WaPOR catalogue accessible; exact Level 3 coverage of Parcel A remains unconfirmed.")
            elif ident in {"FAO_SOILFER", "FAO_CROPSUIT"}:
                package, url = _ckan(runner.client, "soilfer-app")
                resources = package.get("resources", [])
                services = []
                for resource in resources:
                    endpoint = resource.get("url") or resource.get("access_url")
                    fmt = str(resource.get("format", "")).upper()
                    if not endpoint or fmt not in {"WMS", "WMTS"}:
                        continue
                    try:
                        xml = runner.client.request("GET", endpoint, params={"service": fmt, "request": "GetCapabilities"}).text
                        root = ElementTree.fromstring(xml)
                        if "capabilities" not in root.tag.lower():
                            raise ValueError("Not an OGC capabilities document")
                        layers = [x.text for x in root.iter() if x.tag.split("}")[-1] in {"Name", "Identifier"} and x.text]
                        services.append({"url": endpoint, "service": fmt, "layers": layers})
                    except Exception as error:
                        services.append({"url": endpoint, "error": str(error)})
                row.update(catalogue_verified=True, Stage_02B_status="LAYER_OR_SAMPLE_SELECTION_REQUIRED",
                           evidence_json={"endpoint": url, "resources": resources, "services": services},
                           recommended_action="SELECT_CROPSUIT_LAYER" if ident == "FAO_CROPSUIT" else "SELECT_SOILFER_LAYER",
                           verification_evidence=f"{len(resources)} catalogue resources discovered. Capabilities are metadata, not valid soil pixels.")
            elif ident == "FAO_CAVA":
                # Dependency metadata is enough for discovery; installing the SDK is not data verification.
                package = runner.client.request("GET", "https://pypi.org/pypi/cavapy/json").json()["info"]
                row.update(catalogue_verified=True, recommended_action="RUN_MINIMAL_CAVA_SLICE",
                           evidence_json={k: package.get(k) for k in ("name", "version", "requires_python", "requires_dist", "project_urls")},
                           verification_evidence="CAVA SDK metadata recorded. ERA5/CORDEX data slice, models and scenarios still require an AOI query.")
            elif ident == "FAO_ASIS":
                payload = runner.client.request("GET", "https://www.arcgis.com/sharing/rest/search", params={
                    "q": 'ASIS "Agricultural Stress Index"', "f": "json", "num": 100}).json()
                items = payload.get("results", [])
                if not items:
                    raise ValueError("No ASIS catalogue candidates returned")
                row.update(catalogue_verified=True, recommended_action="SELECT_ASIS_INDICATOR_AND_DATE",
                           evidence_json={"candidates": items, "publisher_verified": False},
                           verification_evidence=f"{len(items)} catalogue candidates. Confirm FAO publisher, indicator and date before a pixel test.")
        except Exception as error:
            row.update(Stage_02B_status="SERVICE_OR_ENDPOINT_FAILED", failure_reason=f"{type(error).__name__}: {error}",
                       recommended_action="RETRY_OR_CONFIRM_SOURCE_ENDPOINT")
        rows.append(row)
    frame = pd.DataFrame(rows)
    write_table(frame, out, "fao_priority_inventory")
    (out / "stage02b_report.html").write_text(frame.drop(columns="evidence_json").to_html(index=False, escape=True), encoding="utf-8")
    (out / "logs").mkdir(exist_ok=True)
    (out / "logs/stage02b_log.txt").write_text("\n".join(f"{r['dataset_id']}: {r['Stage_02B_status']} | {r['failure_reason']}" for r in rows), encoding="utf-8")
    return frame, gaez


def write_table(frame, out, name):
    out = Path(out)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(exist_ok=True)
    frame.to_csv(out / "tables" / f"{name}.csv", index=False)
    frame.to_excel(out / "tables" / f"{name}.xlsx", index=False)
    (out / "metadata" / f"{name}.json").write_text(frame.to_json(orient="records", indent=2), encoding="utf-8")
