# Stage 03 maize extension — 03.1 through 03.23

Run the single Stage 03 Colab cell with a completed Stage 02 or Stage 03 ZIP. A completed Stage 03 package is reused after checksum, boundary and inventory validation. The results open in the same five-tab dashboard. Filters select available product, period, scenario, model, management and view. Technical evidence stays in downloadable tables and methods.

## Preserve the accepted work

The core extraction pipeline, 48-source registry, 16 required GAEZ assets, AOI, non-FAO products, soil data, WaPOR, terrain, historical series, legends and existing exports remain available. The original package is copied without alteration to `metadata/core_baseline/`; original map, graph and native-data files also keep their original paths and bytes. Aggregated tables append new rows while preserving original rows and columns. Every upgraded run creates a new directory and ZIP. No earlier output is overwritten.

The 16/16 core count and 254 supplemental source count are separate. A list of source filenames is not evidence of a completed AOI extraction. The original Stage 02 checksum contract is unchanged; supplemental objects are held in `config/stage03/maize_sources.json`.

## Exact analytical scope

| Product | Periods and sources | Supplemental rasters |
|---|---|---:|
| RES05-SXX30AS | Historical 2001–2020 AgERA5; HRLM, LRLM, HILM, LILM | 4 |
| RES05-SIX | Four future periods × three SSPs × five GCMs × HRLM/HILM | 120 |
| RES05-SIX ENSEMBLE | 2021–2040; SSP126/370; HRLM/HILM | 4 |
| RES05-YXX | Four future periods × three SSPs × five GCMs × HRLM/HILM | 120 |
| RES05-YXX ENSEMBLE | 2021–2040; SSP126/370/585; HRLM/HILM | 6 |

Every raster has its exact matching JSON sidecar. The supplied names are parsed and deduplicated from the preserved guide, not invented from a cross product. All five individual models are GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR, MRI-ESM2-0 and UKESM1-0-LL. Future periods are 2021–2040, 2041–2060, 2061–2080 and 2081–2100; scenarios are SSP1-2.6, SSP3-7.0 and SSP5-8.5. Rainfed high-input and irrigated high-input management remain separate.

Future RES05-SXX30AS has one dataset-level `BLOCKED_BY_PUBLIC_SOURCE_AVAILABILITY` record. The two supplied unsuccessful prefix checks and their unspecified original observation date are retained. The report generation time is not represented as a new source observation. There are no inferred future 1 km URLs, empty analytical layers, selectors, statistics or maps. Crop Water Indicators require a dedicated subsequent metadata review. Other crops, production, yield gaps, revenue, rankings and recommendations are outside this extension.

## Verification and source evidence

Public HTTP byte ranges read only a bounded native AOI window. A server that does not honor ranges is rejected; full global TIFF download is prohibited. Exact filename dimensions, JSON identity, CRS, grid origin, spacing, dimensions, band count, datatype, scale, offset, NoData, internal validity mask, AOI overlap and observed value ranges are checked. The clip is reopened and its raw values, mask, transform, CRS, dimensions and datatype compared with the source window. Statistics use native values, never rendered colours or map tiles.

Receipts retain retrieval UTC, source URL, source JSON, source metadata, sanitized HTTP headers (including object generation and checksum when supplied), local SHA-256, AOI SHA-256, code SHA-256, licence and guide references. Successful cached clips are reused only after checksum verification; failures are retried on rerun. Public product metadata and SLD files are retained under `metadata/maize/source_metadata/`, with parsed SLD entries and retrieval evidence. The guide's metadata, README and dimensional-resource links remain in every source record. The directly accessible official bucket mapset metadata supplies the decoding contract; a catalogue link is not treated as proof of AOI coverage.

`VERIFIED_INSIDE_AOI`, `VERIFIED_BUT_EMPTY_INSIDE_AOI` and `NO_COVERAGE` are distinct from remote, metadata, range and clip failures. Technical failures make the extension incomplete. Verified empty or missing spatial coverage is reported as a coverage gap. No failure is silently converted to a valid empty raster. Conditional historical irrigated SXX coverage reflects the source 2020 existing-cropland mask; absence does not demonstrate that irrigation development is infeasible.

## Units, masks and legends

SXX is a continuous index, 0–10000; NoData is −9. Its shared display scale is fixed at 0–10000 for every management. Project Viridis is explicitly labelled and the official SXX style is preserved as source evidence; no conversion to SIX classes is inferred.

SIX contains nine categorical codes, with 0 as NoData. It retains the accepted historical class captions and colours. Codes are never averaged, interpolated, subtracted, or treated as a numeric suitability range. “Highest/lowest suitability” fields contain source category labels for codes 1–8 only; Water is explicitly excluded from that ordering.

YXX is source-defined attainable yield of the best occurring suitability class, in Kg (DW)/ha; NoData is −9, scale 1 and offset 0. Valid zero is retained. Values must be finite and nonnegative. It is not observed parcel yield or parcel production. Source and derived mean/median/minimum/maximum maps share a pooled historical-plus-future domain separately for each management. Additional historical previews use that shared domain; original historical images remain unchanged. SD, IQR, range and CV have their own units and legends. Map colours alone must not be used to compare different metrics.

## Area and common support

Original cell edges and the AOI are densified and intersected in EPSG:6933. Each cell is weighted by its actual AOI intersection area. Valid, masked and outside-footprint areas must sum to the AOI area within 0.01%. The exact native values and intersection hectares are retained. Fewer than five contributing cells are labelled `FEW_NATIVE_CELLS`; cell counts are not independent observations.

A five-model result requires five distinct, technically verified individual GCMs with identical product, period, SSP and management dimensions. ENSEMBLE is never a sixth model. Missing inputs leave the group pending; technically verified empty inputs can yield `NO_COMMON_VALID_SUPPORT`.

Common support is the geometric intersection of all required valid native cells. Aligned grids use the exact shared cells. Different grids are intersected as geometric partitions without statistical resampling. Each result reports total AOI area, common-valid area, masked exclusions, outside-footprint exclusions and per-source native cell counts. Derived rasters are exported only where the native grids align; otherwise exact GeoJSON partitions are the analytical output and a display-only raster preview is labelled accordingly. This avoids fabricating a finer analytical grid.

## Descriptive five-model measures

Categorical units retain all five classes, frequencies for all nine classes, unique modal class when one exists, tied modal classes, modal count, unanimous agreement, ≥4/5 strong agreement, 3/5 majority, unique class count, modal ties and tied/dispersed status. A 2/1/1/1 split has a unique mode but is still dispersed; a 2/2/1 split has no unique mode. Ties are not broken. Modal maps mask ties; separate tie and dispersed maps retain them. Class-specific modal and unanimous areas are retained. All ten model pairs have matching area and matching percentage on the five-model common support. These are project-derived descriptions, not FAO confidence, uncertainty probabilities or forecasts.

Yield units retain all five values and their arithmetic mean, median, minimum, maximum, population SD, linearly interpolated IQR, range and CV. CV is SD divided by a strictly positive mean; otherwise it is unavailable with a reason. All ten pairwise differences use model B minus model A. AOI source summaries use exact common-support area weights. Per-unit model metrics are spatially summarized separately from the spread of the five AOI model means; these operations are not interchangeable. Weighted spatial quantiles use the first sorted value at cumulative normalized area weight ≥ p.

## Matched comparisons

Historical/future comparisons match product and management; the different climate sources and time periods mean the differences are descriptive, not attributable climate-only effects. SIX comparisons report class transitions and unchanged areas. YXX comparisons report native-unit differences and percentage differences only where baseline values are nonzero. The area on which percentages are defined is reported. Percentage change of the two area-weighted AOI means is separate from the weighted average of cell percentage changes.

Cross-SSP comparisons hold period, GCM and management fixed. Cross-period comparisons hold SSP, GCM and management fixed. Every pair is recomputed on its own exact common valid support. Five-model derived comparisons use the common support of all ten contributing source layers. Tied modes are excluded only from modal comparisons and their area is reported; agreement and category-spread comparisons retain their valid support. There is no unlabelled all-SSP or all-period common mask.

ENSEMBLE is a separate diagnostic source label. Its aggregation formula is not assumed to be a mean, median or mode. Suitability diagnostics compare it with the unique five-model mode on shared valid support and report excluded ties. Yield diagnostics compare it with the project-derived five-model mean; neither is presented as validation against truth.

## Outputs and limits

The package includes native clips and sidecars, static maps, charts, source-cell tables, categorical and continuous summaries, five-model units, frequencies, ten-pair comparisons, common-support accounting, historical/future transitions and yield differences, cross-SSP/period source and derived comparisons, ENSEMBLE diagnostics, and verification CSV/JSON for each addendum and future product/period. Stable IDs link dashboard maps, legends, metadata, tables, charts and downloads. Both legends are visible for side-by-side maps, including the explicitly labelled SIX/SXX juxtaposition.

The original tests remain active. Additional tests exercise exact source counts, completed listing gaps, ties, water, valid zero, masked support, shifted grids, model identity, all ten pairs, zero-denominator percentages, source verification, immutable core outputs, package checksums and offline dashboard controls. Synthetic fixtures are labelled and never asserted to be actual AOI observations. Live bounded checks establish that the adapters can read representative official sources; each user run still verifies every selected asset.
