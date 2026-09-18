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

## Next stage

Inventory and AOI coverage of FAO and non-FAO agricultural datasets.
