# Stage 02 implementation

Open `notebooks/02_data_discovery.ipynb` in Colab and run its single cell. Google authorization is interactive on the first run. The default Earth Engine project is `practical-proxy-441422-n6`; `EARTH_ENGINE_PROJECT` can override it. A failed connection stops the run with an actionable message; it never silently skips Earth Engine.

## Runtime

`tools/build_stage02.py` embeds the required configuration, AOI, every source module, GAEZ manifest and dependency lock into the notebook. GitHub can remain private. A SHA-256 check validates the bundle before extraction. The notebook restores a versioned snapshot on every run, so an old Colab workspace cannot supply a stale GAEZ module.

Dependencies are installed once per lockfile/Python version into a separate environment. The installer uses host pip with `--python`, so Colab does not need `ensurepip`. All geospatial processing runs in that environment, avoiding conflicts with NumPy/GDAL already loaded in a notebook. Authentication runs interactively in the notebook; the worker reuses the Earth Engine credentials through its normal credential location. Credentials are never included in the output package.

Existing project files under `data/local/land_cover` and `data/local/crop_type` remain available through a shared input directory. Stage 01 and its AOI are unchanged. Each Stage 02 run writes a new directory under `outputs/stage02_runs/`, preventing old clips and evidence from entering a new results package.

## Checks and decisions

1. Run every one of the 48 registry entries independently. An endpoint failure does not stop other sources.
2. Verify all 16 selected GAEZ rasters and perform the additional WaPOR, SoilFER, CropSuit, CAVA and ASIS discovery checks.
3. Match FAO evidence by exact dataset ID, preserve all 48 rows, and assign one final status and action per row.
4. Display the AOI, counts and available data samples. Save technical tables, reports, logs, environment versions, source checksums, selected GAEZ clips and the evidence-updated manifest in one ZIP.

`VERIFIED_INSIDE_AOI` requires actual numeric raster/point values or spatially checked features. STAC records, WMS colours, catalogue entries, package metadata and bounding-box counts are retained as discovery evidence and cannot alone qualify as verified data. A sample confirms that sample, not every band, date, scenario, product or pixel in a dataset.

`USE_NEXT` and `USE_LATER` require verified sample evidence. Manual access, failed endpoints, missing local input, absent samples and deferred scope retain explicit separate decisions. No failed request is treated as proof that a source does not exist.

## GAEZ v5

The manifest remains version 2.5 with these 16 selected assets:

| Group | Assets |
|---|---:|
| AEZ57 | 1 |
| Historical LGP (HP0120, HP8100) | 2 |
| SQX SQ0 (HIM, LIM) | 2 |
| SQ-IDX (HIM, LIM) | 2 |
| Irrigated-land share | 1 |
| Maize suitability (HRLM, LRLM, HILM, LILM) | 4 |
| Maize attainable yield (same four combinations) | 4 |

Reads use HTTP byte ranges and bounded native-grid windows. There is no full-global-raster download fallback. `all_touched=True` includes intersecting coarse cells even when their centres fall outside the polygon. Masked arrays, intrinsic and documented NoData, finite-value checks and dataset-specific value rules prevent false valid pixels. Saved clips carry explicit masks so valid zero values survive.

The valid-cell percentage describes selected native cells, not the percentage of AOI area covered. Coarse ~10 km values are contextual evidence; they are not field-scale estimates. Class values must be integers; maize suitability must lie in 1–9, attainable dry-weight yield must be nonnegative, and irrigation share must lie in 0–100. Statistics are native-cell summaries, not area-weighted agricultural conclusions.

The current GAEZ row passes only when exactly the expected 16 unique assets all pass. Partial, missing or duplicated results remain `METADATA_ONLY / REVIEW_GAEZ_VERIFICATION_REPORT`. Future GAEZ CMIP6 assets and other crops remain deferred pending prototype approval. Other registered future-climate sources remain in the inventory.

## Maintenance and verification

Use Python 3.11 or 3.12:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python tools/build_stage02.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/build_stage02.py --check
```

After a source, manifest, registry or dependency change, regenerate and commit the notebook. GitHub Actions checks the exact source/bundle match, locked dependencies, frozen Stage 01 checksums, raster masks, all-16 gate, all-48 integrity and complete ZIP assembly on both Python versions. CI uses synthetic rasters and mocked remote services; it cannot approve a user's Google OAuth request.

References: [Earth Engine authentication](https://developers.google.com/earth-engine/guides/auth), [Rasterio mask and all_touched semantics](https://rasterio.readthedocs.io/en/stable/api/rasterio.mask.html). Official GAEZ asset and metadata URLs are retained in the source manifest.
