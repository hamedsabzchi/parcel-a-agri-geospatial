#!/usr/bin/env python3
"""Deterministic, self-contained Stage 04 notebook; no GitHub runtime clone."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT=Path(__file__).resolve().parents[1]


def bundle_payload():
    paths=[ROOT/'stage04/requirements-lock.txt']
    paths+=sorted((ROOT/'stage04/src/parcel_a_stage04').rglob('*.py'))
    paths+=sorted(p for p in (ROOT/'stage04/src/parcel_a_stage04/assets').iterdir() if p.suffix in {'.html','.css','.js','.json'})
    return json.dumps({p.relative_to(ROOT).as_posix():base64.b64encode(p.read_bytes()).decode() for p in paths},sort_keys=True,separators=(',',':')).encode()


def build_notebook():
    raw=bundle_payload();encoded=base64.b64encode(zlib.compress(raw,9)).decode()
    code=(ROOT/'tools/stage04_notebook_cell.py').read_text().replace('__BUNDLE_LITERAL__','\n'.join(f'    "{encoded[i:i+100]}"' for i in range(0,len(encoded),100)))
    code=code.replace('__BUNDLE_SHA256__',hashlib.sha256(raw).hexdigest())
    return dict(cells=[dict(cell_type='markdown',metadata={},source=['# Stage 04 — Future scenario summary\n','Run the cell. Upload your completed Stage 03 ZIP. View the scenario summary and download the results.\n']),
        dict(cell_type='code',execution_count=None,metadata={'cellView':'form'},outputs=[],source=code.splitlines(keepends=True))],
        metadata=dict(colab=dict(name='04_future_scenario_summary.ipynb',provenance=[]),kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python')),nbformat=4,nbformat_minor=5)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    text=json.dumps(build_notebook(),indent=2,ensure_ascii=False)+'\n';path=ROOT/'notebooks/04_future_scenario_summary.ipynb'
    if args.check:
        if path.read_text()!=text:raise SystemExit('Stage 04 notebook is stale: run python tools/build_stage04.py')
        print('Stage 04 notebook matches its isolated bundle.')
    else:path.write_text(text,encoding='utf-8')


if __name__=='__main__':main()
