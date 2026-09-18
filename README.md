# Parcel A Agricultural Geospatial Analysis

This repository contains the reproducible, step-by-step geospatial analysis workflow for Parcel A in the Central Plain of Dir 1, Mbéré Department, Adamaoua Region, Cameroon. Every stage is designed to run in Google Colab and to remain auditable in GitHub.

## Current status

Stage 01 is complete: reconstruction, validation, and visualization of the study-area boundary.

The initial boundary was reconstructed from the seven survey vertices listed in the French final characterization report. The map in that report identifies the coordinate reference system as `WGS 84 / UTM Zone 33N`. The polygon calculated from those vertices covers `5127.48 ha`; the report states `5128.69 ha`. The difference is `1.21 ha`, or approximately `0.024%`.

The geometry is technically valid and suitable for workflow development and preliminary visualization. However, quality gate `G0` remains `HOLD` until the project owner or survey team confirms the reconstructed boundary. Expensive extractions and definitive farm-level decisions must not start before that confirmation.

## Run Stage 01 in Google Colab

1. Open `notebooks/01_define_and_display_aoi.ipynb` in Google Colab.
2. Select **Runtime > Run all**.
3. The default `report_vertices` mode runs without Google Earth Engine.
4. If an official boundary is available, change `SOURCE_MODE` to `upload` and upload a GeoJSON, GPKG, KML, or ZIP containing a Shapefile.
5. If the official boundary is stored in Google Earth Engine, change `SOURCE_MODE` to `earth_engine_asset` and enter the Asset ID and Google Cloud project ID.
6. After visual and institutional confirmation, set `AOI_APPROVED=True` and run the notebook again.

## Stage 01 outputs

- `data/aoi/aoi_candidate_wgs84.geojson`: reconstructed boundary in WGS84
- `data/aoi/aoi_candidate_utm33n.gpkg`: analysis-ready boundary in UTM Zone 33N
- `data/aoi/source_vertices_utm33n.csv`: source vertices transcribed from the report
- `data/aoi/aoi_candidate_summary.json`: area, perimeter, centroid, and validation status
- `outputs/maps/01_aoi_candidate.html`: interactive map
- `outputs/maps/01_aoi_candidate.svg`: static, internet-independent map
- `outputs/maps/01_aoi_candidate.png`: rendered map preview
- `outputs/tables/01_aoi_validation.csv`: validation summary

## Repository structure

```text
parcel-a-agri-geospatial/
├── config/             Stable project configuration
├── data/aoi/           Study-area boundary and metadata
├── docs/               Decisions and methods
├── notebooks/          Numbered Google Colab workflows
├── outputs/            Reproducible maps and tables
├── src/parcel_a_geo/   Shared Python utilities
├── tests/              Automated quality tests
└── tools/              Rebuild and validation utilities
```

## Reproducibility rules

Raw inputs remain immutable. Every dataset must be registered with its provider, product name, version, access date, coordinate reference system, spatial and temporal resolution, and license. Every analysis must be reproducible from a numbered notebook.

## Next stage

After `G0` passes, Stage 02 will create the comprehensive data inventory and test AOI coverage for FAO sources - including GAEZ v5, WaPOR, SoilFER, Crop Suitability App, and CAVA - and for prioritized non-FAO sources.
