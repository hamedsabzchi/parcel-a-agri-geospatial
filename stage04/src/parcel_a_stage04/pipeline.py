"""ZIP-only, append-only Stage 04 packaging with original-byte preservation."""
import json
import os
import platform
import re
import shutil
import stat
import importlib.metadata
from pathlib import Path,PurePosixPath
from zipfile import ZipFile,ZIP_DEFLATED
from datetime import datetime,timezone
from .common import sha,dump,csv_write,relative,now
from .contract import resolve,embedded
from .browser_qa import inspect
from . import __version__

ENTRY='dashboard/parcel_a_data_inventory.html'
ASSETS=Path(__file__).parent/'assets'
MAX_BYTES=2_000_000_000


def unpack(source,destination):
    source=Path(source);destination=Path(destination)
    if not source.is_file() or source.suffix.lower()!='.zip':raise ValueError('Select the original completed Stage 03 ZIP, not an extracted folder or Stage 04 output')
    destination.mkdir(parents=True,exist_ok=False)
    with ZipFile(source) as z:
        entries=z.infolist();names=set()
        if len(entries)>20000 or sum(i.file_size for i in entries)>MAX_BYTES:raise ValueError('Input ZIP exceeds the configured budget')
        for entry in entries:
            p=PurePosixPath(entry.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in entry.filename or ':' in entry.filename or entry.filename in names or stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Unsafe or duplicate ZIP member')
            names.add(entry.filename)
            if any(part.startswith('stage04_') for part in p.parts):raise ValueError('Stage 04 packages cannot be reused as Stage 03 input')
            if entry.is_dir():continue
            if entry.file_size>500_000_000 or (entry.file_size>10_000_000 and entry.file_size/max(1,entry.compress_size)>2000):raise ValueError('Unsafe ZIP expansion')
            target=destination.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(entry) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1048576)
    relative(destination,ENTRY)
    if 'id="stage04-data"' in (destination/ENTRY).read_text():raise ValueError('Input already contains Stage 04')
    manifest=json.loads(relative(destination,'metadata/package_checksums.json').read_text())
    files={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    if files-set(manifest)!={'metadata/package_checksums.json'}:raise ValueError('Stage 03 package contains unregistered or missing files')
    for name,digest in manifest.items():
        if sha(relative(destination,name))!=digest:raise ValueError('Stage 03 checksum mismatch: '+name)
    return [dict(path=name,size=(destination/name).stat().st_size,sha256=sha(destination/name)) for name in sorted(files)]


def additions(html,data):
    if html.count('</nav>')!=1 or html.count('</main>')!=1 or html.count('</body>')!=1:raise ValueError('Unsupported Stage 03 HTML structure; original dashboard will not be rebuilt')
    button='<button id="stage04-tab" data-tab="stage04" role="tab" aria-controls="stage04" aria-selected="false">Stage 04: Future Scenarios Summary</button>'
    css='<style id="stage04-style">'+(ASSETS/'stage04.css').read_text()+'</style>'
    section=(ASSETS/'stage04.html').read_text()
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    script='<script id="stage04-data" type="application/json">'+payload+'</script><script id="stage04-script">'+(ASSETS/'stage04.js').read_text()+'</script>'
    inserts=[(button,'</nav>'),(css+section,'</main>'),(script,'</body>')]
    changed=html
    for text,anchor in inserts:changed=changed.replace(anchor,text+anchor,1)
    restored=changed
    for text,_ in inserts:restored=restored.replace(text,'',1)
    if restored!=html:raise ValueError('HTML insertion changed original bytes')
    return changed,dict(original_html_preserved_as_subsequence=True,insertions=[dict(anchor=a,added_bytes=len(t.encode())) for t,a in inserts])


def flat_rows(data):
    rows=[]
    for r in data['scenarios']:
        row={k:v for k,v in r.items() if k!='products'}
        for kind,p in r['products'].items():
            for k,v in p['summary'].items():row[kind+'_'+k]=v
        rows.append(row)
    return rows


def run(source,output_base,*,browser_check=inspect,testing=False):
    source=Path(source).resolve();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    run_dir=Path(output_base)/stamp;payload=run_dir/'package';baseline=unpack(source,payload)
    input_info=dict(filename=source.name,size=source.stat().st_size,sha256=sha(source),extracted_at_utc=now())
    original_html=(payload/ENTRY).read_bytes().decode('utf-8');original=embedded(payload)
    if not testing and ('SYNTHETIC_TEST_RUN' in original_html or '"synthetic_test_only":true' in original_html or 'SYNTHETIC TEST FIXTURE' in original_html):raise ValueError('Synthetic test packages are not accepted as user analytical evidence')
    # Baseline browser check happens before any dashboard modification.
    baseline_browser=browser_check(payload/ENTRY,False)
    if baseline_browser['status']!='PASS':raise ValueError('The original Stage 03 dashboard did not pass baseline browser QA')
    data=resolve(payload);data['synthetic_test_only']=bool(testing)
    data['input']=input_info;data['version']=__version__;data['period_order']=['FP2140','FP4160','FP6180','FP8100']
    data['downloads']=[dict(label=label,path='../'+path) for label,path in [
        ('Scenario summary CSV','tables/stage04_future_scenario_summary.csv'),('Scenario summary JSON','metadata/stage04_future_scenario_summary.json'),
        ('Source contract CSV','tables/stage04_source_contract.csv'),('Source contract JSON','metadata/stage04_source_contract.json'),
        ('Quality checks','qa/stage04_qa_report.json'),('Changed files','tables/stage04_change_manifest.csv'),
        ('Processing history','tables/stage04_processing_history.csv'),('Output manifest','tables/stage04_output_manifest.csv'),
        ('Original Stage 03 limitations','tables/source_limitations.csv'),('Original Stage 03 provenance','metadata/provenance.json')]]
    data['status']='COMPLETE_WITH_DOCUMENTED_GAPS' if data['gaps'] or data['conflicts'] else 'COMPLETE'
    if not data['scenarios']:data['status']='INCOMPLETE'
    # Broad per-diagnostic domains across comparable scenarios, separately for each crop.
    domains={}
    for r in data['scenarios']:
        product=r['products'].get('yield')
        if not product:continue
        for u in product['units']:
            for metric,v in u['metrics'].items():
                if metric.startswith('model_') and v is not None:
                    key=r['crop_code']+'__'+metric;old=domains.get(key,[v,v]);domains[key]=[min(old[0],v),max(old[1],v)]
    data['domains']=domains;data['domain_rule']='Pooled finite native-unit diagnostic minimum and maximum across verified periods, SSPs and managements for the selected crop; separate domain for each diagnostic'
    methodology=json.loads((ASSETS/'methodology.json').read_text())
    runtime=Path(__file__).parent
    methodology.update(version=__version__,source_files=data['discovery_inventory'],input=input_info,
        environment=dict(python=platform.python_version(),dependencies={name:importlib.metadata.version(name) for name in ['numpy','shapely','pyproj','playwright']}),
        runtime_source_sha256={p.relative_to(runtime).as_posix():sha(p) for p in sorted(runtime.rglob('*')) if p.is_file() and p.suffix in {'.py','.js','.css','.html','.json'}},synthetic_test_only=bool(testing))
    dump(payload/'metadata/stage04_methodology.json',methodology)
    dump(payload/'metadata/stage04_source_contract.json',dict(records=data['contract'],conflicts=data['conflicts'],gaps=data['gaps']))
    csv_write(payload/'tables/stage04_source_contract.csv',data['contract'])
    rows=flat_rows(data);csv_write(payload/'tables/stage04_future_scenario_summary.csv',rows,['key','crop_code','period_code','ssp_code','management_code'])
    dump(payload/'metadata/stage04_future_scenario_summary.json',dict(status=data['status'],scenarios=rows,gaps=data['gaps'],conflicts=data['conflicts'],synthetic_test_only=bool(testing)))
    dump(payload/'metadata/stage04_baseline_inventory.json',baseline)
    dump(payload/'qa/stage04_baseline_browser.json',baseline_browser)
    dump(payload/'dashboard/assets/stage04_future_scenarios_data.json',data)
    for source_name,target_name in [('stage04.css','stage04_future_scenarios.css'),('stage04.js','stage04_future_scenarios.js')]:shutil.copyfile(ASSETS/source_name,payload/'dashboard/assets'/target_name)
    changed_html,insertion_evidence=additions(original_html,data);(payload/ENTRY).write_bytes(changed_html.encode('utf-8'))
    change=[dict(path=ENTRY,before_sha256=next(x['sha256'] for x in baseline if x['path']==ENTRY),after_sha256=sha(payload/ENTRY),
        reason='Insert one tab, scoped CSS, one section, embedded Stage 04 data and namespaced JavaScript; original content retained exactly',**insertion_evidence)]
    csv_write(payload/'tables/stage04_change_manifest.csv',change)
    regression=browser_check(payload/ENTRY,True)
    paths_ok=all((payload/r['path']).is_file() and (r['path']==ENTRY or sha(payload/r['path'])==r['sha256']) for r in baseline)
    # All existing and additive package-relative downloads are resolved without HTTP.
    links=[]
    for link in data['downloads']:
        try:relative(payload,link['path'].removeprefix('../'));links.append(True)
        except ValueError:links.append(link['path'].startswith(('../qa/stage04_','../tables/stage04_output_','../tables/stage04_processing_')))
    checks=dict(original_paths_and_non_html_bytes_unchanged=paths_ok,original_html_content_unchanged=insertion_evidence['original_html_preserved_as_subsequence'],
        original_browser_passed=baseline_browser['status']=='PASS',extended_browser_passed=regression['status']=='PASS',
        unique_scenario_keys=len(rows)==len({r['key'] for r in rows}),package_downloads_resolved=all(links),
        source_contract_has_verified_combinations=bool(rows),no_duplicate_dashboard_entry=True,input_zip_not_embedded=not(payload/source.name).exists())
    status=data['status'] if all(checks.values()) else 'INCOMPLETE'
    if status!=data['status']:
        data['status']=status
        changed_html,_=additions(original_html,data);(payload/ENTRY).write_bytes(changed_html.encode('utf-8'))
        dump(payload/'dashboard/assets/stage04_future_scenarios_data.json',data)
        dump(payload/'metadata/stage04_future_scenario_summary.json',dict(status=status,scenarios=rows,gaps=data['gaps'],conflicts=data['conflicts'],synthetic_test_only=bool(testing)))
        change[0]['after_sha256']=sha(payload/ENTRY);csv_write(payload/'tables/stage04_change_manifest.csv',change)
    qa=dict(status=status,checks=checks,baseline_browser=baseline_browser,regression_browser=regression,conflicts=data['conflicts'],gaps=data['gaps'],synthetic_test_only=bool(testing))
    dump(payload/'qa/stage04_qa_report.json',qa);csv_write(payload/'qa/stage04_qa_report.csv',[dict(check=k,passed=v) for k,v in checks.items()])
    history=[dict(time_utc=input_info['extracted_at_utc'],operation='Validate and inventory original Stage 03 ZIP',input_sha256=input_info['sha256']),
        dict(time_utc=now(),operation='Resolve contained sources; verify joins and recompute summaries',verified_combinations=len(rows),conflicts=len(data['conflicts'])),
        dict(time_utc=now(),operation='Insert Stage 04 and run preservation, desktop, mobile and offline QA',status=status)]
    dump(payload/'metadata/stage04_processing_history.json',history);csv_write(payload/'tables/stage04_processing_history.csv',history)
    originals={r['path'] for r in baseline};added=[p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file() and p.relative_to(payload).as_posix() not in originals]
    # ZIP hash cannot be stored inside the ZIP it hashes. An adjacent receipt is authoritative.
    summary=dict(status=status,input=input_info,original_file_count=len(baseline),original_files_changed=[ENTRY],
        new_files_added=sorted(added+['metadata/stage04_run_summary.json','tables/stage04_output_manifest.csv','metadata/stage04_package_checksums.json']),
        verified_scenario_combinations=len(rows),excluded_combinations=data['conflicts'],optional_missing_metrics=data['gaps'],
        regression_qa=regression['status'],offline_qa=regression['checks'].get('offline_reload',False),
        mobile_qa=all(v for k,v in regression['checks'].items() if k.startswith('mobile_')),packaging_qa=all(checks.values()),
        output_zip_checksum='Recorded after ZIP creation in the adjacent stage04_run_receipt.json to avoid circular self-hashing',synthetic_test_only=bool(testing))
    summary['final_file_count']=len(baseline)+len(summary['new_files_added'])
    dump(payload/'metadata/stage04_run_summary.json',summary)
    files=[p for p in sorted(payload.rglob('*')) if p.is_file()]
    manifest=[dict(path=p.relative_to(payload).as_posix(),size=p.stat().st_size,sha256=sha(p),origin='ORIGINAL_STAGE03' if p.relative_to(payload).as_posix() in originals else 'ADDED_STAGE04') for p in files]
    csv_write(payload/'tables/stage04_output_manifest.csv',manifest)
    files.append(payload/'tables/stage04_output_manifest.csv');dump(payload/'metadata/stage04_package_checksums.json',{p.relative_to(payload).as_posix():sha(p) for p in files})
    files.append(payload/'metadata/stage04_package_checksums.json')
    if sum(p.stat().st_size for p in files)>MAX_BYTES:raise ValueError('Output package exceeds budget')
    archive=run_dir/'stage04_future_scenario_summary.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for path in files:z.write(path,path.relative_to(payload))
    with ZipFile(archive) as z:
        if z.testzip() is not None or len(z.namelist())!=len(files):raise ValueError('Output ZIP integrity failed')
    receipt=dict(summary,output_zip_name=archive.name,output_zip_size=archive.stat().st_size,output_zip_sha256=sha(archive),final_file_count=len(files))
    dump(run_dir/'stage04_run_receipt.json',receipt)
    return dict(status=status,archive=str(archive),dashboard=str(payload/ENTRY),receipt=str(run_dir/'stage04_run_receipt.json'),summary=receipt)
