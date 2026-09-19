# Stage 03 — Extract, summarize and visualize

Open `notebooks/03_data_inventory_visualization.ipynb` and run its single cell.
Supply the complete Stage 02 ZIP when asked and approve Google access if selected layers require it.
The output is a dashboard and one ZIP. Extract the ZIP and open
`dashboard/parcel_a_data_inventory.html`. Thematic maps, tables, graphs and downloads work offline.
Only the optional light/satellite backgrounds need internet.

The source inventory retains all 48 Stage 02 sources. The layer inventory contains
the exact selected products and records failed, empty, deferred and catalogue-only work.
The core reuses the 16 verified GAEZ native clips. Other maps and series are conditional
on the user's final Stage 02 decisions. The notebook never reruns source discovery.

## Inputs and environment

Supported input: the Stage 02 manifest 2.5 package written by compatible commit
`6911341a75c69fa7389579f22f2516bb133d7920`, with its `stage02a/`, `stage02b/` and `final/`
roots. Every declared hash is checked; all required evidence and clips must be covered.
The final inventory must contain the exact 48 unique registered IDs. The GAEZ report,
verified manifest, final decision and 16 exact assets must agree. The bundled original
AOI must match the Stage 02 SHA-256. Unsafe ZIP paths, duplicates, symlinks and excessive
expansion are rejected. Older or incomplete packages need an explicit adapter; they are
never repaired automatically. Original Stage 02 decisions are retained as evidence.

One run is selected explicitly (`STAGE02_INPUT`), from a single candidate in the current
project's Stage 02 run folder, or through one upload prompt. Multiple runs are never
merged and an arbitrary latest run is never selected. The notebook bundles its code,
configuration, metadata crosswalks and AOI, so no private-GitHub clone/token is required.
An environment keyed by Python version and the Stage 03 lockfile runs the geospatial
worker. Stages 01 and 02, their source bundles and dependencies are unchanged.

Local execution, after installing `stage03/requirements-lock.txt` in an isolated environment:

```bash
PYTHONPATH=stage03/src python -m parcel_a_stage03 --root . \
  --input /path/to/stage02_all_in_one_results.zip \
  --output-base outputs/stage03_runs --result-path stage03_result.json
```

Authenticate Earth Engine in that environment first when using eligible EE layers.
The default project is `practical-proxy-441422-n6`; the notebook respects `EARTH_ENGINE_PROJECT`.
Connection failure is explicit. A fully local selection requires no Google consent.

## Selection and scope

Only verified `USE_NEXT` sources with exact configured products are selected automatically.
Verified `USE_LATER`/`OPTIONAL` products require `enable_later: true`. All selected non-GAEZ
layers are optional by default; GAEZ is required. Unverified, metadata-only, unavailable,
manual or failed sources remain visible with their next actions. A verified sample does
not prove all dates, variables or depths; each extraction has its own QA.

`config/stage03/` defines source selection, legends, methods, dates and budgets.
Default series period: 2024-01-01 through 2025-01-01, end exclusive. Longer periods require
an explicit configuration change. The source registry is not a request for all years or
all bands. Future-climate sources, CAVA scenario work and other GAEZ crops are deferred
until an explicit model/scenario/period or crop plan is selected.

WorldCover, Dynamic World, Copernicus DEM/slope, JRC water, selected soil data, ERA5-Land,
CHIRPS, WaPOR and optional alternatives use only their exact configured collection/API.
WaPOR Level 2 AETI is selected only if that exact product appears as a valid Stage 02 sample;
an NPP or transpiration sample does not authorize substituting AETI. SoilGrids WMS images
and OSM count responses remain catalogue evidence, never numeric rasters or fabricated
features. User-supplied data require a separate checksum, units/legend, CRS and AOI check.
The `supplemental_files` list in `stage03_config.yml` accepts explicit raster/vector layer
definitions linked to a retained source ID. Required fields are `layer_id`, `dataset_id`,
`display_name`, `local_path`, `expected_sha256`, `variable`, `data_type`, `unit`, `mask_rule`,
`licence`, `licence_url`, `source_url`, `metadata_url` and `limitation`. Categorical inputs
also require a `legend_id` with source-backed captions in `symbology.yml`. The original
Stage 02 decision remains unchanged; independent verification appears in
`metadata/supplemental_verification.json`. Vectors retain source attributes and IDs in a
GeoPackage; an optional `context_buffer_metres` layer is excluded from AOI feature counts.

## Native grids, masks and area

All analytical clips retain their native grids. Bounded Earth Engine windows use explicit
CRS, affine transform and dimensions; there is no whole-global-raster fallback or silent
coarsening. Raw values and masks remain in the package. Physical units are decoded once
for statistics. Stage 02 GAEZ clips can have `nodata=None` and a valid internal mask.
Zero is not implicitly missing: zero irrigation share and zero yield remain valid.

Cell weights are the positive physical areas of native cells intersected with Parcel A
in EPSG:6933. AOI edges are densified to 0.0005 degrees; cell edges to eight segments per
edge before transformation. Boundary-only touches have zero weight. The denominator is
the equal-area AOI, not a count of touched pixels. Valid area + masked area + area outside
the raster footprint must close to the AOI within 0.01%. Stage 01's original UTM area is
reported separately; neither number is forced to match the other.

Categorical summaries give hectares, percent of valid area and percent of the entire AOI.
Class codes are never averaged. Continuous means and population SD use intersection-area
weights. Weighted quantiles are the first sorted value whose cumulative normalized weight
reaches the requested probability. Missing values yield null statistics, not zero. A single
cell has SD zero, which is not uncertainty. Fewer than five valid native cells are flagged;
charts show cell values and weighted means, without box plots or confidence intervals.
These are distinct cells, not statistically independent observations.

DEM slope uses a 120 m buffered mosaic, reprojects elevations to a 30 m EPSG:32633 grid
with bilinear interpolation, applies central differences with horizontal/vertical units
in metres, converts to degrees and then masks the AOI. This is a derived surface-terrain
descriptor, not a measured soil slope. Display rasters use EPSG:3857 and nearest-neighbour
reprojection, separately from analytical data. Display pixels never enter statistics.

## GAEZ interpretation and a correction to the guideline

Official JSON definitions and per-product CC-BY-4.0 licence evidence are pinned under
`config/stage03/source_metadata/`. Full source captions are preserved. Display colours
are explicitly project colours unless taken from a documented product palette.

- AEZ57 uses all 57 official class captions.
- LGP uses official growing-period class captions, separately for 1981–2000 and 2001–2020.
  Codes 14–16 retain the exact source text; no threshold or meaning is invented.
- **SQX is encoded as classes in the actual FAO mapset metadata**, although the original
  Stage 02 manifest called it an index. Classes 1–10 denote source rating ranges, 11 is
  permafrost, 12 is not evaluated, and 13 is water. Stage 03 consequently treats SQX as
  categorical and does not average its codes or reinterpret them as continuous ratings.
- SQ-IDX uses the actual 11-code crosswalk. Code 1 means no or slight constraints,
  not automatically nutrient availability; special terrain, permafrost and water classes
  are retained. High and low input levels remain separate.
- Irrigation share uses source-cell **cropland** as its denominator. Its AOI-weighted value
  is contextual and is not converted to irrigated hectares. Lineage years are not a series.
- Maize suitability preserves the source's 1–9 classes and threshold phrases. One shared
  project palette is used across the four historical management alternatives.
- Maize attainable yield is kg dry weight/ha for the best occurring suitability class in
  each source cell. A common pooled min/max Viridis domain serves all four management
  alternatives. Constant data receive a single-value legend. The dashboard shows valid
  support for each alternative. No parcel-wide measured yield or total production is inferred.

Fractional area improves geometry accounting; it does not make coarse GAEZ data field-scale.
Climate scenario `HIST` is distinct from HRLM/LRLM/HILM/LILM management codes.

## Time aggregation

Native timestamps, source image IDs, raw stacks and conversions are retained. Source QA
is applied before per-cell aggregation, then per-cell temporal completeness is checked,
then the accepted cells are area-weighted over the AOI. Spatial and temporal percentages
are reported separately. Daily amounts are summed through time, never across pixels as
rainfall depth. Missing intervals are NaN, not zeros. Rejected periods stay in the audit
table with null values and appear as chart gaps.

The default 90% spatial/temporal acceptance thresholds are configurable project choices,
not universal scientific standards. Incomplete sums remain labelled `PARTIAL_TOTAL` even
when accepted. A one-year seasonal pattern is not a climatology. Temporal coverage is the
area-weighted fraction of requested days supported by valid native intervals; observation
count is the number of native intervals with at least one valid intersecting cell.

| Product | Decode and estimator |
|---|---|
| CHIRPS daily precipitation | mm amounts; sum valid days per cell, then AOI-weighted monthly depth |
| ERA5-Land temperature | K − 273.15; duration-weighted mean |
| ERA5-Land daily precipitation sum | m × 1000; monthly sum; negative packing artifacts retained in raw data, flagged and rejected rather than clamped |
| WaPOR AETI | raw × 0.1 gives mean daily mm/day; integrate over actual dekad duration, including last dekads and leap years |
| MOD13Q1 NDVI/EVI | raw × 0.0001; SummaryQA 0/1; duration-weighted 16-day composite means, not sums |
| TerraClimate precipitation / tmmx | monthly mm amount / raw × 0.1 °C; correct amount/state estimator |
| NASA POWER T2M | UTC point API at AOI centroid; retain returned units and coordinates; spatial coverage is not applicable |

Rates/states are treated as constant within their native interval for boundary allocation;
interval amounts are apportioned by overlap duration. Duplicate/overlapping native dates
are rejected until an explicit mosaic rule is provided. Time-series uniqueness uses layer,
variable, interval, spatial statistic, temporal method and relevant depth/management fields.

Dynamic World uses the modal confident native labels, not average class codes or argmax
of mean probabilities. Source cloud masks, probability ≥ 0.6 and at least three scenes
per cell are project settings. Equal class counts use the lowest source code. Scene IDs,
dates and these choices are recorded. Different land-cover products are not silently fused.

## Dashboard, downloads and run outcomes

Five tabs: Overview, Maps, Tables, Graphs, Data and Methods. Maps provide grouped overlays,
active legends, opacity, native-cell popups, reset, scale, coordinates and full screen.
Synchronized maize comparisons retain common legends/domains and show each valid footprint.
Tables support search, status filters, sorting, pagination and CSV export. Graphs include
class areas, source-defined management comparisons, actual accepted series and separate
coverage graphs. Every map/chart references its underlying data and metadata.

The standalone HTML embeds its data, overlays, JavaScript and CSS. It uses no local JSON
fetches, ES modules, CDN runtime, Earth Engine tiles or expiring links. Leaflet 1.9.4 and
its licence are bundled. Raw analytical rasters remain separate files. All packaged paths
are relative. Static maps include AOI, complete legend, units, scale, north, period and
source information. Chart PNGs come from the same data specifications as interactive charts.

Each run writes a new `outputs/stage03_runs/<run_id>/package/`. The accepted ZIP has
dashboard/, maps/, charts/, tables/, clipped_data/, metadata/, logs/ and qa/ at its root.
It is created outside the payload, excludes caches/credentials/previous runs, and contains
member checksums. The checksum manifest excludes itself. The output manifest excludes
itself and the later checksum file; both exclusions avoid circular hashes.

- `COMPLETE`: all selected layers pass.
- `COMPLETE_WITH_OPTIONAL_GAPS`: required core passes; failed/empty optional layers remain visible.
- `INCOMPLETE`: a required layer or global packaging gate fails. Only a separately named
  diagnostics ZIP is issued; it is not accepted Stage 03 evidence.

Completed bounded downloads are cached by exact source, selection, AOI, dates, QA and
adapter version, with checksums. Reruns reuse verified cache objects and rebuild the fresh
package. A failed or changed unit is retried. Requests are sequential (under the two-request
limit), with bounded retries/timeouts and explicit input/download/memory/dashboard budgets.
No asynchronous Earth Engine export is used, so there are no unpolled export tasks.

Reproducibility means identical analytical data for identical source snapshots, AOI,
configuration and software. Run timestamps/logs and ZIP bytes can differ. Remote checksums
that are unavailable are explicitly marked, never fabricated. Input/output hashes, source
IDs, units, QA, processing, software versions and limitations are retained in the package.

## Verification and Stage 04 handoff

`stage03/tests/` contains isolated synthetic fixtures and mocked services used only in tests.
They never replace a user's Stage 02 data. Separate CI checks input integrity, native masks,
area statistics, temporal estimators, legends, packaging, notebook freshness, offline browser
controls and preservation of Stage 01/02. A user's authenticated live extraction is separate
from those tests; it requires their completed ZIP and Google access.

Stage 04 may use only Stage 03 products with passed extraction/QA, retaining masks, coverage,
native support and limitations. Define agricultural questions and assumptions before adding
new suitability models, trends, yield gaps, decision scores or future scenarios.

## Primary technical references

- [FAO GAEZ source catalogue](https://data.apps.fao.org/catalog/iso/22c4b002-ae80-41f7-9f36-463b546378a2), with exact per-layer links in the layer catalogue.
- [FAO SQX mapset definition](https://storage.googleapis.com/fao-gismgr-gaez-v5-data/DATA/GAEZ-V5/MAPSET/SQX/GAEZ-V5.SQX.json).
- [Earth Engine bounded downloads](https://developers.google.com/earth-engine/apidocs/ee-image-getdownloadurl).
- [ERA5-Land daily aggregates](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR).
- [WaPOR L1 AETI](https://developers.google.com/earth-engine/datasets/catalog/FAO_WAPOR_3_L1_AETI_D) and [official L2 AETI definition](https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets/L2-AETI-D).
- [MOD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1), [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1), [WorldCover](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200).
- [OpenLandMap organic carbon](https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_ORGANIC-CARBON_USDA-6A1C_M_v02), [TerraClimate](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE).
