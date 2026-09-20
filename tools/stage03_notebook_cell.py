#@title Run Stage 03
from pathlib import Path
import base64
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import traceback
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
    configured=os.getenv("STAGE03_INPUT") or os.getenv("STAGE02_INPUT")
    if configured:
        path=Path(configured)
        if not path.exists():raise ValueError("The configured input package does not exist.")
        return path.resolve()
    runs=base/"outputs/stage02_runs"
    candidates=sorted(runs.glob("*/stage02_all_in_one_results.zip")) if runs.exists() else []
    if len(candidates)==1:return candidates[0]
    try:
        from google.colab import files
    except ImportError:
        if candidates:
            for i,path in enumerate(candidates,1):print(f"{i}: {path.parent.name}")
        response=input("Select a run number or enter the full Stage 02 / Stage 03 ZIP path: ").strip()
        return candidates[int(response)-1] if response.isdigit() and candidates else Path(response).expanduser().resolve()
    print("Choose your completed Stage 02 or Stage 03 results ZIP.")
    uploaded=files.upload()
    if len(uploaded)!=1:raise ValueError("Select exactly one completed results ZIP.")
    name,data=next(iter(uploaded.items()))
    if not name.lower().endswith(".zip"):raise ValueError("Select a complete Stage 02 or Stage 03 ZIP.")
    folder=base/"data/stage03_inputs"/hashlib.sha256(data).hexdigest()[:16];folder.mkdir(parents=True,exist_ok=True)
    target=folder/Path(name).name;target.write_bytes(data)
    return target


def worker_command(python,root,selected,base,result_path):
    # Isolate the worker from notebook/user-site packages and Python environment
    # settings. Pass the bundled source path explicitly rather than PYTHONPATH.
    launch="import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('parcel_a_stage03',run_name='__main__')"
    return [str(python),"-I","-u","-c",launch,str(root/"stage03/src"),
        "--root",str(root),"--input",str(selected),
        "--output-base",str(base/"outputs/stage03_runs"),
        "--cache",str(base/"data/cache/stage03"),"--result-path",str(result_path)]


def log_error(log,start=0):
    with log.open("rb") as stream:
        stream.seek(max(start,log.stat().st_size-16000))
        lines=stream.read().decode("utf-8",errors="replace").splitlines()
    lines=[line.strip() for line in lines if line.strip()]
    errors=[line for line in lines if re.match(r"(?:[\w.]+(?:Error|Exception)|ERROR|Fatal Python error):",line)]
    return (errors[-1] if errors else lines[-1] if lines else "No error text was returned.")[:1200]


def run_worker(command,extra,env,log,result_path):
    result_path.unlink(missing_ok=True)
    with log.open("a",encoding="utf-8") as stream:
        stream.write("\n--- "+("Input check" if "--preflight" in extra else "Build results")+" ---\n")
        stream.flush();start=log.stat().st_size
        process=subprocess.run(command+extra,env=env,stdout=stream,stderr=subprocess.STDOUT)
    data={}
    if result_path.exists():
        try:data=json.loads(result_path.read_text(encoding="utf-8"))
        except (ValueError,OSError):pass
    if process.returncode or not isinstance(data,dict) or not data:
        reason=data.get("error") if isinstance(data,dict) else None
        reason=reason or log_error(log,start)
        phase=data.get("phase") if isinstance(data,dict) else None
        label=phase or ("checking inputs" if "--preflight" in extra else "building results")
        raise RuntimeError(f"Stopped while {label} (exit {process.returncode}). {reason}")
    return data


def download_file(path):
    try:
        from google.colab import files
    except ImportError:
        display(FileLink(str(path)))
        return
    try:files.download(str(path))
    except Exception:
        display(FileLink(str(path)))
        print(f"Download {Path(path).name} from Colab's Files panel.")


def run_notebook():
    cwd=Path.cwd()
    base=cwd if (cwd/"config/project.yml").exists() else ((Path("/content") if Path("/content").exists() else cwd)/"parcel-a-agri-geospatial")
    base.mkdir(parents=True,exist_ok=True)
    log=base/"outputs/stage03_setup.log";log.parent.mkdir(parents=True,exist_ok=True)
    try:
        log.write_text(f"Stage 03 notebook {STAGE03_SHA256}\nPython {sys.version}\n",encoding="utf-8")
        print("Preparing Stage 03…")
        root=materialize(STAGE03_BUNDLE,STAGE03_SHA256,base)
        selected=choose_input(base)
        lock=root/"stage03/requirements-lock.txt"
        key=hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
        env_dir=base/".stage03"/f"env-{sys.version_info.major}.{sys.version_info.minor}-{key}"
        python=env_dir/"bin/python";installed=env_dir/"stage03-installed"
        if not python.exists():venv.EnvBuilder(with_pip=False).create(env_dir)
        if not installed.exists():
            with log.open("a") as stream:
                result=subprocess.run([sys.executable,"-I","-m","pip","--python",str(python),"install","-q","-r",str(lock)],stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError("Dependency setup failed. "+log_error(log))
            installed.write_text(key)
        env=dict(os.environ,MPLBACKEND="Agg",MPLCONFIGDIR=str(base/".stage03/matplotlib"))
        result_path=root/"stage03_result.json"
        command=worker_command(python,root,selected,base,result_path)
        def worker(extra):return run_worker(command,extra,env,log,result_path)
        preflight=worker(["--preflight"])
        if preflight["needs_earth_engine"]:
            package_path=subprocess.check_output([str(python),"-I","-c","import sysconfig; print(sysconfig.get_path('purelib'))"],text=True).strip()
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
            if summary.get('maize_extension'):
                print(f"Stage 03 complete: original results retained + {summary['maize_extension']['available_layers']} maize source maps.")
            else:print(f"Stage 03 complete: {summary['extracted_layer_count']} layers from {summary['extracted_source_count']} sources.")
            if summary["gaps"]:print(f"{len(summary['gaps'])} optional layers need attention; details are in the dashboard.")
        download_file(output["archive"])
        return output["outcome"]!="INCOMPLETE"
    except Exception as error:
        with log.open("a",encoding="utf-8") as stream:traceback.print_exc(file=stream)
        display(HTML(f"<p><b>Stage 03 needs attention:</b> {escape(str(error))}</p>"))
        print("Attach the downloaded stage03_setup.log here so the exact error can be checked.")
        download_file(log)
        return False


_stage03_success=run_notebook()
