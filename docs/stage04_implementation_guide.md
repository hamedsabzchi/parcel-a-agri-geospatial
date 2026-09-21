# Stage 04 implementation guide

This clarification accompanies the [complete original supplied guideline](source_guides/stage04_future_scenario_summary_original.txt), which is retained without alteration. It makes the calculations and packaging rules unambiguous and maps them to executable checks. Existing Stage 1, 2 and 3 code, notebooks, data, documentation and workflows stay unchanged.

## User workflow

1. Open [Stage 04 in Colab](https://colab.research.google.com/github/hamedsabzchi/parcel-a-agri-geospatial/blob/main/notebooks/04_future_scenario_summary.ipynb).
2. Run its single cell and upload the original completed Stage 03 ZIP.
3. View the new scenario tab and download `stage04_future_scenario_summary.zip`.
4. Extract the ZIP and open `dashboard/parcel_a_data_inventory.html`. This is the same dashboard entry point, with one additional tab. Use the extracted dashboard for file downloads and offline use.

The notebook embeds its versioned Stage 04 code and locked dependencies. It does not clone a private repository, request a GitHub token, connect to Earth Engine, reuse analytical caches, or require code editing. Internet access is needed to install software and the browser used for automated QA. The analytical evidence comes exclusively from the supplied ZIP.

## Scientific clarifications

| Topic | Executable rule |
|---|---|
| Five models | Exactly GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR, MRI-ESM2-0 and UKESM1-0-LL, one each. ENSEMBLE is never a sixth model. |
| Scenario identity | Crop × period × SSP × management; product is resolved separately. Only verified combinations enter selectors. |
| Spatial support | Preserve Stage 03 native analytical units and fractional intersection hectares in EPSG:6933. Recheck membership, source cells, geometry, overlaps and area closure. No resampling or interpolation. |
| Product denominators | Suitability and yield can have different common valid areas and unit counts. Keep and display them separately. Managements and periods also retain their own support. |
| Whole-AOI label | Retain **Whole-AOI mean, valid zeros retained**. Its denominator is yield common valid area. When coverage is partial, prominently show that percentage and explain that uncovered area is not estimated. |
| Mean | Calculate the equal-weight mean of the five values within each unit, then the intersection-area-weighted spatial mean. Do not weight all source raster cells equally. |
| Positive yield | A unit is positive when its five-model mean is greater than zero. This criterion is fixed for cards, trends and tables. A selected SD, CV, range or other map diagnostic never changes the population. |
| Source-defined positive criterion | The accepted Stage 03 contract has no alternative positive-area definition. A future conflicting source-defined criterion blocks the affected product until its adapter is documented; it is not silently replaced. |
| Valid zero yield | A unit has valid zero yield when its five-model mean is zero. Include individual model zeros in all five-model calculations. Zero spread among identical positive yields is not zero yield. |
| NoData | Exclude masked, outside-footprint, NoData and non-common areas. Report their source-defined exclusions. Never convert valid zero to NoData. |
| Area closure | Positive-yield area + valid zero-yield area = yield common valid area, within the documented relative tolerance of 0.0001 of AOI area. Geometry areas use the same tolerance. |
| Positive-area mean | Weighted mean of unit five-model means over positive units only. If positive area is zero, return null with an explicit reason. |
| Yield units | Preserve kg dry weight/ha, the equivalent readable label for the source's kg (DW)/ha. No observed-yield, production or economic interpretation. |
| Spread | Five-model minimum, maximum, range, median, linear-quartile IQR, and population SD. CV = population SD / mean only when mean > 0. |
| Spatial CV | Area-weighted mean of defined unit CV ratios. Report defined-CV area separately. This is not CV of spatially aggregated model means. Display a ratio to at least two decimal places. |
| Categorical suitability | Preserve exact source captions and colours. Never average class codes. A modal class exists only for a unique mode. Retain ties explicitly. |
| AOI dominant class | Largest intersection area assigned a unique unit-level modal class. An equal largest-area tie remains undefined. Tied units remain in the common-area denominator. |
| Agreement | Full = 5/5; strong = at least 4/5, including full; majority = exactly 3/5 unique mode; tied/dispersed = modal count below 3. Full and strong percentages are overlapping, not additive. |
| Temporal comparison | Four discrete 20-year periods, with gaps for unavailable combinations. No annual interpolation, extrapolation, forecast probabilities or categorical numeric trend lines. |
| Management comparison | Side-by-side HILM and HRLM with coverage and source definitions. No irrigation-benefit subtraction or feasibility claim. |
| Display domains | Shared finite native-unit range by crop and diagnostic across verified scenarios. Also show selected-scenario extrema. Display palette is labelled as a project choice; source categorical colours are preserved. |
| Precision | Full precision in CSV/JSON. Display hectares/yield to two decimals, percentages to one (small positives as <0.1%), and CV to three decimals. Missing values include a reason. |

## Source contract

This version adapts the accepted Stage 03 v3.23 package. It resolves the following contained evidence and records per-product field mappings in CSV and JSON:

| Evidence | Package source |
|---|---|
| Individual-model metadata, scenario codes, units, scales, NoData, masks, local paths, licences and limitations | `metadata/layer_catalog.json` |
| Clip verification and SHA-256 | `metadata/maize/supplemental_verification.json` |
| Five-model groups, support areas and existing aggregate diagnostics | `metadata/maize/five_model_summary.json` |
| Five native model values, analytical-unit hectares and source-cell joins | `tables/maize_model_units.csv` |
| Independent support record and quality flags | `tables/maize_common_support.csv` |
| Original source-cell validity, values and intersections | `tables/source_cells.csv` |
| Class captions and colours | `metadata/legends.json` |
| AOI geometry and denominator | `clipped_data/vectors/parcel_a.geojson`, original embedded dashboard summary |
| Native analytical geometry | Exact `analytical_geometry_path` referenced by the complete-support modal-count or mean-yield layer |
| Existing QA and unsupported future continuous suitability | `qa/maize_validation_report.json`, `metadata/maize/blocked_future_continuous.json` |

Every mapping records source, property, units, denominator, joins, validation rule, fallback and status. Conflicting values, duplicate keys, unknown quality flags, missing verification or incompatible source semantics disable the affected product. Other verified products remain available. Required global evidence, unsafe packages or invalid input checksums stop the run with a retained log.

The original guideline's prohibitions remain: no external analytical values, inferred filename values, invented units, categorical averaging, ENSEMBLE reinterpretation, hidden source substitution, crop ranking, investment decision, production estimate or unsupported recommendation.

## Dashboard scope and isolation

The added tab is exactly **Stage 04: Future Scenarios Summary**. It contains cascading crop/period/SSP/management/product controls; separate suitability and yield diagnostics; an executive summary; coverage and model-count cards; native-unit maps with five-value popups; agreement and spread indicators; discrete period comparisons; management comparisons; a searchable, sortable scenario table; an accessible native-unit table; limitations; and local evidence/download links.

The extension uses `#stage04`-scoped CSS and `window.ParcelAStage04`. It adds event listeners without replacing original ones. Maps initialize when the tab is opened; only the selected scenario geometry is active. Data, CSS and JavaScript are embedded for `file://` use. There is no analytical HTTP request, CDN dependency or required basemap connection.

Original HTML is extended with reversible literal insertions at three anchors. Removing those exact additions recreates the original bytes. All other original files are retained byte-for-byte. Stage 04 assets use new paths; the existing scripts, CSS, IDs, tables, maps and downloads are preserved.

## Packaging and checksum clarifications

1. Extract into a new timestamped run directory. Reject extracted-folder input, unsafe ZIP paths, duplicate members, unsupported input, previous Stage 04 packages and failed original checksums.
2. Record input name, bytes and SHA-256, then inventory every original relative path, size and SHA-256.
3. Run an actual offline browser baseline before inserting the new tab.
4. Create Stage 04 outputs, run the browser regression, and record all checks and gaps honestly.
5. Keep the original Stage 03 checksum manifest unchanged. Its dashboard digest describes the original HTML. The additive change manifest records the original and extended HTML digests; the new Stage 04 checksum manifest describes the final package.
6. The output file manifest excludes itself and the checksum ledger to avoid self-referential hashes. The checksum ledger covers the output manifest and all other final files, excluding only itself. Final file count is recorded in the run summary and receipt.
7. The final ZIP cannot contain its own SHA-256. Record its actual size and hash **after creation** in the adjacent `stage04_run_receipt.json` and expose those values in the notebook. The analytical deliverable remains one ZIP.

Output records include methodology, source contract, scenario summary CSV/JSON, baseline inventory and browser results, QA JSON/CSV, change manifest, processing history, run summary, output file manifest, final checksums, and separate completed-ZIP receipt. The input ZIP is not embedded into the output.

## Verification and completion

| Guideline requirement | Check |
|---|---|
| Preserve accepted repository stages | Git blob hashes for all 139 files from accepted commit `417e4f40122bc2cee1e2bec35aeaa02ea19b9a2b`; only new files added |
| Preserve accepted package | Every original relative path retained; every non-dashboard SHA-256 unchanged; dashboard insertions reversible |
| Scientific correctness | Hand-calculated tests for area weighting, valid zeros, zero-positive-area, zero/undefined CV, modes/ties, agreement overlap, partial coverage and distinct model membership |
| Evidence consistency | Cross-check source cells, native geometry, analytical tables, verification hashes, support tables, original aggregates, legends, source units and QA flags |
| Original dashboard regression | Open every original tab and exercise every original map, table and chart, opacity, AOI zoom, comparison controls and CSV export |
| New tab | Exercise every verified combination and available map diagnostic, trend selection, filtering, sorting, CSV export, repeated activation and keyboard interactions |
| Offline and responsive use | Real Chromium on `file://` with network disabled; desktop and mobile widths, readable controls, contained table scrolling and no browser exceptions |
| Packaging | Reopen ZIP, verify members/CRC, hash final files, resolve local evidence links and record completed ZIP size/SHA-256 |
| Reruns | New timestamped output for every run; never reuse a previous Stage 04 analytical package |

**COMPLETE** means required evidence resolved and all QA passed. **COMPLETE_WITH_DOCUMENTED_GAPS** means usable verified combinations remain, gaps are explicit, and package/browser QA passed. **INCOMPLETE** means a required gate failed or no verified combination remains. A failed browser check cannot produce a success status.

Development checks use synthetic fixtures, clearly labelled in QA and artifacts. They validate the implementation; they do not validate the user's actual Stage 03 evidence. The user's ZIP is validated when the notebook runs. No test fixture is accepted as normal analytical input.
