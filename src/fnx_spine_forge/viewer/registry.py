"""Official runtime manifest; runtime acceptance never alters B2 qualification."""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from ..json_types import decode_json_object, is_document
from ..versions import VersionRegistry


@dataclass(frozen=True)
class RuntimeCapability:
    family: str
    revision: str | None
    identity: str | None
    embedded: bool
    binary: bool
    source_commit: str | None
    capabilities: tuple[str, ...]
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
            if any(
                value is not None and not isinstance(value, str)
                for value in (revision, identity, commit, backend)
            ):
                raise ValueError("Invalid runtime identity")
            # Explicit narrowing retains the strong source type gate.
            if not (revision is None or isinstance(revision, str)):
                raise ValueError("Invalid revision")
            if not (identity is None or isinstance(identity, str)):
                raise ValueError("Invalid identity")
            if not (commit is None or isinstance(commit, str)):
                raise ValueError("Invalid commit")
            if not (backend is None or isinstance(backend, str)):
                raise ValueError("Invalid backend")
            names: list[str] = []
            for capability in capabilities:
                if not isinstance(capability, str):
                    raise ValueError("Invalid capability name")
                names.append(capability)
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
