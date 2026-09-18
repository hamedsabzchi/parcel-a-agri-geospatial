#@title Run Stage 02
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
from IPython.display import HTML, FileLink, clear_output, display

PROJECT_BUNDLE_B64 = (
__PROJECT_BUNDLE_LITERAL__
)
PROJECT_BUNDLE_SHA256 = "__PROJECT_BUNDLE_SHA256__"


def materialize_bundle(encoded, checksum, base):
    raw = zlib.decompress(base64.b64decode(encoded))
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError("The notebook's bundled files failed their integrity check. Reopen the GitHub notebook.")
    root = base / ".stage02" / "snapshots" / checksum[:16]
    root.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, value in json.loads(raw).items():
        target = root / name
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid bundled path")
        content = base64.b64decode(value)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)  # Always restore the exact notebook version, even on reruns.
        hashes[name] = hashlib.sha256(content).hexdigest()
    (root / "bundle_manifest.json").write_text(json.dumps({"bundle_sha256": checksum, "files": hashes}, indent=2))
    shared = base / "data/local"
    shared.mkdir(parents=True, exist_ok=True)
    local = root / "data/local"
    local.parent.mkdir(parents=True, exist_ok=True)
    if not local.exists():
        local.symlink_to(shared, target_is_directory=True)
    return root


def run_notebook():
    cwd = Path.cwd()
    base = cwd if (cwd / "config/project.yml").exists() else (
        (Path("/content") if Path("/content").exists() else cwd) / "parcel-a-agri-geospatial")
    base.mkdir(parents=True, exist_ok=True)
    log = base / "outputs/stage02_setup.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        print("Preparing Stage 02…")
        root = materialize_bundle(PROJECT_BUNDLE_B64, PROJECT_BUNDLE_SHA256, base)
        dependency_hash = hashlib.sha256((root / "requirements-lock.txt").read_bytes()).hexdigest()[:12]
        env_dir = base / ".stage02" / f"env-{sys.version_info.major}.{sys.version_info.minor}-{dependency_hash}"
        python = env_dir / "bin/python"
        installed = env_dir / "stage02-installed"
        if not python.exists():
            venv.EnvBuilder(with_pip=False).create(env_dir)
        if not installed.exists():
            # A separate interpreter prevents NumPy/GDAL conflicts with packages already loaded by Colab.
            with log.open("w") as stream:
                result = subprocess.run([sys.executable, "-m", "pip", "--python", str(python), "install", "-q", "-r", str(root / "requirements-lock.txt")],
                                        stdout=stream, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError("Dependency installation failed. See the setup log below.")
            installed.write_text(dependency_hash)
        package_path = subprocess.check_output([str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
        # Only authentication runs in the notebook; all geospatial imports run in the isolated worker.
        sys.path.insert(0, package_path)
        importlib.invalidate_caches()
        import ee
        project = os.getenv("EARTH_ENGINE_PROJECT", "practical-proxy-441422-n6")
        os.environ["EARTH_ENGINE_PROJECT"] = project
        try:
            ee.Initialize(project=project)
        except Exception:
            ee.Authenticate(auth_mode="notebook", force=True)
            try:
                ee.Initialize(project=project)
            except Exception as error:
                raise RuntimeError(f"Earth Engine could not connect to project {project}. Check that your Google account can use this Earth Engine project. {error}") from error
        ee.data.setDeadline(60000)
        if ee.String("Parcel A Stage 02").getInfo() != "Parcel A Stage 02":
            raise RuntimeError("Earth Engine server verification failed.")
        print("Earth Engine connected. Checking 48 sources and 16 selected GAEZ assets…")
        result_path = root / "stage02_result.json"
        if result_path.exists():
            result_path.unlink()
        env = dict(os.environ, PYTHONPATH=str(root / "src"))
        with log.open("a") as stream:
            result = subprocess.run([str(python), "-m", "parcel_a_geo.stage02", "--root", str(root),
                "--output-base", str(base / "outputs/stage02_runs"), "--result-path", str(result_path)],
                env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode or not result_path.exists():
            raise RuntimeError("Stage 02 stopped before completion. Download the log below for the exact error.")
        output = json.loads(result_path.read_text())
        clear_output(wait=True)
        display(HTML(Path(output["dashboard"]).read_text(encoding="utf-8")))
        archive = output["archive"]
        try:
            from google.colab import files
            files.download(archive)
        except ImportError:
            display(FileLink(archive))
        print("SUCCESS: Stage 02 data discovery completed")
    except Exception as error:
        from html import escape
        display(HTML(f"<p><b>Stage 02 needs attention:</b> {escape(str(error))}</p>"))
        if log.exists():
            display(FileLink(str(log)))
        return False
    return True


run_notebook()
