# Stage 04 — Future scenario summary

[Open in Google Colab](https://colab.research.google.com/github/hamedsabzchi/parcel-a-agri-geospatial/blob/main/notebooks/04_future_scenario_summary.ipynb)

Run the cell and upload your completed **Stage 03 ZIP**.

The **Stage 04: Future Scenarios Summary** tab answers four questions:

- How suitable does the area look, and do the five models agree?
- What modelled yield is indicated, including valid zero-yield areas?
- How do the results differ across future periods?
- How do rainfed and irrigated cases compare?

Read the four headline findings, then the captions below each map and graph. Captions update with your selections. The final section identifies what to check next: local crop conditions, model disagreement, uncovered areas, zero-yield cells or water requirements, as relevant to the evidence.

Full statistics, alternative map views, the complete scenario table, model values and downloads remain in expandable sections. Calculations and source data are unchanged. To use this revised layout, reopen the notebook from GitHub and rerun it with the original Stage 03 ZIP.

Download `stage04_future_scenario_summary.zip`, extract it, and open `dashboard/parcel_a_data_inventory.html`. All existing Stage 03 tabs remain available. The extracted dashboard works offline.

Stages 1, 2 and 3 in this repository are unchanged. Stage 04 uses the evidence already inside the Stage 03 ZIP; it does not request Earth Engine access or download more analytical data. Initial software setup needs internet access. The Colab preview shows the dashboard; package-relative downloads work from the extracted ZIP.

[Implementation guide and clarifications](../docs/stage04_implementation_guide.md) · [Original supplied guideline](../docs/source_guides/stage04_future_scenario_summary_original.txt)

## Development

Use Python 3.11–3.13. Install `stage04/requirements-lock.txt`, then run `python -m playwright install --with-deps chromium`.

```bash
python tools/build_stage04.py --check
PYTHONPATH=stage04/src python -m parcel_a_stage04 \
  --input /path/to/completed-stage03.zip \
  --output-base /path/to/stage04-runs \
  --result-path /path/to/result.json
```

The separate `stage04-quality` workflow checks all previously accepted repository file hashes, reruns the unchanged Stage 03 tests, and tests Stage 04 calculations, source conflicts, package preservation and offline desktop/mobile interactions. Its analytical inputs are explicitly synthetic test fixtures. They are not project findings and are rejected by the normal notebook worker.
