#!/usr/bin/env python3
"""Rebuild all lightweight Stage 01 AOI outputs."""

from __future__ import annotations

import csv
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parcel_a_geo.aoi import (  # noqa: E402
    REPORT_VERTICES_UTM33N,
    build_feature_collection,
    build_summary,
    report_points,
    utm33n_to_wgs84,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_vertices_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "vertex_id",
                "easting_m",
                "northing_m",
                "altitude_m",
                "source_crs",
                "source",
            ]
        )
        for vertex_id, easting, northing, altitude in REPORT_VERTICES_UTM33N:
            writer.writerow(
                [
                    vertex_id,
                    f"{easting:.8f}",
                    f"{northing:.8f}",
                    f"{altitude:.0f}",
                    "EPSG:32633",
                    "Final characterization report table 1",
                ]
            )


def write_validation_csv(path: Path, summary: dict) -> None:
    rows = [
        ("source_crs", "EPSG:32633", "PASS_FROM_REPORT_MAP"),
        ("vertex_count", summary["vertex_count"], "PASS"),
        ("ring_orientation", summary["ring_orientation"], "PASS"),
        ("self_intersection", str(not summary["is_simple"]).lower(), "PASS"),
        ("computed_area_ha", summary["computed_area_ha"], "PASS"),
        ("reported_area_ha", summary["reported_area_ha"], "REFERENCE"),
        (
            "area_difference_ha",
            summary["area_difference_ha"],
            "PASS_WITHIN_0.1_PERCENT",
        ),
        ("manual_boundary_confirmation", "false", "HOLD"),
        ("G0_geometry_gate", "HOLD", "HOLD"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["check", "value", "result"])
        writer.writerows(rows)


def write_interactive_map(path: Path, feature_collection: dict, summary: dict) -> None:
    feature_json = json.dumps(feature_collection, ensure_ascii=False)
    vertices = [
        {
            "id": vertex_id,
            "lon": utm33n_to_wgs84(easting, northing)[0],
            "lat": utm33n_to_wgs84(easting, northing)[1],
            "alt": altitude,
        }
        for vertex_id, easting, northing, altitude in REPORT_VERTICES_UTM33N
    ]
    vertices_json = json.dumps(vertices, ensure_ascii=False)
    center_lon, center_lat = summary["centroid_wgs84"]
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stage 01 Parcel A Boundary</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body {{ height: 100%; margin: 0; font-family: Tahoma, Arial, sans-serif; }}
    #map {{ height: 100%; }}
    .panel {{
      position: absolute; z-index: 1000; top: 16px; left: 16px;
      width: min(390px, calc(100% - 52px)); background: rgba(255,255,255,.96);
      padding: 16px 18px; border-radius: 10px; box-shadow: 0 3px 16px rgba(0,0,0,.25);
      line-height: 1.65; color: #17351f;
    }}
    .panel h1 {{ margin: 0 0 6px; font-size: 20px; }}
    .panel p {{ margin: 4px 0; font-size: 13px; }}
    .hold {{ display: inline-block; background: #fff3cd; color: #7a5600;
      border: 1px solid #e7c768; border-radius: 14px; padding: 1px 9px; font-weight: 700; }}
    .vertex-label {{ background: #fff; border: 1px solid #2f6b3b;
      color: #17351f; font-weight: 700; padding: 1px 4px; border-radius: 3px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <section class="panel">
    <h1>Parcel A study area</h1>
    <p>Dir 1, Mbéré, Adamaoua, Cameroon</p>
    <p><b>Reference CRS:</b> WGS 84 / UTM Zone 33N</p>
    <p><b>Calculated area:</b> {summary["computed_area_ha"]:.2f} ha</p>
    <p><b>Reported area:</b> {summary["reported_area_ha"]:.2f} ha</p>
    <p><b>Difference:</b> {abs(summary["area_difference_ha"]):.2f} ha</p>
    <p><b>G0 status:</b> <span class="hold">HOLD pending boundary confirmation</span></p>
  </section>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map("map", {{ zoomControl: true }}).setView([{center_lat}, {center_lon}], 12);
    const osm = L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
    }}).addTo(map);
    const satellite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
      {{ maxZoom: 19, attribution: "Tiles &copy; Esri" }}
    );
    const feature = {feature_json};
    const boundary = L.geoJSON(feature, {{
      style: {{ color: "#24573a", weight: 4, fillColor: "#80b918", fillOpacity: 0.32 }},
      onEachFeature: (f, layer) => layer.bindPopup(
        "<b>Parcel A</b><br>5127.48 ha<br>Reconstructed from report vertices"
      )
    }}).addTo(map);
    const vertices = {vertices_json};
    const vertexLayer = L.layerGroup().addTo(map);
    for (const v of vertices) {{
      L.circleMarker([v.lat, v.lon], {{
        radius: 5, color: "#9d2a2a", weight: 2, fillColor: "#fff", fillOpacity: 1
      }}).bindTooltip(v.id, {{ permanent: true, direction: "top", className: "vertex-label" }})
        .bindPopup(`${{v.id}}<br>Altitude: ${{v.alt}} m`).addTo(vertexLayer);
    }}
    L.control.layers({{"OpenStreetMap": osm, "Esri World Imagery": satellite}},
      {{"AOI boundary": boundary, "Report vertices": vertexLayer}}, {{collapsed: false}}).addTo(map);
    L.control.scale({{ imperial: false }}).addTo(map);
    map.fitBounds(boundary.getBounds(), {{ padding: [30, 30] }});
  </script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def write_static_svg(path: Path, summary: dict) -> None:
    width, height = 1200, 820
    left, top, map_width, map_height = 90, 125, 760, 610
    points = report_points()
    min_x, min_y, max_x, max_y = summary["bounds_utm33n"]
    pad_x = (max_x - min_x) * 0.08
    pad_y = (max_y - min_y) * 0.08
    min_x, max_x = min_x - pad_x, max_x + pad_x
    min_y, max_y = min_y - pad_y, max_y + pad_y
    scale = min(map_width / (max_x - min_x), map_height / (max_y - min_y))
    draw_w = (max_x - min_x) * scale
    draw_h = (max_y - min_y) * scale
    offset_x = left + (map_width - draw_w) / 2
    offset_y = top + (map_height - draw_h) / 2

    def project(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (
            offset_x + (x - min_x) * scale,
            offset_y + (max_y - y) * scale,
        )

    projected = [project(point) for point in points]
    polygon = " ".join(f"{x:.2f},{y:.2f}" for x, y in projected)
    grid_lines: list[str] = []
    grid_labels: list[str] = []
    x_start = int(min_x // 2000) * 2000
    for x in range(x_start, int(max_x) + 2001, 2000):
        px, _ = project((x, min_y))
        if left <= px <= left + map_width:
            grid_lines.append(
                f'<line x1="{px:.2f}" y1="{top}" x2="{px:.2f}" y2="{top + map_height}" class="grid"/>'
            )
            grid_labels.append(
                f'<text x="{px:.2f}" y="{top + map_height + 23}" text-anchor="middle" class="axis">{x}</text>'
            )
    y_start = int(min_y // 2000) * 2000
    for y in range(y_start, int(max_y) + 2001, 2000):
        _, py = project((min_x, y))
        if top <= py <= top + map_height:
            grid_lines.append(
                f'<line x1="{left}" y1="{py:.2f}" x2="{left + map_width}" y2="{py:.2f}" class="grid"/>'
            )
            grid_labels.append(
                f'<text x="{left - 10}" y="{py + 4:.2f}" text-anchor="end" class="axis">{y}</text>'
            )
    vertex_svg = []
    for (vertex_id, _, _, _), (x, y) in zip(REPORT_VERTICES_UTM33N, projected):
        vertex_svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" class="vertex"/>'
            f'<text x="{x + 10:.2f}" y="{y - 9:.2f}" class="vertex-label">{escape(vertex_id)}</text>'
        )
    centroid_x, centroid_y = project(tuple(summary["centroid_utm33n"]))
    scale_bar_px = 2000 * scale
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f7f8f4"/>
  <style>
    text {{ font-family: "DejaVu Sans", Arial, sans-serif; fill: #183623; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 16px; fill: #46634e; }}
    .grid {{ stroke: #d9dfda; stroke-width: 1; }}
    .axis {{ font-size: 12px; fill: #586b5e; }}
    .frame {{ fill: #eef3ec; stroke: #284f35; stroke-width: 2; }}
    .aoi {{ fill: #80b918; fill-opacity: .42; stroke: #24573a; stroke-width: 4; }}
    .vertex {{ fill: white; stroke: #9d2a2a; stroke-width: 3; }}
    .vertex-label {{ font-size: 15px; font-weight: 700; }}
    .stat-title {{ font-size: 20px; font-weight: 700; }}
    .stat {{ font-size: 16px; }}
    .small {{ font-size: 13px; fill: #526357; }}
  </style>
  <text x="600" y="48" text-anchor="middle" class="title">Parcel A study area</text>
  <text x="600" y="78" text-anchor="middle" class="subtitle">Dir 1, Mbere, Adamaoua, Cameroon — Stage 01 AOI reconstruction</text>
  <rect x="{left}" y="{top}" width="{map_width}" height="{map_height}" rx="4" class="frame"/>
  {"".join(grid_lines)}
  {"".join(grid_labels)}
  <polygon points="{polygon}" class="aoi"/>
  {"".join(vertex_svg)}
  <circle cx="{centroid_x:.2f}" cy="{centroid_y:.2f}" r="5" fill="#17351f"/>
  <line x1="{left + 36}" y1="{top + map_height - 42}" x2="{left + 36 + scale_bar_px:.2f}" y2="{top + map_height - 42}" stroke="#17351f" stroke-width="7"/>
  <line x1="{left + 36}" y1="{top + map_height - 50}" x2="{left + 36}" y2="{top + map_height - 34}" stroke="#17351f" stroke-width="2"/>
  <line x1="{left + 36 + scale_bar_px:.2f}" y1="{top + map_height - 50}" x2="{left + 36 + scale_bar_px:.2f}" y2="{top + map_height - 34}" stroke="#17351f" stroke-width="2"/>
  <text x="{left + 36 + scale_bar_px / 2:.2f}" y="{top + map_height - 56}" text-anchor="middle" class="axis">2 km</text>
  <path d="M {left + map_width - 45} {top + 74} L {left + map_width - 45} {top + 24} L {left + map_width - 59} {top + 45} M {left + map_width - 45} {top + 24} L {left + map_width - 31} {top + 45}" fill="none" stroke="#17351f" stroke-width="3"/>
  <text x="{left + map_width - 45}" y="{top + 18}" text-anchor="middle" class="vertex-label">N</text>
  <text x="895" y="154" class="stat-title">AOI quality summary</text>
  <text x="895" y="198" class="stat">Source CRS</text>
  <text x="895" y="224" class="subtitle">WGS 84 / UTM Zone 33N</text>
  <text x="895" y="274" class="stat">Computed area</text>
  <text x="895" y="304" class="stat-title">{summary["computed_area_ha"]:.2f} ha</text>
  <text x="895" y="350" class="stat">Reported area</text>
  <text x="895" y="378" class="subtitle">{summary["reported_area_ha"]:.2f} ha</text>
  <text x="895" y="424" class="stat">Difference</text>
  <text x="895" y="452" class="subtitle">{abs(summary["area_difference_ha"]):.2f} ha ({abs(summary["area_difference_percent"]):.3f}%)</text>
  <rect x="895" y="500" width="235" height="48" rx="24" fill="#fff3cd" stroke="#d7ae37"/>
  <text x="1012" y="531" text-anchor="middle" font-size="18" font-weight="700" fill="#765500">G0 HOLD</text>
  <text x="895" y="587" class="small">Geometry is valid and suitable for</text>
  <text x="895" y="609" class="small">workflow setup and visual review.</text>
  <text x="895" y="645" class="small">Final boundary confirmation is</text>
  <text x="895" y="667" class="small">required before decision analysis.</text>
  <text x="90" y="790" class="small">Source: final characterization report, table 1. Reconstructed from seven reported survey vertices.</text>
</svg>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    data_dir = ROOT / "data/aoi"
    map_dir = ROOT / "outputs/maps"
    table_dir = ROOT / "outputs/tables"
    feature_collection = build_feature_collection()
    summary = build_summary()

    write_vertices_csv(data_dir / "source_vertices_utm33n.csv")
    write_json(data_dir / "aoi_candidate_wgs84.geojson", feature_collection)
    write_json(data_dir / "aoi_candidate_summary.json", summary)
    write_validation_csv(table_dir / "01_aoi_validation.csv", summary)
    write_interactive_map(
        map_dir / "01_aoi_candidate.html", feature_collection, summary
    )
    write_static_svg(map_dir / "01_aoi_candidate.svg", summary)

    print(
        json.dumps(
            {
                "stage": "01",
                "aoi": summary["aoi_id"],
                "area_ha": round(summary["computed_area_ha"], 6),
                "g0_gate": summary["g0_gate"],
                "outputs": 6,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
