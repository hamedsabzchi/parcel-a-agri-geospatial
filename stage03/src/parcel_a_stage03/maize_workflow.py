"""One-run upgrade: reuse a verified Stage 03 package, or build its core from Stage 02."""
from __future__ import annotations
import json
from pathlib import Path
from zipfile import ZipFile
import yaml
from .common import relative_file,sha256
from .inputs import unpack
from .pipeline import prepare,run as core_run


def is_stage03(source):
    source=Path(source)
    if source.is_dir():return (source/'metadata/package_checksums.json').is_file()
    with ZipFile(source) as archive:return 'metadata/package_checksums.json' in archive.namelist()


def verify_package(root):
    checks=json.loads(relative_file(root,'metadata/package_checksums.json').read_text())
    files={p.relative_to(root).as_posix() for p in Path(root).rglob('*') if p.is_file()}
    if files-set(checks)!={'metadata/package_checksums.json'}:raise ValueError('Stage 03 package contains missing or unregistered files')
    for name,digest in checks.items():
        if sha256(relative_file(root,name))!=digest:raise ValueError('Stage 03 checksum mismatch: '+name)
    return checks


def baseline(root,project):
    root=Path(root);project=Path(project);verify_package(root)
    if (root/'metadata/core_baseline').is_dir():root=root/'metadata/core_baseline';verify_package(root)
    summary=json.loads(relative_file(root,'metadata/run_summary.json').read_text())
    qa=json.loads(relative_file(root,'qa/stage03_validation_report.json').read_text())
    if summary['outcome']=='INCOMPLETE' or not all(qa['checks'].values()):raise ValueError('The core Stage 03 package is incomplete; use a completed Stage 02 package to rebuild it')
    if summary.get('source_count')!=48 or summary.get('gaez_extracted')!=16:raise ValueError('Stage 03 must preserve the original 48 sources and 16 required GAEZ layers')
    if sha256(relative_file(root,'clipped_data/vectors/parcel_a.geojson'))!=sha256(project/'data/aoi/parcel_a.geojson'):raise ValueError('Stage 03 AOI differs from the accepted Stage 01 boundary')
    source_rows=json.loads(relative_file(root,'metadata/stage02_final_inventory.json').read_text())
    expected={r['dataset_id'] for r in yaml.safe_load((project/'config/datasets.yml').read_text())['datasets']}
    if len(source_rows)!=48 or {r['dataset_id'] for r in source_rows}!=expected:raise ValueError('Stage 03 source inventory does not match the original registry')
    return root


def preflight(project,source,workspace):
    if is_stage03(source):
        root=baseline(unpack(source,Path(workspace)/'stage03_input'),project)
        return dict(needs_earth_engine=False,input_stage='03',reuse_existing_core=True,selected_layers=254,aoi_sha256=sha256(Path(project)/'data/aoi/parcel_a.geojson'))
    cfg,inputs,layers,rows,_=prepare(project,source,workspace)
    return dict(needs_earth_engine=any(l['extraction_status']=='PENDING' and l['adapter'].startswith('ee_') for l in layers),
        input_stage='02',reuse_existing_core=False,selected_layers=sum(l['extraction_status']=='PENDING' for l in layers)+254,aoi_sha256=inputs['aoi_sha256'])


def run(project,source,output_base=None,cache=None,ee_project=None,progress=print):
    import tempfile
    from .maize_extension import extend
    project=Path(project);source=Path(source);output_base=Path(output_base or project/'outputs/stage03_runs');output_base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='input-check-',dir=output_base) as workspace:
        if is_stage03(source):core=baseline(unpack(source,Path(workspace)/'stage03_input'),project)
        else:
            # Reuse only a fully verified core matching the exact selected Stage 02 ZIP.
            core=None;digest=sha256(source) if source.is_file() else None
            if digest:
                for path in sorted(output_base.glob('*/package/input_manifest.json'),reverse=True):
                    try:
                        if json.loads(path.read_text()).get('input_sha256')==digest:core=baseline(path.parent,project);break
                    except (ValueError,KeyError,OSError):continue
            if core is None:
                built=core_run(project,source,output_base,cache,ee_project,progress)
                if built['outcome']=='INCOMPLETE':return built
                core=baseline(Path(built['dashboard']).parent.parent,project)
        return extend(project,core,output_base,cache,progress)
