"""Official runtime manifest; runtime acceptance never alters B2 qualification."""

from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from pathlib import Path

from ..json_types import JSONValue, decode_json_object, is_document
from ..versions import VersionRegistry


class RuntimeFeature(StrEnum):
    VERSION_RECOGNIZED = "VERSION_RECOGNIZED"
    RUNTIME_AVAILABLE = "RUNTIME_AVAILABLE"
    SKELETON_LOAD_SUPPORTED = "SKELETON_LOAD_SUPPORTED"
    ANIMATION_EVALUATION_SUPPORTED = "ANIMATION_EVALUATION_SUPPORTED"
    RENDERING_SUPPORTED = "RENDERING_SUPPORTED"
    APPROVED_BINARY_ONLY = "APPROVED_BINARY_ONLY"
    BINARY_LOAD_SUPPORTED = "BINARY_LOAD_SUPPORTED"
    HEADLESS_CAPTURE_SUPPORTED = "HEADLESS_CAPTURE_SUPPORTED"
    EXTERNAL_VIEWER_ONLY = "EXTERNAL_VIEWER_ONLY"
    UNSUPPORTED = "UNSUPPORTED"


def _optional_identity(value: JSONValue, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid runtime {field}")
    return value


@dataclass(frozen=True)
class RuntimeCapability:
    family: str
    revision: str | None
    identity: str | None
    embedded: bool
    binary: bool
    source_commit: str | None
    capabilities: tuple[RuntimeFeature, ...]
    backend: str | None
    qualification: str

    def supports(self, export_version: str) -> bool:
        return self.embedded and VersionRegistry().family_for(export_version) == self.family

    def available(self, web_root: Path) -> bool:
        """Installed local bundle identity is distinct from implemented source support."""
        path = web_root / "runtime-manifest.json"
        if not self.embedded or not path.is_file() or not (web_root / "component.js").is_file():
            return False
        expected = files(__package__).joinpath("runtime_manifest.json").read_bytes()
        return path.read_bytes() == expected


class RuntimeRegistry:
    def __init__(self) -> None:
        document = decode_json_object(
            files(__package__).joinpath("runtime_manifest.json").read_text(), "Runtime manifest"
        )
        rows = document.get("runtimes")
        if document.get("schemaVersion") != 1 or not isinstance(rows, list):
            raise ValueError("Invalid runtime manifest")
        entries: list[RuntimeCapability] = []
        for row in rows:
            if not is_document(row):
                raise ValueError("Invalid runtime row")
            family, revision, identity = row.get("family"), row.get("revision"), row.get("identity")
            embedded, binary = row.get("embeddedImplemented"), row.get("binaryImplemented")
            commit, backend, qualification = (
                row.get("sourceCommit"),
                row.get("backend"),
                row.get("qualification"),
            )
            capabilities = row.get("capabilities")
            if (
                not isinstance(family, str)
                or not isinstance(embedded, bool)
                or not isinstance(binary, bool)
                or not isinstance(qualification, str)
                or not isinstance(capabilities, list)
            ):
                raise ValueError("Invalid runtime capability")
            revision = _optional_identity(revision, "revision")
            identity = _optional_identity(identity, "identity")
            commit = _optional_identity(commit, "sourceCommit")
            backend = _optional_identity(backend, "backend")
            if VersionRegistry().family_for(f"{family}.0") != family:
                raise ValueError("Invalid runtime family")
            if any(entry.family == family for entry in entries):
                raise ValueError("Duplicate runtime family")
            if embedded and not all((revision, identity, commit, backend)):
                raise ValueError("Embedded runtime requires a complete identity")
            if binary and not embedded:
                raise ValueError("Binary support requires an embedded runtime")
            names: list[RuntimeFeature] = []
            for capability in capabilities:
                if not isinstance(capability, str):
                    raise ValueError("Invalid capability name")
                feature = RuntimeFeature(capability)
                if feature in names:
                    raise ValueError("Duplicate runtime capability")
                names.append(feature)
            if (RuntimeFeature.BINARY_LOAD_SUPPORTED in names) != binary:
                raise ValueError("Binary capability contradicts implementation")
            if (RuntimeFeature.APPROVED_BINARY_ONLY in names) != binary:
                raise ValueError("Binary trust restriction contradicts implementation")
            if embedded and RuntimeFeature.UNSUPPORTED in names:
                raise ValueError("Embedded runtime cannot be unsupported")
            entries.append(
                RuntimeCapability(
                    family,
                    revision,
                    identity,
                    embedded,
                    binary,
                    commit,
                    tuple(names),
                    backend,
                    qualification,
                )
            )
        self._entries = tuple(entries)

    def entries(self) -> tuple[RuntimeCapability, ...]:
        return self._entries

    def select(self, export_version: str) -> RuntimeCapability:
        family = VersionRegistry().family_for(export_version)
        entry = next((r for r in self._entries if r.family == family), None)
        if entry is None:
            raise ValueError("UNSUPPORTED_SKELETON_VERSION")
        if not entry.embedded:
            raise ValueError("RUNTIME_NOT_INSTALLED")
        return entry
