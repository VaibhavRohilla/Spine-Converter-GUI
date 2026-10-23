# FNX Spine Forge 1.0 — Revamp Plan and Definition of Done

Date: 2026-10-23. Status: ARCHITECTURE BASELINE / R0 FOUNDATION.

## Goal

A Python-first, deterministic Spine export converter with four separate workflows:
1. Viewer Bundle Converter (ZIP/folder discovery -> dependencies -> versions -> full conversion -> ZIP)
2. Atlas Converter (isolated atlas read/convert/validate)
3. Skeleton Converter (isolated JSON and later binary `.skel` convert/validate)
4. Spine Viewer (load with version-matched runtime, inspect skins, animations, events, playback)

One shared conversion engine. The UI is an adapter; it owns no asset schemas.

## Architecture and data contracts

```text
UI (PySide6)       CLI          Python SDK
       \            |              /
            application/usecases
                      |
        inventory + dependency graph
                      |
   version registry / feature compatibility analyzer
                      |
        readers -> semantic IR -> writers
                      |
        atlas/texture + package output
                      |
    independent parse/playback/visual QA
```

Input models: FileAsset, SkeletonAsset, AtlasAsset, TexturePage, BundleGraph,
Diagnostics, SourceVersion, TargetVersion, ConversionPolicy, ConversionPlan.
Output models: ConversionArtifact, ConversionManifest, FidelityReport, QAStatus.

IMPORTANT: IR must model actual semantic constraints, not only rename JSON fields.
Both reader and writer are version-specific; backwards conversions require explicit
loss detection. No global `skeleton.spine = target_version` shortcut.

## Release milestones (one at a time)

### R0 — Foundation & inventory (started in this artifact)
- Source admission: ZIP/folder + secure path and decompression limits
- Skeleton JSON version detection, initial atlas pages, texture matching
- Dependency diagnostics and an auditable version migration registry
- CLI and repeatable unit tests
- Exit: consistent manifests and understandable fail-fast errors on fixtures
- Remaining R0: full grammar parser, image integrity/decode, feature inventory,
  complex multi-skeleton associations, structured schemas

### R1 — Format specification + feature matrix
- Fixture set per minor version: 3.5, 3.6, 3.7, 3.8, 4.0, 4.1, 4.2, 4.3
- Identify changes to bones/slots/skins, attachments, constraints, animation
  timeline formats, Bézier curves, metadata, atlas schema
- Define `supported`, `convertible-with-loss`, `blocked`, `untested`
- Exit: schema fixtures and a version compatibility test table

### R2 — Custom conversion kernel
- Full JSON version-family readers -> typed IR -> version-family writers
- Pluggable feature transcoders, timeline/curve semantics, attachment refs
- Validate invariants: reference topology, counts, numeric finiteness, ordering
- Build migration edges in ascending version order; register only tested edges
- Exit: actual converted outputs parse as target versions, tested on fixtures
- First production anchor: port/retest the known v0.3.1 3.8 -> 4.2 path

### R3 — Full bundle and standalone conversion orchestration
- Select folder/ZIP; enumerate multiple skeletons/atlases/textures; repair only
  explicitly accepted/recorded problems; target version selection
- Atlas-only / skeleton-only / complete-bundle use cases share same core
- Preserve textures byte-for-byte unless user selects an explicit texture operation
- Atomic output, path preservation, deterministic ZIP, manifest with hashes
- Exit: complete viewer-ready package emitted, no missing dependency tolerated

### R4 — Runtime verification + viewer engine
- Runtime adapters for exact supported Spine major/minor families
- Setup-pose load, every animation/skin, events, mesh/deform/constraints checks
- Deterministic pose samples and image comparisons with documented tolerances
- Explicit status: `SCHEMA_VALID`, `RUNTIME_LOADED`, `VISUALLY_VERIFIED`, or `BLOCKED`
- Never infer playback quality from JSON parsing or Bézier math alone
- Exit: verifier correctly identifies intentionally broken conversions

### R5 — Desktop user interface
- PySide6: Bundle Converter / Atlas Converter / Skeleton Converter / Viewer
- Source chooser, drag/drop, asset table, matching overrides, version selector
- Diagnostics before Convert, background worker execution, logs, cancel support
- Viewer controls: animation, skin, speed, looping, scrub, transparent/checkerboard
- Embed or sidecar player based on licensed version-matched renderer
- Exit: GUI uses same API as CLI; no duplicated conversion logic

### R6 — Hardening and release
- Test old->new, new->old, no-op, malformed input, multiple atlas pages,
  multi-skeleton bundles, huge inputs, failure rollback, deterministic archives
- Windows/Linux/macOS packaged build, legal review, reproducible artifacts
- Exit: all supported paths verified end to end, unsupported paths block clearly

## Deliberately NOT promised in R0

- All historical versions convertible, especially without source feature loss
- Native `.skel` conversion, export-from-editor equivalence, or any runtime playback
- Automatic compatibility guarantees from a rewritten version string

## Quality gate decision table

| Condition | Convert allowed? | Export status |
|-----------|------------------|---------------|
| Missing skeleton/required texture | No | BLOCKED |
| Ambiguous file relationship | No until resolved | BLOCKED |
| Unsupported source/target feature | No by default | BLOCKED |
| Explicit approved lossy fallback | Only when implemented | LOSSY / NOT CERTIFIED |
| Schema checks pass | May export to QA | SCHEMA_VALID |
| Real target runtime loads all required data | Yes | RUNTIME_LOADED |
| Recorded pose/render comparisons pass | Yes | VISUALLY_VERIFIED |

## MVP success scenario

Input: real 3.8.75 Spine ZIP with JSON, atlas, multiple PNG pages. Scanner
recognizes required files, identifies all missing/ambiguous dependencies, and
previews animations/skins. Select 4.2.43. Converter transforms skeleton and atlas
using explicit schemas. Viewer loads all animations through 4.2 runtime. Outputs
include verified full ZIP, per-file hashes, compatibility warnings, and QA report.

This is a target milestone, not a current claim.

## Decisions

- Python 3.11+ modular package, Qt/PySide6 for eventual desktop UI.
- Version registry rather than one giant switch statement.
- Separate JSON, atlas, and binary codecs.
- Core-independent viewer runtime bridge (may be JS/WebGL or native adapter).
- Independent runtime validation gate and visible diagnostic codes.
- No third-party converter code imported until terms and provenance reviewed.

## Official reference docs

- https://esotericsoftware.com/spine-json-format
- https://esotericsoftware.com/spine-versioning
- https://esotericsoftware.com/spine-changelog
- https://esotericsoftware.com/spine-player
- https://esotericsoftware.com/spine-runtimes-license
