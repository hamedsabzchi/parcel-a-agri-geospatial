"""Concise Stage 02 HTML and map outputs."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import folium
import pandas as pd

from .inventory import Inventory
from .validation import AOIContext


COVERAGE_COLORS = {
    "FULL_COVERAGE": "#238b45",
    "PARTIAL_COVERAGE": "#f0ad4e",
    "NO_COVERAGE": "#c62828",
    "COVERAGE_UNKNOWN": "#777777",
}


def _table(frame: pd.DataFrame) -> str:
    columns = [
        "dataset_name",
        "AOI_coverage_status",
        "valid_data_status",
        "access_status",
        "processing_priority",
    ]
    if frame.empty:
        return "<p>None.</p>"
    return frame[columns].to_html(index=False, escape=True, border=0, classes="inventory")


def _manual_table(frame: pd.DataFrame, aoi: AOIContext) -> str:
    if frame.empty:
        return "<p>None.</p>"
    bbox = ", ".join(f"{value:.6f}" for value in aoi.bounds)
    rows = []
    for _, row in frame.iterrows():
        url = str(row["catalogue_url"])
        safe_url = escape(url, quote=True)
        link = (
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">Official source</a>'
            if url not in {"", "UNKNOWN", "LOCAL_PROJECT_DATA"}
            else escape(url or "UNKNOWN")
        )
        if row["access_status"] == "AUTOMATED_AUTHENTICATION_REQUIRED":
            action = "Provide the documented account or project credential, then rerun the minimal AOI check."
        elif row["access_status"] == "UNAVAILABLE":
            action = "Supply the referenced local project file, then rerun Stage 02."
        else:
            action = (
                f"Open the official source, search the AOI bounding box ({bbox}), and inspect only "
                "the smallest available sample or tile."
            )
        rows.append(
            "<tr>"
            f"<td>{escape(str(row['dataset_name']))}</td>"
            f"<td>{escape(str(row['AOI_coverage_status']))}</td>"
            f"<td>{escape(str(row['access_status']))}</td>"
            f"<td>{link}</td>"
            f"<td>{escape(action)}</td>"
            "</tr>"
        )
    return (
        '<table class="inventory"><thead><tr><th>Dataset</th><th>Coverage</th>'
        "<th>Access</th><th>Link</th><th>Required action</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def write_html_report(
    inventory: Inventory, aoi: AOIContext, path: str | Path
) -> Path:
    frame = inventory.frame()
    counts = inventory.summary()
    use_next = frame[frame["processing_priority"] == "USE_NEXT"]
    fao = frame[frame["dataset_id"].str.startswith("FAO_")]
    non_fao = frame[~frame["source_group"].isin(["FAO", "Future climate"])]
    future = frame[frame["source_group"] == "Future climate"]
    manual = frame[frame["processing_priority"] == "NEEDS_MANUAL_REVIEW"]
    no_coverage = frame[frame["AOI_coverage_status"] == "NO_COVERAGE"]
    access_problems = frame[
        frame["access_status"].isin(
            ["ACCESS_RESTRICTED", "AUTOMATED_AUTHENTICATION_REQUIRED", "VERIFICATION_FAILED"]
        )
    ]
    summary_cards = "".join(
        f"<li><strong>{escape(label.replace('_', ' ').title())}:</strong> {value}</li>"
        for label, value in counts.items()
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage 02 Data Discovery Report</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#1f2d24}}
h1,h2{{color:#000}} ul{{line-height:1.7}} table{{border-collapse:collapse;width:100%;font-size:13px}}
th{{background:#244a35;color:#fff;text-align:left}} th,td{{padding:8px;border:1px solid #d9d9d9}}
tr:nth-child(even){{background:#f4f7f5}} .meta{{color:#46564c}}
</style></head><body>
<h1>Stage 02 Agricultural Data Discovery for Parcel A</h1>
<h2>1 AOI summary</h2><p class="meta">AOI: {escape(aoi.identifier)} | Bounds: {', '.join(f'{v:.6f}' for v in aoi.bounds)} | Checksum: {aoi.checksum}</p>
<h2>2 Discovery summary</h2><ul>{summary_cards}</ul>
<h2>3 Recommended datasets for Stage 03</h2>{_table(use_next)}
<h2>4 FAO datasets</h2>{_table(fao)}
<h2>5 Non FAO datasets</h2>{_table(non_fao)}
<h2>6 Future climate datasets</h2>{_table(future)}
<h2>7 Datasets requiring manual verification</h2>{_manual_table(manual, aoi)}
<h2>8 Datasets with no AOI coverage</h2>{_table(no_coverage)}
<h2>9 Access or authentication problems</h2>{_table(access_problems)}
<h2>10 Proposed Stage 03 download plan</h2><p>Download only datasets marked USE_NEXT, preserving native resolution and source metadata.</p>
</body></html>"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def write_coverage_map(
    inventory: Inventory,
    registry: list[dict[str, Any]],
    aoi: AOIContext,
    path: str | Path,
) -> Path:
    center = [aoi.centroid[1], aoi.centroid[0]]
    result_map = folium.Map(location=center, zoom_start=11, tiles=None)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Light Gray Canvas",
        name="Light map",
        show=True,
    ).add_to(result_map)
    folium.GeoJson(
        data=aoi.wgs84.__geo_interface__,
        name="Parcel A",
        style_function=lambda _: {"color": "#124f2f", "weight": 4, "fillOpacity": 0.08},
    ).add_to(result_map)
    folium.CircleMarker(center, radius=5, color="#111", fill=True, tooltip="AOI centroid").add_to(result_map)

    by_id = {record["dataset_id"]: record for record in registry}
    for row in inventory.records:
        source = by_id.get(str(row["dataset_id"]), {})
        bounds = source.get("expected_bbox")
        status = str(row["AOI_coverage_status"])
        name = str(row["dataset_name"])
        popup = (
            f"<b>{escape(name)}</b><br>Coverage: {escape(status)}"
            f"<br>Resolution: {escape(str(row['spatial_resolution']))}"
            f"<br>Time: {escape(str(row['earliest_date']))} to {escape(str(row['latest_date']))}"
            f"<br>Access: {escape(str(row['access_status']))}"
            f"<br>Validation: {escape(str(row['valid_data_status']))}"
        )
        if isinstance(bounds, list) and len(bounds) == 4 and bounds != [-180, -90, 180, 90]:
            folium.Rectangle(
                bounds=[[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                color=COVERAGE_COLORS.get(status, "#777"),
                weight=2,
                fill=False,
                tooltip=name,
                popup=popup,
            ).add_to(result_map)
        elif source.get("expected_spatial_coverage") == "Global" or bounds == [-180, -90, 180, 90]:
            folium.FeatureGroup(name=f"Global: {name}", show=False).add_to(result_map)

    folium.LayerControl(collapsed=True).add_to(result_map)
    minx, miny, maxx, maxy = aoi.bounds
    result_map.fit_bounds([[miny, minx], [maxy, maxx]])
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    result_map.save(target)
    return target
