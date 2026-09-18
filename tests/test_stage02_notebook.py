from __future__ import annotations
import ast
import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestStage02Notebook(unittest.TestCase):
    def test_current_bundle_and_single_cell(self):
        spec = importlib.util.spec_from_file_location("build_stage02", ROOT / "tools/build_stage02.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        notebook = json.loads((ROOT / "notebooks/02_data_discovery.ipynb").read_text())
        self.assertEqual(notebook, builder.build_notebook())
        cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0]["outputs"], [])
        tree = ast.parse("".join(cells[0]["source"]))
        values = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and n.targets[0].id in {"PROJECT_BUNDLE_B64", "PROJECT_BUNDLE_SHA256"}}
        raw = zlib.decompress(base64.b64decode(values["PROJECT_BUNDLE_B64"]))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), values["PROJECT_BUNDLE_SHA256"])
        files = json.loads(raw)
        for required in ("src/stage02_gaez_verification.py", "src/parcel_a_geo/stage02.py",
                         "config/sources/gaez_v5_source_manifest.yml", "requirements-lock.txt"):
            self.assertIn(required, files)
        for name, content in files.items():
            self.assertEqual(base64.b64decode(content), (ROOT / name).read_bytes(), name)

    def test_stale_snapshot_repaired_without_deleting_user_files(self):
        tree = ast.parse((ROOT / "tools/stage02_notebook_cell.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "materialize_bundle")
        namespace = dict(Path=Path, zlib=zlib, base64=base64, hashlib=hashlib, json=json)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "bootstrap", "exec"), namespace)
        payload = {"src/stage02_gaez_verification.py": base64.b64encode(b"CURRENT").decode()}
        raw = json.dumps(payload).encode()
        encoded, checksum = base64.b64encode(zlib.compress(raw)).decode(), hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            user = base / "data/local/land_cover/notes.txt"
            user.parent.mkdir(parents=True)
            user.write_text("USER INPUT")
            root = namespace["materialize_bundle"](encoded, checksum, base)
            source = root / "src/stage02_gaez_verification.py"
            source.write_text("STALE!!")
            namespace["materialize_bundle"](encoded, checksum, base)
            self.assertEqual(source.read_text(), "CURRENT")
            self.assertEqual(user.read_text(), "USER INPUT")
            with self.assertRaises(ValueError):
                namespace["materialize_bundle"](encoded, "wrong", base)
