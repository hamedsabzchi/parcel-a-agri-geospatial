"""Check scientific meaning in the user-facing captions, including edge cases."""
from pathlib import Path
import subprocess
import unittest


class NarrativeTests(unittest.TestCase):
    def test_captions_and_follow_up_checks(self):
        result=subprocess.run(['node','--test',str(Path(__file__).with_name('narrative.test.cjs'))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
