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

## Stage 02 - Find available agricultural data

[![Open Stage 02 In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hamedsabzchi/parcel-a-agri-geospatial/blob/main/notebooks/02_data_discovery.ipynb)

Run the single cell. Approve Google access if asked.

You receive an AOI map, a short list of datasets with valid samples, the GAEZ result out of 16 assets, and one downloadable ZIP with the complete 48-source inventory and supporting evidence.

The notebook contains its required project files, prepares its own Python environment, and refreshes its code on every run. It needs no GitHub token. Open the latest notebook from the button above; an older Colab copy remains an older version.

Stage 02 checks metadata and small samples. Agricultural analyses and full data collection come later. Current GAEZ maize passes only when all 16 selected assets pass; additional crops and future GAEZ scenarios remain deferred.

[Technical details and maintenance](docs/02_stage02.md)
