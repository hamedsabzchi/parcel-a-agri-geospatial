from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestStage02Notebook(unittest.TestCase):
    def test_notebook_is_simple_and_registry_driven(self) -> None:
        notebook = json.loads((ROOT / "notebooks/02_data_discovery.ipynb").read_text())
        text = "".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        self.assertIn("SUCCESS: Stage 02 data discovery completed", text)
        self.assertIn("## 1 Setup", text)
        self.assertIn("## 10 Save outputs", text)
        self.assertNotIn("FAO_GAEZ_V5_CURRENT", text)
        self.assertIn("load_dataset_registry", text)
        self.assertIn("PROJECT_BUNDLE_B64", text)
        self.assertNotIn("GITHUB_TOKEN", text)
        self.assertIn("Verified datasets for the analysis pipeline", text)
        self.assertIn("progress=lambda _: None", text)


if __name__ == "__main__":
    unittest.main()
