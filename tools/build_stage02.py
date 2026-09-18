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
    setup = r'''
#@title Setup
from pathlib import Path
import base64
import json
import os
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
print("Setup complete")
'''.replace("__PROJECT_BUNDLE_LITERAL__", bundle_literal(project_bundle()))

    return {
        "cells": [
            markdown("# Stage 02 - Agricultural Data Discovery for Parcel A"),
            markdown("## 1 Setup"),
            code(setup),
            markdown("## 2 Load Parcel A"),
            code(
                r'''
#@title Load Parcel A
import folium
from IPython.display import display
from parcel_a_geo.config import load_project_config, project_path
from parcel_a_geo.validation import load_aoi

project_config = load_project_config(PROJECT_ROOT / "config/project.yml")
aoi = load_aoi(
    project_path(PROJECT_ROOT, project_config["aoi_path"]),
    project_config["aoi_identifier"],
)
aoi_map = folium.Map(location=[aoi.centroid[1], aoi.centroid[0]], zoom_start=11)
folium.GeoJson(
    aoi.wgs84.__geo_interface__,
    name="Parcel A",
    style_function=lambda _: {"color": "#176b3a", "weight": 4, "fillOpacity": 0.10},
).add_to(aoi_map)
minx, miny, maxx, maxy = aoi.bounds
aoi_map.fit_bounds([[miny, minx], [maxy, maxx]])
display(aoi_map)
'''
            ),
            markdown("## 3 Load dataset registry"),
            code(
                r'''
#@title Load dataset registry
import pandas as pd
from parcel_a_geo.config import load_dataset_registry

registry = load_dataset_registry(PROJECT_ROOT / "config/datasets.yml")
registry_summary = (
    pd.DataFrame(registry)
    .groupby("source_group", as_index=False)
    .size()
    .rename(columns={"size": "datasets"})
)
display(registry_summary)
'''
            ),
            markdown("## 4 Optional Earth Engine connection"),
            code(
                r'''
#@title Optional Earth Engine connection
ENABLE_EARTH_ENGINE = False #@param {type:"boolean"}

if ENABLE_EARTH_ENGINE:
    try:
        import ee
        project = os.getenv("EARTH_ENGINE_PROJECT", "")
        try:
            from google.colab import userdata
            project = project or userdata.get("EARTH_ENGINE_PROJECT")
        except Exception:
            pass
        if not project:
            raise RuntimeError("EARTH_ENGINE_PROJECT is not configured")
        os.environ["EARTH_ENGINE_PROJECT"] = project
        try:
            ee.Initialize(project=project)
        except Exception:
            ee.Authenticate()
            ee.Initialize(project=project)
        print("Earth Engine connected")
    except Exception as error:
        ENABLE_EARTH_ENGINE = False
        print(f"Earth Engine skipped: {type(error).__name__}. Add the Colab secret and rerun when needed.")
else:
    print("Earth Engine checks skipped")
'''
            ),
            markdown("## 5 Check FAO sources"),
            code(
                r'''
#@title Check FAO sources
from parcel_a_geo.discovery import DiscoveryRunner

runner = DiscoveryRunner(PROJECT_ROOT)
runner.config["earth_engine_enabled"] = ENABLE_EARTH_ENGINE
runner.run_fao()
'''
            ),
            markdown("## 6 Check non FAO sources"),
            code(
                r'''
#@title Check non FAO sources
runner.run_non_fao()
'''
            ),
            markdown("## 7 Check future climate sources"),
            code(
                r'''
#@title Check future climate sources
runner.run_future_climate()
'''
            ),
            markdown("## 8 Build inventory"),
            code(
                r'''
#@title Build inventory
inventory_table = runner.inventory.frame()
print(f"Inventory rows: {len(inventory_table)}")
'''
            ),
            markdown("## 9 Display summary"),
            code(
                r'''
#@title Display summary
summary = pd.DataFrame([runner.inventory.summary()])
display(summary)
display(
    inventory_table[
        [
            "dataset_id",
            "AOI_coverage_status",
            "valid_data_status",
            "access_status",
            "processing_priority",
        ]
    ]
)
'''
            ),
            markdown("## 10 Save outputs"),
            code(
                r'''
#@title Save outputs
from IPython.display import FileLink

output_paths = runner.write_outputs()
for name, path in output_paths.items():
    print(name)
    display(FileLink(str(path)))
print("SUCCESS: Stage 02 data discovery completed")
'''
            ),
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
