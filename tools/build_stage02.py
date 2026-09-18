#!/usr/bin/env python3
"""Build/check the self-contained, single-cell Stage 02 notebook."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]


def bundle_payload():
    paths = [ROOT / name for name in ("requirements.txt", "requirements-lock.txt", "config/project.yml",
             "config/datasets.yml", "config/sources/gaez_v5_source_manifest.yml", "data/aoi/parcel_a.geojson")]
    paths += sorted((ROOT / "src").rglob("*.py"))
    return json.dumps({p.relative_to(ROOT).as_posix(): base64.b64encode(p.read_bytes()).decode("ascii")
                       for p in paths}, sort_keys=True, separators=(",", ":")).encode("utf-8")


def project_bundle():
    return base64.b64encode(zlib.compress(bundle_payload(), 9)).decode("ascii")


def build_notebook():
    bundle = project_bundle()
    literal = "\n".join(f'    "{bundle[i:i+100]}"' for i in range(0, len(bundle), 100))
    code = (ROOT / "tools/stage02_notebook_cell.py").read_text().replace("__PROJECT_BUNDLE_LITERAL__", literal)
    code = code.replace("__PROJECT_BUNDLE_SHA256__", hashlib.sha256(bundle_payload()).hexdigest())
    return {"cells": [
        {"cell_type": "markdown", "metadata": {}, "source": ["# Stage 02 — Agricultural data discovery\n", "\n",
            "Run the cell below. Approve Google access if asked. Your results and one ZIP will appear here.\n"]},
        {"cell_type": "code", "execution_count": None, "metadata": {"cellView": "form"},
         "outputs": [], "source": code.splitlines(keepends=True)}],
        "metadata": {"colab": {"name": "02_data_discovery.ipynb", "provenance": []},
                     "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build_notebook(), indent=2, ensure_ascii=False) + "\n"
    target = ROOT / "notebooks/02_data_discovery.ipynb"
    if args.check:
        if target.read_text() != text:
            raise SystemExit("Stage 02 notebook is stale. Run python tools/build_stage02.py and commit it.")
        print("Stage 02 notebook matches all bundled source files.")
    else:
        target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
