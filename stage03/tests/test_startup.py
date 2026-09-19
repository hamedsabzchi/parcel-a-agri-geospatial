"""Exercise the notebook's bundled worker, not just in-process package imports."""
import ast
from contextlib import chdir
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from fixtures import ROOT, fixture


def notebook_namespace():
    notebook=json.loads((ROOT/'notebooks/03_data_inventory_visualization.ipynb').read_text())
    code=''.join(next(c['source'] for c in notebook['cells'] if c['cell_type']=='code'))
    tree=ast.parse(code)
    # Display/upload need a browser; the actual bundled code and subprocesses do not.
    tree.body=[node for node in tree.body
        if not (isinstance(node,ast.ImportFrom) and node.module=='IPython.display')
        and not (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_stage03_success' for t in node.targets))]
    namespace=dict(HTML=lambda value:value,FileLink=str,display=lambda *_:None,clear_output=lambda **_:None)
    exec(compile(tree,'stage03-notebook-under-test','exec'),namespace)
    return namespace,ast.parse(code)


class NotebookStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook,cls.tree=notebook_namespace()

    def prepared(self,base):
        _,archive=fixture(base/'fixtures',large_evidence=True)
        notebook=self.notebook
        root=notebook['materialize'](notebook['STAGE03_BUNDLE'],notebook['STAGE03_SHA256'],base)
        result_path=root/'stage03_result.json'
        command=notebook['worker_command'](sys.executable,root,archive,base,result_path)
        log=base/'stage03_setup.log';log.write_text('SYNTHETIC TEST ONLY\n')
        env=dict(os.environ,MPLBACKEND='Agg',MPLCONFIGDIR=str(base/'mpl'))
        return root,result_path,command,log,env

    def test_materialized_notebook_preflight_and_build_in_isolated_process(self):
        with tempfile.TemporaryDirectory(prefix='stage03-notebook-') as temp:
            base=Path(temp)
            root,result_path,command,log,env=self.prepared(base)
            # A notebook runtime can carry Python paths/settings or shadowing
            # files. None may leak into the bundled worker or its pip subprocess.
            env.update(PYTHONHOME=str(base/'not-a-python-home'),PYTHONPATH=str(base),PYTHONUSERBASE=str(base))
            (base/'numpy.py').write_text("raise RuntimeError('Notebook working directory leaked into the worker')\n")
            worker=self.notebook['run_worker']
            with chdir(base):
                preflight=worker(command,['--preflight'],env,log,result_path)
                self.assertFalse(preflight['needs_earth_engine'])
                self.assertEqual(preflight['selected_layers'],16)
                result=worker(command,[],env,log,result_path)
            self.assertEqual(result['outcome'],'COMPLETE')
            self.assertEqual(result['summary']['gaez_extracted'],16)
            self.assertTrue(Path(result['archive']).is_file())
            self.assertTrue(Path(result['dashboard']).is_file())

    def test_missing_dependency_still_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root,result_path,command,log,env=self.prepared(Path(temp))
            command.insert(1,'-S')  # Deliberately exclude installed dependencies.
            with self.assertRaisesRegex(RuntimeError,'ModuleNotFoundError'):
                self.notebook['run_worker'](command,['--preflight'],env,log,result_path)
            result=json.loads(result_path.read_text())
            self.assertEqual(result['outcome'],'INCOMPLETE')
            self.assertEqual(result['phase'],'loading Stage 03 dependencies')
            self.assertIn('numpy',result['error'])
            self.assertNotIn('unmodified Stage 02 ZIP',result['error'])

    def test_worker_without_result_exposes_error_and_clears_stale_success(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);log=base/'setup.log';log.write_text('Old unrelated error\n')
            result=base/'result.json';result.write_text('{"outcome":"COMPLETE"}')
            command=[sys.executable,'-I','-c',"raise OSError('Synthetic startup failure')"]
            with self.assertRaisesRegex(RuntimeError,r'exit 1.*OSError: Synthetic startup failure'):
                self.notebook['run_worker'](command,[],dict(os.environ),log,result)
            self.assertFalse(result.exists())

    def test_colab_failure_downloads_log_without_false_display(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);(base/'config').mkdir();(base/'config/project.yml').write_text('{}')
            downloaded=[]
            files=types.SimpleNamespace(download=lambda path:downloaded.append(Path(path)))
            colab=types.ModuleType('google.colab');colab.files=files
            def fail_upload(_):raise ValueError('Synthetic upload failure')
            with chdir(base),patch.dict(self.notebook,choose_input=fail_upload),patch.dict(sys.modules,{'google.colab':colab}):
                self.assertFalse(self.notebook['run_notebook']())
            self.assertEqual(downloaded,[base/'outputs/stage03_setup.log'])
            self.assertIn('ValueError: Synthetic upload failure',downloaded[0].read_text())
            # An assignment suppresses the stray False/True notebook output.
            self.assertIsInstance(self.tree.body[-1],ast.Assign)
            self.assertEqual(self.tree.body[-1].targets[0].id,'_stage03_success')
