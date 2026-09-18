#!/usr/bin/env python3
"""Build the Stage 02 Google Colab notebook."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import zlib


ROOT = Path(__file__).resolve().parents[1]


def project_bundle() -> str:
    """Return a deterministic compressed bundle required by the private-repository notebook."""

    paths = [
        ROOT / "requirements.txt",
        ROOT / "config/project.yml",
        ROOT / "config/datasets.yml",
        ROOT / "data/aoi/parcel_a.geojson",
        *sorted((ROOT / "src/parcel_a_geo").rglob("*.py")),
    ]
    payload = {
        path.relative_to(ROOT).as_posix(): base64.b64encode(path.read_bytes()).decode("ascii")
        for path in paths
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(zlib.compress(serialized, level=9)).decode("ascii")


def bundle_literal(value: str, width: int = 100) -> str:
    return "\n".join(f'    "{value[index:index + width]}"' for index in range(0, len(value), width))


def markdown(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": (source.strip() + "\n").splitlines(keepends=True),
    }


def code(source: str, form: bool = True) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"cellView": "form"} if form else {},
        "outputs": [],
        "source": (source.strip() + "\n").splitlines(keepends=True),
    }


def build_notebook() -> dict:
    workflow = r'''
#@title Run Stage 02
from pathlib import Path
import base64
import json
import os
import shutil
import subprocess
import sys
import zlib

PROJECT_BUNDLE_B64 = (
__PROJECT_BUNDLE_LITERAL__
)

PROJECT_ROOT = Path.cwd()
if not (PROJECT_ROOT / "config/project.yml").exists():
    base_directory = Path("/content") if Path("/content").exists() else Path.cwd()
    PROJECT_ROOT = base_directory / "parcel-a-agri-geospatial"
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    bundled_files = json.loads(
        zlib.decompress(base64.b64decode(PROJECT_BUNDLE_B64)).decode("utf-8")
    )
    for relative_path, encoded_content in bundled_files.items():
        target = PROJECT_ROOT / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(encoded_content))

subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-q", "-r", str(PROJECT_ROOT / "requirements.txt")]
)
sys.path.insert(0, str(PROJECT_ROOT / "src"))
for module_name in list(sys.modules):
    if module_name == "parcel_a_geo" or module_name.startswith("parcel_a_geo."):
        del sys.modules[module_name]

import ee
import folium
from IPython.display import HTML, clear_output, display
from parcel_a_geo.config import load_dataset_registry, load_project_config, project_path
from parcel_a_geo.discovery import DiscoveryRunner
from parcel_a_geo.validation import load_aoi

EARTH_ENGINE_PROJECT = os.getenv("EARTH_ENGINE_PROJECT", "practical-proxy-441422-n6")
os.environ["EARTH_ENGINE_PROJECT"] = EARTH_ENGINE_PROJECT
try:
    ee.Initialize(project=EARTH_ENGINE_PROJECT)
except Exception:
    ee.Authenticate(auth_mode="notebook", force=True)
    ee.Initialize(project=EARTH_ENGINE_PROJECT)

if ee.String("Parcel A Stage 02").getInfo() != "Parcel A Stage 02":
    raise RuntimeError("Earth Engine server connection could not be verified")

project_config = load_project_config(PROJECT_ROOT / "config/project.yml")
aoi = load_aoi(
    project_path(PROJECT_ROOT, project_config["aoi_path"]),
    project_config["aoi_identifier"],
)
registry = load_dataset_registry(PROJECT_ROOT / "config/datasets.yml")

runner = DiscoveryRunner(PROJECT_ROOT, progress=lambda _: None)
runner.config["earth_engine_enabled"] = True
runner.run_all()
inventory_table = runner.inventory.frame()
output_paths = runner.write_outputs()
archive_path = Path(
    shutil.make_archive(
        str(PROJECT_ROOT / "outputs/stage02_results"),
        "zip",
        root_dir=runner.output_dir,
    )
)

clear_output(wait=True)

aoi_map = folium.Map(location=[aoi.centroid[1], aoi.centroid[0]], zoom_start=11)
folium.GeoJson(
    aoi.wgs84.__geo_interface__,
    name="Parcel A",
    style_function=lambda _: {"color": "#176b3a", "weight": 4, "fillOpacity": 0.10},
).add_to(aoi_map)
minx, miny, maxx, maxy = aoi.bounds
aoi_map.fit_bounds([[miny, minx], [maxy, maxx]])
display(aoi_map)

verified = inventory_table["valid_data_status"].isin(["VALID_DATA", "VALID_RECORDS"])
ready_next = inventory_table["processing_priority"] == "USE_NEXT"
ready_later = inventory_table["processing_priority"] == "USE_LATER"
pending = ~verified

cards = [
    ("Sources reviewed", len(inventory_table)),
    ("Verified inside Parcel A", int(verified.sum())),
    ("Ready for the next stage", int(ready_next.sum())),
    ("Require further verification", int(pending.sum())),
]
card_html = "".join(
    f'<div style="flex:1;min-width:160px;padding:16px;border:1px solid #d9e2dc;'
    f'border-radius:8px;background:#f6faf7"><div style="font-size:28px;font-weight:700;'
    f'color:#176b3a">{value}</div><div>{label}</div></div>'
    for label, value in cards
)
display(
    HTML(
        '<p style="padding:10px;background:#e8f5e9;color:#176b3a;border-radius:6px">'
        '<b>Google Earth Engine connected.</b> All registered sources were checked.</p>'
        f'<h2>Stage 02 result</h2><div style="display:flex;gap:12px;flex-wrap:wrap">{card_html}</div>'
    )
)

recommended = inventory_table[ready_next | ready_later][
    ["dataset_name", "agricultural_theme", "spatial_resolution", "processing_priority"]
].copy()
recommended["processing_priority"] = recommended["processing_priority"].map(
    {"USE_NEXT": "Use next", "USE_LATER": "Useful later"}
)
recommended = recommended.rename(
    columns={
        "dataset_name": "Verified dataset",
        "agricultural_theme": "Agricultural use",
        "spatial_resolution": "Resolution",
        "processing_priority": "Decision",
    }
)
display(HTML("<h3>Verified datasets for the analysis pipeline</h3>"))
display(HTML(recommended.to_html(index=False, escape=True, border=0)))

if pending.any():
    display(
        HTML(
            f"<p><b>{int(pending.sum())} sources are not yet confirmed.</b> "
            "They require a supplied project file, manual access, or a source-specific check. "
            "They are not treated as available data.</p>"
        )
    )

display(HTML("<h3>Results package ready</h3><p>The ZIP contains the report, map, inventory and technical log.</p>"))
try:
    from google.colab import files
    files.download(str(archive_path))
except ImportError:
    from IPython.display import FileLink
    display(FileLink(str(archive_path)))
print("SUCCESS: Stage 02 data discovery completed")
'''.replace("__PROJECT_BUNDLE_LITERAL__", bundle_literal(project_bundle()))

    return {
        "cells": [
            markdown(
                "# Stage 02 - Agricultural Data Discovery for Parcel A\n\n"
                "Run the single cell below. The first run may ask you to approve Google Earth Engine access."
            ),
            code(workflow),
        ],
        "metadata": {
            "colab": {"name": "02_data_discovery.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    path = ROOT / "notebooks/02_data_discovery.ipynb"
    path.write_text(json.dumps(build_notebook(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
