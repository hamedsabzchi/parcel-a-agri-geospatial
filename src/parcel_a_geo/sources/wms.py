"""WMS capabilities and minimal image adapter."""

from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image

from .base import BaseSourceAdapter


class WmsSourceAdapter(BaseSourceAdapter):
    def get_metadata(self) -> dict[str, Any]:
        endpoint = str(self.dataset.get("access_endpoint", "UNKNOWN"))
        if endpoint == "UNKNOWN":
            raise ValueError("No documented WMS endpoint is configured")
        payload = self.client.request(
            "GET",
            endpoint,
            params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"},
        ).text
        layers = re.findall(r"<Name>([^<]+)</Name>", payload)
        self._layers = layers
        return {"catalogue_verified": True, "bands": layers[:100]}

    def get_minimal_sample(self, aoi: Any) -> bytes:
        endpoint = str(self.dataset["access_endpoint"])
        layer = str(self.dataset.get("collection_id", "UNKNOWN"))
        if layer == "UNKNOWN":
            raise ValueError("No WMS layer is configured")
        minx, miny, maxx, maxy = aoi.bounds
        params = {
            "service": "WMS",
            "request": "GetMap",
            "version": "1.1.1",
            "layers": layer,
            "styles": "",
            "srs": "EPSG:4326",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "width": 64,
            "height": 64,
            "format": "image/png",
            "transparent": "true",
        }
        return self.client.request("GET", endpoint, params=params, use_cache=False).content

    def validate_sample(self, sample: Any) -> tuple[str, str]:
        try:
            image = Image.open(io.BytesIO(sample)).convert("RGBA")
        except Exception as error:
            return "VERIFICATION_FAILED", f"WMS response is not a readable image: {error}"
        pixels = list(image.getdata())
        valid = [pixel for pixel in pixels if pixel[3] > 0]
        if not valid:
            return "NO_VALID_DATA", "WMS image is fully transparent"
        if len(set(valid)) == 1:
            return "UNKNOWN", "WMS image contains one repeated value; NoData cannot be excluded"
        return "VALID_DATA", "WMS returned a non-empty AOI image with varying pixel values"

    def get_access_information(self) -> str:
        return "AUTOMATED_OPEN"
