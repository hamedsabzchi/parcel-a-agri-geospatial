"""Adapters for documented manual portals and downloads."""

from __future__ import annotations

from typing import Any

from .base import BaseSourceAdapter


class ManualSourceAdapter(BaseSourceAdapter):
    def get_minimal_sample(self, aoi: Any) -> None:
        return None

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        return "UNKNOWN", "Manual spatial or valid-data verification is required"

    def get_access_information(self) -> str:
        if self.dataset.get("access_type") == "DIRECT_DOWNLOAD":
            return "MANUAL_DOWNLOAD_AVAILABLE"
        return "MANUAL_INSPECTION_REQUIRED"
