"""CropSuit discovery adapter."""

from typing import Any

from .base import BaseSourceAdapter
from .wms import WmsSourceAdapter


class CropSuitSourceAdapter(WmsSourceAdapter):
    def run(self) -> dict[str, Any]:
        if self.dataset.get("access_endpoint") == "UNKNOWN":
            try:
                self.metadata = BaseSourceAdapter.get_metadata(self)
            except Exception as error:
                self.failure_reason = f"{type(error).__name__}: {error}"
            self.coverage = self.check_aoi_intersection(self.aoi)
            self.access_status = "MANUAL_INSPECTION_REQUIRED"
            self.validation_note = "No documented service endpoint is configured; inspect the official catalogue manually"
            return self.return_inventory_record()
        return super().run()
