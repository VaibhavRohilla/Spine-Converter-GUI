"""RC1 evidence authority. Graph reachability never confers qualification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .json_types import JSONDocument, JSONObject
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
    SLOTS = "slot_color_attachment"
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
    if any(bone.transform.mode not in {None, "normal"} for bone in semantic.bones):
        found.add(SourceFeature.UNKNOWN)
    animations = document.get("animations", {})
    if isinstance(animations, dict):
        for animation in animations.values():
            if isinstance(animation, dict) and set(animation) - {
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
            "translatex": SourceFeature.TRANSLATION,
            "translatey": SourceFeature.TRANSLATION,
            "scale": SourceFeature.SCALE,
            "scalex": SourceFeature.SCALE,
            "scaley": SourceFeature.SCALE,
            "shear": SourceFeature.SHEAR,
            "shearx": SourceFeature.SHEAR,
            "sheary": SourceFeature.SHEAR,
        }.get(owner)
        if timeline.category == "bones":
            found.add(feature or SourceFeature.UNKNOWN)
        elif timeline.category == "slots":
            found.add(SourceFeature.SLOTS)
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
class QualificationRecord:
    source_version: str
    target_version: str
    path: tuple[str, ...]
    supported_features: frozenset[SourceFeature] = frozenset()
    unsupported_features: frozenset[SourceFeature] = frozenset({SourceFeature.UNKNOWN})
    unverified_features: frozenset[SourceFeature] = frozenset(SourceFeature)
    fixtures: tuple[str, ...] = ()
    provenance: str = "No end-to-end evidence recorded"
    structural_evidence: tuple[str, ...] = ()
    semantic_evidence: tuple[str, ...] = ()
    numerical_evidence: tuple[str, ...] = ()
    runtime_verified: bool = False
    visually_verified: bool = False
    schema_version: int = 1

    @property
    def engineering_level(self) -> QualificationLevel:
        if self.semantic_evidence:
            return QualificationLevel.SEMANTIC
        if self.structural_evidence:
            return QualificationLevel.STRUCTURAL
        return QualificationLevel.NOT_QUALIFIED


# Fixed evidence inventory, deliberately independent of future graph additions.
_HIERARCHY_EVIDENCE_PATHS = frozenset(
    ("3.8.99", target)
    for target in (
        "3.5.51",
        "3.6.53",
        "3.7.94",
        "4.0.31",
        "4.1.56",
        "4.2.43",
        "4.3.13",
    )
)


class ConversionQualificationRegistry:
    """Exact directed paths, with no inheritance from constituent edges."""

    def records(self) -> tuple[QualificationRecord, ...]:
        """Inventory every deterministic advertised candidate, including unqualified paths."""
        from .planner import ConversionPlanner
        from .registry import SUPPORTED_PATCH_VERSIONS

        planner = ConversionPlanner()
        return tuple(
            self.record(path)
            for source in sorted(SUPPORTED_PATCH_VERSIONS)
            for target in sorted(SUPPORTED_PATCH_VERSIONS)
            if source != target
            for path in planner.candidate_routes(source, target)
        )

    def record(self, path: tuple[str, ...]) -> QualificationRecord:
        if not path:
            raise ValueError("Qualification record requires a complete directed path")
        supported = (
            frozenset({SourceFeature.HIERARCHY})
            if path in _HIERARCHY_EVIDENCE_PATHS and (path[0], path[1]) in EXACT_ROUTE_PAIRS
            else frozenset[SourceFeature]()
        )
        authentic = path == ("3.8.75", "4.2.43")
        return QualificationRecord(
            path[0],
            path[-1],
            path,
            supported,
            unverified_features=frozenset(SourceFeature) - supported - {SourceFeature.UNKNOWN},
            fixtures=("tests/fixtures/b2_semantic/spine_3_8_99.json",)
            if supported
            else ("tests/fixtures/spine38/golden_ingot.json",)
            if authentic
            else (),
            provenance="Schema-derived synthetic fixture; not an editor export"
            if supported
            else "Authentic 3.8.75 export; known export risk, structural bundle evidence only"
            if authentic
            else "No end-to-end semantic qualification",
            structural_evidence=("tests/test_b2_semantic_qualification.py",)
            if supported
            else ("docs/B2_REPORT.md: Targeted fidelity recovery",)
            if authentic
            else (),
            numerical_evidence=("Exact serialized bone setup values compared at endpoints",)
            if supported
            else (),
            semantic_evidence=(
                "test_38_99_feature_fixture_direct_route_semantic_evaluation: bones equality",
            )
            if supported
            else (),
        )


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
            "runtime_verified": False,
            "visually_verified": False,
        }


class QualificationService:
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
        valid = (
            bool(migration_path)
            and migration_path[0] == source_version
            and (migration_path[-1] == target_version)
            and all(edge in EXACT_ROUTE_PAIRS for edge in zip(migration_path, migration_path[1:]))
        )
        record = ConversionQualificationRegistry().record(migration_path) if valid else None
        supported = record.supported_features if record else frozenset()
        missing = source_features - supported
        available = (
            QualificationLevel.SEMANTIC
            if (record and record.semantic_evidence and not missing)
            else QualificationLevel.STRUCTURAL
            if record and record.structural_evidence
            else QualificationLevel.NOT_QUALIFIED
        )
        qualified = valid and available == required_level
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
                (
                    "Experimental structural output; semantic qualification is not asserted",
                ),
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
        )
