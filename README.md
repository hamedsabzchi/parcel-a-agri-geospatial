# Parcel A Agricultural Geospatial Analysis

Reproducible Google Colab workflows for agricultural geospatial analysis of Parcel A, Cameroon.

## Stage 01 - AOI visualization

- Display the AOI boundary on satellite, street, and light basemaps.
- Label the seven boundary points.
- Calculate AOI area in hectares.
- Show point X/Y coordinates in `EPSG:32633`.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hamedsabzchi/parcel-a-agri-geospatial/blob/main/notebooks/01_define_and_display_aoi.ipynb)

In Colab, select **Runtime > Run all**.

## Stage 01 result

- Calculated area: `5,127.48 ha`
- Reported area: `5,128.69 ha`
- Difference: `1.21 ha` (`0.024%`)

## Repository structure

```text
config/             Project configuration
data/aoi/           AOI boundary and coordinates
docs/               Methods and decisions
notebooks/          Google Colab workflows
outputs/            Maps and tables
src/parcel_a_geo/   Shared Python code
tests/              Automated tests
tools/              Build utilities
```

## Stage 02 - Agricultural geospatial data discovery

Stage 02 uses `data/aoi/parcel_a.geojson` to verify FAO and non-FAO dataset coverage and valid data. It uses metadata and small samples only. It does not perform agricultural analysis or large downloads.

[![Open Stage 02 In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hamedsabzchi/parcel-a-agri-geospatial/blob/main/notebooks/02_data_discovery.ipynb)

1. Select **Runtime > Run all**. The notebook contains one runnable cell.
2. On the first run, approve the Google Earth Engine authorization request.

The notebook automatically initializes the existing Earth Engine project used by the owner's other geospatial notebooks. No GitHub token or Colab secret is required.

Outputs:

- `outputs/stage02/tables/data_inventory.csv`
- `outputs/stage02/tables/data_inventory.xlsx`
- `outputs/stage02/metadata/data_inventory.json`
- `outputs/stage02/logs/discovery_log.txt`
- `outputs/stage02/maps/data_coverage_map.html`
- `outputs/stage02/stage02_report.html`

The notebook displays only the AOI, four decision-summary counts, and the verified datasets recommended for later analysis. Detailed statuses and logs are saved in the downloadable results ZIP.

Supported access methods include Earth Engine, REST API, STAC, COG, WMS, direct download, Python SDK, manual portals and local project files.

Status meanings:

- Coverage: `FULL_COVERAGE`, `PARTIAL_COVERAGE`, `NO_COVERAGE`, `COVERAGE_UNKNOWN`
- Valid data: `VALID_DATA`, `VALID_RECORDS`, `NO_VALID_DATA`, `VERIFICATION_FAILED`, `UNKNOWN`
- Access: `AUTOMATED_OPEN`, `AUTOMATED_AUTHENTICATION_REQUIRED`, `MANUAL_DOWNLOAD_AVAILABLE`, `MANUAL_INSPECTION_REQUIRED`, `ACCESS_RESTRICTED`, `UNAVAILABLE`, `VERIFICATION_FAILED`
- Priority: `USE_NEXT`, `USE_LATER`, `OPTIONAL`, `NOT_SUITABLE`, `NO_COVERAGE`, `ACCESS_BLOCKED`, `NEEDS_MANUAL_REVIEW`

Manual portals and authenticated services cannot be confirmed without the required access. Unknown values remain `UNKNOWN`.

Stage 03 will process only datasets marked `USE_NEXT`.
