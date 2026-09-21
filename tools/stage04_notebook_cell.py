#@title Run Stage 04
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import sys
import traceback
import venv
import zlib
from datetime import datetime, timezone
from html import escape
from IPython.display import HTML, FileLink, clear_output, display

STAGE04_BUNDLE=(
__BUNDLE_LITERAL__
)
STAGE04_SHA256="__BUNDLE_SHA256__"


def materialize(encoded,digest,base):
    raw=zlib.decompress(base64.b64decode(encoded))
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Notebook integrity check failed. Open Stage 04 again from GitHub.')
    root=base/'.stage04/snapshots'/digest[:16];root.mkdir(parents=True,exist_ok=True)
    for name,value in json.loads(raw).items():
        path=root/name
        if not path.resolve().is_relative_to(root.resolve()) or '..' in Path(name).parts:raise ValueError('Unsafe notebook bundle path')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(base64.b64decode(value))
    return root


def choose_input(base):
    configured=os.getenv('STAGE04_INPUT')
    if configured:return Path(configured).expanduser().resolve()
    try:from google.colab import files
    except ImportError:return Path(input('Completed Stage 03 ZIP path: ').strip()).expanduser().resolve()
    print('Choose your completed Stage 03 ZIP.')
    uploaded=files.upload()
    if len(uploaded)!=1:raise ValueError('Select exactly one completed Stage 03 ZIP.')
    name,data=next(iter(uploaded.items()))
    if not name.lower().endswith('.zip'):raise ValueError('Select the original Stage 03 ZIP.')
    folder=base/'data/stage04_inputs'/hashlib.sha256(data).hexdigest()[:16];folder.mkdir(parents=True,exist_ok=True)
    target=folder/Path(name).name;target.write_bytes(data);return target


def download_file(path):
    try:
        from google.colab import files
        files.download(str(path))
    except ImportError:display(FileLink(str(path)))
    except Exception:
        display(FileLink(str(path)));print(f'Download {Path(path).name} from the Files panel.')


def checked(command,log,env=None):
    with log.open('a',encoding='utf-8') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,env=env)
    if result.returncode:
        lines=log.read_text(encoding='utf-8',errors='replace').splitlines()
        tail=next((line for line in reversed(lines) if line.strip()),'See the downloaded log.')
        raise RuntimeError(tail[:700])


def run_notebook():
    cwd=Path.cwd();base=(Path('/content') if Path('/content').exists() else cwd)/'parcel-a-agri-geospatial'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    log=base/'outputs/stage04_logs'/stamp/'stage04_setup.log';log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text(f'Stage 04 bundle {STAGE04_SHA256}\nPython {sys.version}\n',encoding='utf-8')
    try:
        print('Preparing Stage 04…')
        root=materialize(STAGE04_BUNDLE,STAGE04_SHA256,base);selected=choose_input(base)
        if not selected.is_file() or selected.suffix.lower()!='.zip':raise ValueError('Select a completed Stage 03 ZIP file.')
        lock=root/'stage04/requirements-lock.txt';key=hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
        env_dir=base/'.stage04'/f'env-{sys.version_info.major}.{sys.version_info.minor}-{key}'
        python=env_dir/'bin/python';installed=env_dir/'stage04-installed';browser_ready=env_dir/'stage04-browser-installed'
        if not python.exists():venv.EnvBuilder(with_pip=False).create(env_dir)
        if not installed.exists():
            checked([sys.executable,'-I','-m','pip','--python',str(python),'install','-q','-r',str(lock)],log)
            installed.write_text(key)
        if not browser_ready.exists():
            checked([str(python),'-I','-m','playwright','install','--with-deps','chromium'],log)
            browser_ready.write_text('chromium-playwright-1.55.0')
        result_path=log.parent/'stage04_result.json'
        launch="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('parcel_a_stage04',run_name='__main__')"
        command=[str(python),'-I','-u','-c',launch,str(root/'stage04/src'),'--input',str(selected),
                 '--output-base',str(base/'outputs/stage04_runs'),'--result-path',str(result_path)]
        print('Building scenario summaries and checking the offline dashboard…')
        with log.open('a',encoding='utf-8') as stream:process=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        output=json.loads(result_path.read_text()) if result_path.exists() else {}
        if process.returncode or not output.get('archive'):raise RuntimeError(output.get('error','The worker stopped. See the downloaded log.'))
        clear_output(wait=True)
        html=Path(output['dashboard']).read_text(encoding='utf-8')
        # Open the new tab in this inline preview only; the packaged original startup stays unchanged.
        preview=html.replace('</body>','<script>document.getElementById("stage04-tab").click();</script></body>')
        display(HTML('<iframe title="Stage 04 results" style="width:100%;height:1000px;border:0" srcdoc="'+escape(preview,quote=True)+'"></iframe>'))
        if output['status']=='INCOMPLETE':print('Stage 04 needs attention. See the dashboard quality checks.')
        elif output['status']=='COMPLETE_WITH_DOCUMENTED_GAPS':print('Stage 04 ready. Some source evidence is unavailable; see the dashboard gaps.')
        else:print('Stage 04 ready.')
        print('Download and extract the ZIP. Open dashboard/parcel_a_data_inventory.html for all maps and file downloads.')
        receipt=output['summary']
        display(HTML('<details><summary>Package checksum</summary><p>'+str(receipt['output_zip_size'])+' bytes</p><code>'+escape(receipt['output_zip_sha256'])+'</code></details>'))
        download_file(output['archive'])
    except Exception as error:
        with log.open('a',encoding='utf-8') as stream:traceback.print_exc(file=stream)
        display(HTML('<p><b>Stage 04 needs attention:</b> '+escape(str(error))+'</p>'))
        print('Attach the downloaded stage04_setup.log so the exact error can be checked.')
        download_file(log)


run_notebook()
