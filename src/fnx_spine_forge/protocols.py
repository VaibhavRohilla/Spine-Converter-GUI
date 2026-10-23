from typing import Protocol

from .models import AssetManifest
from .parsers import AtlasInfo


class Inspector(Protocol):
    def inspect(self, origin: str) -> AssetManifest: ...


class AtlasParser(Protocol):
    def parse(self, payload: bytes) -> AtlasInfo: ...
