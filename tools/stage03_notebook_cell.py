#@title Run Stage 03
from pathlib import Path
import base64
import hashlib
import importlib
import json
import os
import subprocess
import sys
import venv
import zlib
from html import escape
from IPython.display import HTML, FileLink, clear_output, display

STAGE03_BUNDLE=(
__BUNDLE_LITERAL__
)
STAGE03_SHA256="__BUNDLE_SHA256__"


def materialize(encoded,digest,base):
    raw=zlib.decompress(base64.b64decode(encoded))
    if hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError("Notebook integrity check failed. Open Stage 03 again from GitHub.")
    root=base/".stage03/snapshots"/digest[:16]
    root.mkdir(parents=True,exist_ok=True)
    hashes={}
    for name,value in json.loads(raw).items():
        path=root/name
        if not path.resolve().is_relative_to(root.resolve()) or ".." in Path(name).parts:
            raise ValueError("Unsafe notebook bundle path")
        data=base64.b64decode(value);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        hashes[name]=hashlib.sha256(data).hexdigest()
    (root/"bundle_manifest.json").write_text(json.dumps(dict(bundle_sha256=digest,files=hashes),indent=2))
    return root


def choose_input(base):
    configured=os.getenv("STAGE02_INPUT")
    if configured:
        path=Path(configured)
        if not path.exists():raise ValueError("The configured Stage 02 input does not exist.")
        return path.resolve()
    runs=base/"outputs/stage02_runs"
    candidates=sorted(runs.glob("*/stage02_all_in_one_results.zip")) if runs.exists() else []
    if len(candidates)==1:return candidates[0]
    try:
        from google.colab import files
    except ImportError:
        if candidates:
            for i,path in enumerate(candidates,1):print(f"{i}: {path.parent.name}")
        response=input("Select the Stage 02 run number or enter the full ZIP/run path: ").strip()
        return candidates[int(response)-1] if response.isdigit() and candidates else Path(response).expanduser().resolve()
    print("Choose the completed Stage 02 results ZIP.")
    uploaded=files.upload()
    if len(uploaded)!=1:raise ValueError("Select exactly one Stage 02 ZIP.")
    name,data=next(iter(uploaded.items()))
    if not name.lower().endswith(".zip"):raise ValueError("Select the complete Stage 02 ZIP.")
    folder=base/"data/stage03_inputs"/hashlib.sha256(data).hexdigest()[:16];folder.mkdir(parents=True,exist_ok=True)
    target=folder/"stage02_all_in_one_results.zip";target.write_bytes(data)
    return target


def run_notebook():
    cwd=Path.cwd()
    base=cwd if (cwd/"config/project.yml").exists() else ((Path("/content") if Path("/content").exists() else cwd)/"parcel-a-agri-geospatial")
    base.mkdir(parents=True,exist_ok=True)
    log=base/"outputs/stage03_setup.log";log.parent.mkdir(parents=True,exist_ok=True)
    try:
        print("Preparing Stage 03…")
        root=materialize(STAGE03_BUNDLE,STAGE03_SHA256,base)
        selected=choose_input(base)
        lock=root/"stage03/requirements-lock.txt"
        key=hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
        env_dir=base/".stage03"/f"env-{sys.version_info.major}.{sys.version_info.minor}-{key}"
        python=env_dir/"bin/python";installed=env_dir/"stage03-installed"
        if not python.exists():venv.EnvBuilder(with_pip=False).create(env_dir)
        if not installed.exists():
            with log.open("w") as stream:
                result=subprocess.run([sys.executable,"-m","pip","--python",str(python),"install","-q","-r",str(lock)],stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError("Setup could not finish. The setup log contains the cause.")
            installed.write_text(key)
        env=dict(os.environ,PYTHONPATH=str(root/"stage03/src"),MPLCONFIGDIR=str(base/".stage03/matplotlib"))
        result_path=root/"stage03_result.json"
        command=[str(python),"-m","parcel_a_stage03","--root",str(root),"--input",str(selected),
            "--output-base",str(base/"outputs/stage03_runs"),"--cache",str(base/"data/cache/stage03"),"--result-path",str(result_path)]
        def worker(extra):
            result_path.unlink(missing_ok=True)
            with log.open("a") as stream:r=subprocess.run(command+extra,env=env,stdout=stream,stderr=subprocess.STDOUT)
            data=json.loads(result_path.read_text()) if result_path.exists() else {}
            if r.returncode:raise RuntimeError(data.get("error","Stage 03 stopped. See the retained log."))
            return data
        preflight=worker(["--preflight"])
        if preflight["needs_earth_engine"]:
            package_path=subprocess.check_output([str(python),"-c","import sysconfig; print(sysconfig.get_path('purelib'))"],text=True).strip()
            sys.path.insert(0,package_path);importlib.invalidate_caches()
            import ee
            project=os.getenv("EARTH_ENGINE_PROJECT","practical-proxy-441422-n6")
            try:ee.Initialize(project=project)
            except Exception:
                ee.Authenticate(auth_mode="notebook",force=True)
                ee.Initialize(project=project)
            ee.data.setDeadline(90000)
            if ee.String("stage03-ready").getInfo()!="stage03-ready":raise RuntimeError("Earth Engine connection could not be verified.")
            command.extend(["--ee-project",project])
        print("Preparing maps, tables and graphs. Completed downloads are reused on reruns…")
        output=worker([])
        clear_output(wait=True)
        html=Path(output["dashboard"]).read_text(encoding="utf-8")
        display(HTML('<iframe style="width:100%;height:900px;border:0" allow="fullscreen" srcdoc="'+escape(html,quote=True)+'"></iframe>'))
        summary=output["summary"]
        if output["outcome"]=="INCOMPLETE":
            print("Stage 03 needs attention. See the gaps in the dashboard; diagnostics are available below.")
        else:
            print(f"Stage 03 complete: {summary['extracted_layer_count']} layers from {summary['extracted_source_count']} sources.")
            if summary["gaps"]:print(f"{len(summary['gaps'])} optional layers need attention; details are in the dashboard.")
        try:
            from google.colab import files
            files.download(output["archive"])
        except ImportError:display(FileLink(output["archive"]))
        return output["outcome"]!="INCOMPLETE"
    except Exception as error:
        display(HTML(f"<p><b>Stage 03 needs attention:</b> {escape(str(error))}</p>"))
        if log.exists():display(FileLink(str(log)))
        return False


run_notebook()
