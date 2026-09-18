"""Source-adapter factory."""

from __future__ import annotations

from typing import Any

from .api import ApiSourceAdapter
from .base import BaseSourceAdapter
from .cog import CogSourceAdapter
from .earth_engine import EarthEngineSourceAdapter
from .fao_cava import CAVASourceAdapter
from .fao_cropsuit import CropSuitSourceAdapter
from .fao_gaez import GAEZSourceAdapter
from .fao_soilfer import SoilFERSourceAdapter
from .fao_wapor import WaPORManualSourceAdapter, WaPORSourceAdapter
from .local import LocalProjectSourceAdapter
from .manual import ManualSourceAdapter
from .stac import StacSourceAdapter
from .wms import WmsSourceAdapter


def create_adapter(dataset: dict[str, Any], *args: Any, **kwargs: Any) -> BaseSourceAdapter:
    dataset_id = str(dataset.get("dataset_id", ""))
    access_type = str(dataset.get("access_type", "MANUAL_PORTAL"))
    if dataset_id.startswith("FAO_GAEZ"):
        adapter = GAEZSourceAdapter
    elif dataset_id == "FAO_WAPOR_V3_L1":
        adapter = WaPORSourceAdapter
    elif dataset_id.startswith("FAO_WAPOR"):
        adapter = WaPORManualSourceAdapter
    elif dataset_id == "FAO_SOILFER":
        adapter = SoilFERSourceAdapter
    elif dataset_id == "FAO_CROPSUIT":
        adapter = CropSuitSourceAdapter
    elif dataset_id == "FAO_CAVA":
        adapter = CAVASourceAdapter
    else:
        adapter = {
            "EARTH_ENGINE": EarthEngineSourceAdapter,
            "REST_API": ApiSourceAdapter,
            "STAC_API": StacSourceAdapter,
            "CLOUD_OPTIMIZED_GEOTIFF": CogSourceAdapter,
            "WMS": WmsSourceAdapter,
            "WMTS": WmsSourceAdapter,
            "LOCAL_PROJECT_DATA": LocalProjectSourceAdapter,
        }.get(access_type, ManualSourceAdapter)
    return adapter(dataset, *args, **kwargs)
