"""RC1 evidence authority. Graph reachability never confers qualification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from types import MappingProxyType

from ..json_types import JSONDocument, JSONObject, JSONValue, decode_json_object, is_document
from .document import require_array, require_object, require_text
from .registry import EXACT_ROUTE_PAIRS
from .semantic import SemanticSkeleton


class QualificationLevel(StrEnum):
    NOT_QUALIFIED = "not_qualified"
    STRUCTURAL = "structural_only"
    SEMANTIC = "semantic_qualified"
    RUNTIME = "runtime_verified"
    VISUAL = "visually_verified"


class QualificationCode(StrEnum):
    PATH = "QUALIFICATION_PATH_INVALID"
    EVIDENCE = "QUALIFICATION_EVIDENCE_MISSING"
    FEATURES = "QUALIFICATION_FEATURES_UNVERIFIED"
    EXPERIMENTAL = "QUALIFICATION_EXPERIMENTAL_OUTPUT"


class SourceFeature(StrEnum):
    HIERARCHY = "hierarchy_setup_transforms"
    BONE_INHERITANCE = "bone_inheritance"
    BONE_EXTENSIONS = "bone_length_skin_editor_metadata"
    ATTACHMENTS = "skins_attachments"
    MESH = "mesh_geometry"
    AUXILIARY_ATTACHMENTS = "auxiliary_attachment_geometry"
    WEIGHTED = "weighted_mesh"
    LINKED = "linked_mesh"
    DEFORM = "deform"
    ROTATION = "rotation"
    TRANSLATION = "translation"
    SCALE = "scale"
    SHEAR = "shear"
    SEPARATE_AXIS = "separate_axis_bone_timelines"
    SLOTS = "slot_color_attachment"
    SLOT_ATTACHMENT_TIMELINE = "slot_attachment_timelines"
    OTHER_SLOT_COLOR_TIMELINE = "other_slot_color_timelines"
    SLOT_BEZIER = "slot_bezier_channels"
    CONSTRAINTS = "constraints"
    EVENTS = "events_draw_order"
    BEZIER = "bezier_channels"
    ATLAS = "atlas_geometry"
    UNKNOWN = "unknown_semantics"


def inspect_features(
    semantic: SemanticSkeleton, document: JSONDocument
) -> frozenset[SourceFeature]:
    """Classify validated records; retain unknown raw extensions as blocking evidence."""
    found = {SourceFeature.HIERARCHY}
    if any(
        bone.transform.mode is not None
        and (semantic.version != "4.2.22" or bone.transform.mode.value != "normal")
        for bone in semantic.bones
    ):
        found.add(SourceFeature.BONE_INHERITANCE)
    if semantic.version == "4.2.22":
        has_bone_extensions = any(
            (bone.length is not None and bone.length != 0)
            or bone.skin is True
            or bone.skin_required is True
            for bone in semantic.bones
        )
    else:
        has_bone_extensions = any(
            bone.length is not None
            or bone.skin is not None
            or bone.skin_required is not None
            or bone.editor_metadata
            for bone in semantic.bones
        )
    if has_bone_extensions:
        found.add(SourceFeature.BONE_EXTENSIONS)
    metadata = document.get("skeleton", {})
    if isinstance(metadata, Mapping) and set(metadata) - {
        "spine",
        "hash",
        "x",
        "y",
        "width",
        "height",
        "referenceScale",
        "fps",
        "images",
        "audio",
    }:
        found.add(SourceFeature.UNKNOWN)
    animations = document.get("animations", {})
    if is_document(animations):
        for animation in animations.values():
            if is_document(animation) and set(animation) - {
                "bones",
                "slots",
                "ik",
                "path",
                "transform",
                "physics",
                "attachments",
                "deform",
                "drawOrder",
                "draworder",
                "events",
            }:
                found.add(SourceFeature.UNKNOWN)
    if semantic.skins or semantic.attachments:
        found.add(SourceFeature.ATTACHMENTS)
    for attachment in semantic.attachments:
        if attachment.weighted:
            found.add(SourceFeature.WEIGHTED)
        if attachment.kind == "linkedmesh":
            found.add(SourceFeature.LINKED)
        if attachment.kind == "mesh":
            found.add(SourceFeature.MESH)
        if attachment.kind in {"boundingbox", "path", "clipping", "point"}:
            found.add(SourceFeature.AUXILIARY_ATTACHMENTS)
    if semantic.slots:
        found.add(SourceFeature.SLOTS)
    if semantic.constraints:
        found.add(SourceFeature.CONSTRAINTS)
    if document.get("events"):
        found.add(SourceFeature.EVENTS)
    for timeline in semantic.timelines:
        owner = timeline.owner.split("/")[-1]
        feature = {
            "rotate": SourceFeature.ROTATION,
            "translate": SourceFeature.TRANSLATION,
            "scale": SourceFeature.SCALE,
            "shear": SourceFeature.SHEAR,
        }.get(owner)
        if timeline.category == "bones":
            found.add(
                SourceFeature.SEPARATE_AXIS
                if owner in {"translatex", "translatey", "scalex", "scaley", "shearx", "sheary"}
                else feature or SourceFeature.UNKNOWN
            )
        elif timeline.category == "slots":
            found.add(SourceFeature.SLOTS)
            if owner == "attachment":
                found.add(SourceFeature.SLOT_ATTACHMENT_TIMELINE)
            elif owner != "rgba":
                found.add(SourceFeature.OTHER_SLOT_COLOR_TIMELINE)
            if timeline.curves:
                found.add(SourceFeature.SLOT_BEZIER)
        elif timeline.category in {"events", "draworder", "drawOrder"}:
            found.add(SourceFeature.EVENTS)
        elif timeline.category in {"deform", "attachments"}:
            found.add(SourceFeature.DEFORM)
        else:
            found.add(SourceFeature.CONSTRAINTS)
        if timeline.curves:
            found.add(SourceFeature.BEZIER)
    if set(document) - {
        "skeleton",
        "bones",
        "slots",
        "skins",
        "animations",
        "events",
        "ik",
        "transform",
        "path",
        "physics",
        "constraints",
    }:
        found.add(SourceFeature.UNKNOWN)
    return frozenset(found)


@dataclass(frozen=True)
class FixtureEvidence:
    identity: str
    sha256: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.identity or not self.provenance or len(self.sha256) != 64:
            raise ValueError("Fixture evidence requires identity, provenance and SHA-256")
        if any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("Fixture evidence SHA-256 must be lowercase hexadecimal")


@dataclass(frozen=True)
class QualificationRecord:
    source_version: str
    target_version: str
    path: tuple[str, ...]
    supported_features: frozenset[SourceFeature] = frozenset()
    unsupported_features: frozenset[SourceFeature] = frozenset({SourceFeature.UNKNOWN})
    unverified_features: frozenset[SourceFeature] = frozenset(SourceFeature) - {
        SourceFeature.UNKNOWN
    }
    fixtures: tuple[FixtureEvidence, ...] = ()
    provenance: str = "No end-to-end evidence recorded"
    structural_evidence: tuple[str, ...] = ()
    semantic_evidence: tuple[str, ...] = ()
    numerical_evidence: tuple[str, ...] = ()
    runtime_verified: bool = False
    visually_verified: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported qualification contract version")
        identity_profile = (
            self.source_version == self.target_version
            and self.path == (self.source_version,)
        )
        if not identity_profile and (
            len(self.path) < 2
            or len(set(self.path)) != len(self.path)
            or self.path[0] != self.source_version
            or self.path[-1] != self.target_version
        ):
            raise ValueError("Qualification endpoints must match the complete migration path")
        if not identity_profile and any(
            edge not in EXACT_ROUTE_PAIRS for edge in zip(self.path, self.path[1:])
        ):
            raise ValueError("Qualification references an unregistered migration edge")
        if (
            self.supported_features & self.unsupported_features
            or self.supported_features & self.unverified_features
            or self.unsupported_features & self.unverified_features
        ):
            raise ValueError("Qualification feature sets must be disjoint")
        if (
            self.supported_features | self.unsupported_features | self.unverified_features
            != frozenset(SourceFeature)
        ):
            raise ValueError("Qualification must account for every semantic feature category")
        if SourceFeature.UNKNOWN in self.supported_features:
            raise ValueError("Unknown semantics cannot be qualified")
        if self.supported_features and not (
            self.fixtures and self.structural_evidence and self.semantic_evidence
        ):
            raise ValueError("Supported features require fixture, structural and semantic evidence")
        if SourceFeature.HIERARCHY in self.supported_features and not self.numerical_evidence:
            raise ValueError("Setup transform qualification requires numerical evidence")
        if self.semantic_evidence and not self.supported_features:
            raise ValueError("Semantic evidence must identify a qualified feature subset")
        if len({fixture.identity for fixture in self.fixtures}) != len(self.fixtures):
            raise ValueError("Duplicate fixture evidence identity")
        if self.runtime_verified or self.visually_verified:
            raise ValueError(
                "Runtime and visual certifications require an external evidence contract"
            )

    @property
    def engineering_level(self) -> QualificationLevel:
        if self.semantic_evidence:
            return QualificationLevel.SEMANTIC
        if self.structural_evidence:
            return QualificationLevel.STRUCTURAL
        return QualificationLevel.NOT_QUALIFIED


def _strings(value: JSONValue, context: str) -> tuple[str, ...]:
    # The object boundary is admitted once, then all nested access remains typed.
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{context} must be an array")
    # Configuration callers supply JSON arrays; a separate checked object handles the root.
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{context} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def load_qualification_records(payload: bytes) -> tuple[QualificationRecord, ...]:
    document = decode_json_object(payload, "Qualification evidence")
    if (
        set(document) != {"schema_version", "records"}
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("Unsupported qualification evidence schema")
    records: list[QualificationRecord] = []
    seen: set[tuple[str, ...]] = set()
    expected = {
        "source_version",
        "target_version",
        "path",
        "supported_features",
        "unsupported_features",
        "unverified_features",
        "fixtures",
        "structural_evidence",
        "semantic_evidence",
        "numerical_evidence",
        "runtime_verified",
        "visually_verified",
    }
    for index, value in enumerate(require_array(document["records"], "qualification records")):
        row = require_object(value, f"qualification record {index}")
        if set(row) != expected:
            raise ValueError(f"Qualification record {index} has missing or unknown fields")
        path = _strings(row["path"], "qualification path")
        if path in seen:
            raise ValueError("Duplicate qualification path")
        seen.add(path)
        fixtures: list[FixtureEvidence] = []
        for fixture_value in require_array(row["fixtures"], "fixture evidence"):
            fixture = require_object(fixture_value, "fixture evidence")
            if set(fixture) != {"identity", "sha256", "provenance"}:
                raise ValueError("Invalid fixture evidence fields")
            fixtures.append(
                FixtureEvidence(
                    require_text(fixture["identity"], "fixture identity"),
                    require_text(fixture["sha256"], "fixture SHA-256"),
                    require_text(fixture["provenance"], "fixture provenance"),
                )
            )
        runtime, visual = row["runtime_verified"], row["visually_verified"]
        if not isinstance(runtime, bool) or not isinstance(visual, bool):
            raise ValueError("Verification flags must be booleans")
        records.append(
            QualificationRecord(
                require_text(row["source_version"], "source version"),
                require_text(row["target_version"], "target version"),
                path,
                frozenset(
                    SourceFeature(v)
                    for v in _strings(row["supported_features"], "supported features")
                ),
                frozenset(
                    SourceFeature(v)
                    for v in _strings(row["unsupported_features"], "unsupported features")
                ),
                frozenset(
                    SourceFeature(v)
                    for v in _strings(row["unverified_features"], "unverified features")
                ),
                tuple(fixtures),
                "; ".join(f.provenance for f in fixtures) or "No fixture evidence",
                _strings(row["structural_evidence"], "structural evidence"),
                _strings(row["semantic_evidence"], "semantic evidence"),
                _strings(row["numerical_evidence"], "numerical evidence"),
                runtime,
                visual,
            )
        )
    return tuple(records)


_PACKAGED_RECORDS = load_qualification_records(
    files("fnx_spine_forge.conversion").joinpath("qualification_evidence.json").read_bytes()
)


class ConversionQualificationRegistry:
    """Exact directed paths, with no inheritance from constituent edges."""

    def __init__(self, records: tuple[QualificationRecord, ...] | None = None) -> None:
        admitted = _PACKAGED_RECORDS if records is None else records
        self._evidence: Mapping[tuple[str, ...], QualificationRecord] = MappingProxyType(
            {r.path: r for r in admitted}
        )
        if len(self._evidence) != len(admitted):
            raise ValueError("Duplicate qualification path")

    def records(self) -> tuple[QualificationRecord, ...]:
        """Inventory every deterministic advertised candidate, including unqualified paths."""
        from .planner import ConversionPlanner
        from .registry import SUPPORTED_PATCH_VERSIONS

        planner = ConversionPlanner()
        migration_records = tuple(
            self.record(path)
            for source in sorted(SUPPORTED_PATCH_VERSIONS)
            for target in sorted(SUPPORTED_PATCH_VERSIONS)
            if source != target
            for path in planner.candidate_routes(source, target)
        )
        identity_profiles = tuple(
            self._evidence[path]
            for path in sorted(self._evidence)
            if len(path) == 1 and path[0] in SUPPORTED_PATCH_VERSIONS
        )
        return (*migration_records, *identity_profiles)

    def record(self, path: tuple[str, ...]) -> QualificationRecord:
        if not path:
            raise ValueError("Qualification record requires a complete directed path")
        record = self._evidence.get(path)
        return record if record is not None else QualificationRecord(path[0], path[-1], path)


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    required_level: QualificationLevel
    available_level: QualificationLevel
    qualified_features: tuple[SourceFeature, ...]
    unqualified_features: tuple[SourceFeature, ...]
    missing_evidence: tuple[str, ...]
    diagnostic_codes: tuple[QualificationCode, ...]
    selected_path: tuple[str, ...]
    runtime_verified: bool = False
    visually_verified: bool = False

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return self.missing_evidence

    def to_json(self) -> JSONObject:
        return {
            "qualified": self.qualified,
            "required_level": self.required_level.value,
            "available_level": self.available_level.value,
            "qualified_features": tuple(x.value for x in self.qualified_features),
            "unqualified_features": tuple(x.value for x in self.unqualified_features),
            "missing_evidence": self.missing_evidence,
            "diagnostics": self.diagnostics,
            "diagnostic_codes": tuple(x.value for x in self.diagnostic_codes),
            "selected_path": self.selected_path,
            "schema_version": 1,
            "runtime_verified": self.runtime_verified,
            "visually_verified": self.visually_verified,
        }


class QualificationService:
    def __init__(self, registry: ConversionQualificationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else ConversionQualificationRegistry()

    def evaluate(
        self,
        source_version: str,
        target_version: str,
        migration_path: tuple[str, ...],
        source_features: frozenset[SourceFeature],
        required_level: QualificationLevel = QualificationLevel.SEMANTIC,
        *,
        experimental_structural: bool = False,
    ) -> QualificationResult:
        identity_profile = source_version == target_version and migration_path in {
            (source_version,),
            (source_version, source_version),
        }
        valid = bool(source_features) and (identity_profile or (
            len(migration_path) >= 2
            and bool(source_features)
            and len(set(migration_path)) == len(migration_path)
            and migration_path[0] == source_version
            and migration_path[-1] == target_version
            and all(edge in EXACT_ROUTE_PAIRS for edge in zip(migration_path, migration_path[1:]))
        ))
        evidence_path = (source_version,) if identity_profile else migration_path
        record = self.registry.record(evidence_path) if valid else None
        supported = record.supported_features if record else frozenset()
        missing = source_features - supported
        available = (
            QualificationLevel.SEMANTIC
            if (record and record.semantic_evidence and not missing)
            else QualificationLevel.STRUCTURAL
            if record and record.structural_evidence
            else QualificationLevel.NOT_QUALIFIED
        )
        qualified = valid and available == required_level and not missing
        codes = (
            ()
            if qualified
            else (
                QualificationCode.PATH
                if not valid
                else QualificationCode.FEATURES
                if missing
                else QualificationCode.EVIDENCE,
            )
        )
        if experimental_structural:
            return QualificationResult(
                False,
                required_level,
                available,
                tuple(sorted(source_features & supported)),
                tuple(sorted(missing)),
                ("Experimental structural output; semantic qualification is not asserted",),
                (QualificationCode.EXPERIMENTAL,),
                migration_path,
            )
        return QualificationResult(
            qualified,
            required_level,
            available,
            tuple(sorted(source_features & supported)),
            tuple(sorted(missing)),
            ()
            if qualified
            else (
                "End-to-end "
                + required_level.value
                + " evidence missing for path "
                + " -> ".join(migration_path)
                + "; features: "
                + (", ".join(sorted(missing)) or "requested verification level")
                + ". Supply evidence or explicitly opt into experimental structural output.",
            ),
            codes,
            migration_path,
            runtime_verified=record.runtime_verified if record else False,
            visually_verified=record.visually_verified if record else False,
        )
