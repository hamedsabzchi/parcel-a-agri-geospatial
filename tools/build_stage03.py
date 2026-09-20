#!/usr/bin/env python3
"""Build/check the isolated self-contained Stage 03 notebook."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT=Path(__file__).resolve().parents[1]


def bundle_payload():
    paths=[ROOT/p for p in ("stage03/requirements-lock.txt","config/datasets.yml",
        "config/sources/gaez_v5_source_manifest.yml","data/aoi/parcel_a.geojson","docs/stage03_methodology.md","docs/stage03_maize_methodology.md","docs/stage03_maize_traceability.md",
        "docs/source_guides/stage03_maize_03_1_to_03_23.txt")]
    paths += sorted((ROOT/"stage03/src/parcel_a_stage03").rglob("*.py"))
    paths += sorted(p for p in (ROOT/"stage03/src/parcel_a_stage03/assets").iterdir() if p.suffix in {".html",".js",".css",".txt"})
    paths += sorted(p for p in (ROOT/"config/stage03").rglob("*") if p.suffix in {".yml",".json",".sld"})
    return json.dumps({p.relative_to(ROOT).as_posix():base64.b64encode(p.read_bytes()).decode() for p in paths},
                      sort_keys=True,separators=(",",":")).encode()


def build_notebook():
    raw=bundle_payload();bundle=base64.b64encode(zlib.compress(raw,9)).decode()
    code=(ROOT/"tools/stage03_notebook_cell.py").read_text().replace("__BUNDLE_LITERAL__","\n".join(f'    "{bundle[i:i+100]}"' for i in range(0,len(bundle),100)))
    code=code.replace("__BUNDLE_SHA256__",hashlib.sha256(raw).hexdigest())
    return dict(cells=[dict(cell_type="markdown",metadata={},source=["# Stage 03 — Maps, tables and graphs\n","Run the cell. Supply your completed Stage 02 or Stage 03 ZIP. Approve Google access if asked. Download your results as one ZIP.\n"]),
        dict(cell_type="code",execution_count=None,metadata={"cellView":"form"},outputs=[],source=code.splitlines(keepends=True))],
        metadata=dict(colab=dict(name="03_data_inventory_visualization.ipynb",provenance=[]),
            kernelspec=dict(display_name="Python 3",language="python",name="python3"),language_info=dict(name="python")),nbformat=4,nbformat_minor=5)


def main():
    p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");args=p.parse_args()
    text=json.dumps(build_notebook(),indent=2,ensure_ascii=False)+"\n"
    path=ROOT/"notebooks/03_data_inventory_visualization.ipynb"
    if args.check:
        if path.read_text()!=text:raise SystemExit("Stage 03 notebook is stale; run python tools/build_stage03.py")
        print("Stage 03 notebook matches its explicit isolated bundle.")
    else:path.write_text(text,encoding="utf-8")


if __name__=="__main__":main()
