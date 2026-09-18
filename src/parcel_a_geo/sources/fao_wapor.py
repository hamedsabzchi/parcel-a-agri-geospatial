"""WaPOR discovery adapter."""

from .earth_engine import EarthEngineSourceAdapter
from .manual import ManualSourceAdapter


class WaPORSourceAdapter(EarthEngineSourceAdapter):
    pass


class WaPORManualSourceAdapter(ManualSourceAdapter):
    pass
