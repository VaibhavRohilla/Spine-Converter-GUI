# FNX Spine Forge B2 conversion report

## Decision

**B2 OPEN / BLOCKED.** The exact Spine 3.8.75 to 4.2.43 skeleton and atlas path is structurally verified, numerically checked, dependency checked, and loaded by the exact official Spine 4.2.43 TypeScript runtime for the available real fixture. The planned migration families and broader source/target asset qualification remain incomplete. No freeze is claimed.

## A. Implemented conversion architecture

- `conversion/skeleton.py` provides the independent Python `SkeletonConverter`, source-version detection, route selection, semantic transformation, target reinspection, conversion metrics, and structured diagnostics/provenance.
- `conversion/migrate_38_42.py` performs the exact 3.8.75 to 4.2.43 JSON migration. It converts bone transform modes, slot color timelines, rotation values, constraint mix fields/channels, draw-order naming, deform ownership/timeline nesting, linked-mesh deform inheritance, and normalized to absolute Bézier controls. It validates references, attachment geometry, constraints, deform ranges, and target schema. Unknown top-level and timeline groups reject conversion.
- `conversion/atlas.py` exposes the standalone atlas API and converts the exact 3.8.75 to 4.2.43 atlas encoding. It reparses and compares pages, region ordering/indexing, rotation, packed bounds, trim offsets, and original dimensions. It does not alter texture data.
- `conversion/planner.py` registers executable exact-version routes only. The only cross-version route is `3.8.75 -> 4.2.43`.
- `conversion/runtime.py` and packaged `runtime_smoke.mjs` run the headless exact-version official TypeScript runtime smoke when the caller supplies `@esotericsoftware/spine-core` 4.2.43. Runtime parsing, animation-state evaluation, and visual equivalence are reported separately.
- `cli.py` retains standalone skeleton and atlas conversion and adds `runtime-smoke`. Spine 3.8.75 conversion requires explicit `--allow-known-source-export-risk`. Writes use the existing atomic writer.

The schema mappings were checked against the official [Spine JSON export format](https://esotericsoftware.com/spine-json-format) and the official Spine 3.8 and 4.2 TypeScript readers cited in the previous report. 4.2 curve values are channel-specific absolute control points; migration maps normalized source controls using the adjacent keyframes and verifies curve values numerically.

## B. Supported conversion routes

| Exact source | Exact target | Qualification |
|---|---|---|
| Spine 3.8.75 JSON | Spine 4.2.43 JSON | Executable; structural validation, sampled Bézier equivalence, real-fixture runtime load and animation-state evaluation |
| Spine 3.8.75 atlas | Spine 4.2.43 atlas | Executable with caller-supplied exact source version; semantic atlas reparse and real bundle dependency check |

The implemented route covers skeleton metadata, hierarchy, bones and slots, array-form skins, setup attachment references, events, draw order, region/mesh/weighted/linked-mesh/clipping/bounding-box/path/point attachments, supported constraints, and the implemented rotation, translation, scale, shear, attachment, color/two-color, deform, draw-order, event, IK, transform-constraint, and path-constraint timelines. Unsupported or malformed features reject without output. Synthetic fixtures exercise feature families not present in the reference asset.

There are no registered migration routes for 3.5, 3.6, 3.7, 4.0, 4.1, or 4.3. Other patch versions do not inherit qualification. Recognizing a version family or same-version serialization does not constitute cross-version migration support. No composed route is registered.

## C. Spine 3.8.75 source export risk

The official maintainers state that Spine 3.8.75 exports contain known issues, that official 3.8 runtimes reject that version, and recommend exporting from 3.8.99 when possible ([issue 2428](https://github.com/EsotericSoftware/spine-runtimes/issues/2428)). The notice does not identify specific affected construct categories, so the converter records those as unspecified rather than guessing.

The converter detects exact source version `3.8.75`. Default policy rejects with `SOURCE_EXPORT_KNOWN_BUG`. An explicit `SourceRiskPolicy.ALLOW_WITH_DIAGNOSTIC` or CLI `--allow-known-source-export-risk` permits a controlled migration attempt and adds provenance containing the unchanged declared source version, recommendation to re-export from 3.8.99, and `source_fidelity: unverified_without_trusted_baseline`. It does not relabel source metadata to bypass a runtime restriction. No authentic 3.8.99 fixture is currently available.

## D. Real asset and runtime results

Available real fixture: `tests/fixtures/spine38/golden_ingot.json`, `.atlas`, and `.png`.

- Exact input `3.8.75`; output `4.2.43`.
- Skeleton: 5 bones, 8 slots, 1 skin, 8 region attachments, 2 animations.
- Timeline/keyframe totals: 5 timeline instances and 25 keyframes. Animations: `idle`, `winning`.
- Curves: 42 Bézier channel segments evaluated at 257 shared positions each; maximum absolute deviation `2.731148640577885e-14`.
- Atlas: 1 page, 6 regions. Reparse retained region geometry, offsets, rotation, indices, and page declarations.
- Complete source and converted folders were reinspected through B1. Both manifests were `ok`; skeleton attachment paths matched; output atlas and page resolved; no missing or ambiguous texture, atlas, or region dependency was reported. The texture PNG bytes were preserved unchanged.
- Repeated conversion was deterministic and source JSON remained unchanged.

Official target runtime smoke executed with `@esotericsoftware/spine-core@4.2.43` from the official Esoteric Software package. It parsed the converted skeleton and atlas, read the referenced page texture, resolved all atlas-backed attachments while loading, instantiated the skeleton, applied setup pose, and evaluated both animations at 4 representative timestamps each. Result: parsing passed, animation-state evaluation passed, 8 samples, no runtime exception or non-finite world transform. This is runtime load/evaluation evidence for this fixture only. The headless core does not render texture pixels; visual equivalence is **not assessed**. The runtime package is an optional caller-supplied dependency and remains subject to the Spine runtime license.

`merged_multi.json` is a separate 4.2.43 asset, not an animation-equivalence counterpart to `golden_ingot.json`; it was not used as a paired comparison. No 4.3 or other historical fixture is available in the repository.

## E. Animation and atlas integrity

Bézier conversion decodes the source controls, emits target channel-specific controls, evaluates both representations at 257 identical normalized time positions per segment, and reports the maximum deviation. Real-fixture maximum error is `2.731148640577885e-14`; synthetic tests cover negative value deltas, channel defaults, and deform curves. Timeline categories and keyframe counts are reported. Unknown timeline groups block conversion.

The atlas migration handles page declarations and multi-page layout, legacy region `xy`/`size`/`orig`/`offset` fields, rotation, filter/wrap attributes, trimming/original dimensions, and indexed regions. Target output is reparsed. Texture bytes are not transformed. Full attachment-to-atlas and page-to-texture dependency verification has passed for the available combined real fixture; broader fixture coverage remains open.

## F. Testing and executed checks

- `.venv/bin/python -m pytest -q` — 58 passed.
- `.venv/bin/ruff check src tests` — passed.
- `.venv/bin/mypy` — strict typing, 21 source files, passed.
- `.venv/bin/python -m build` — sdist and wheel passed; runtime `.mjs` harness is included in the package.
- Installed `.venv/bin/spine-forge convert skeleton` with explicit known-risk policy — real fixture converted and reported its risk provenance and structural metrics.
- Installed `.venv/bin/spine-forge convert atlas` — 1 page and 6 regions converted.
- Installed `.venv/bin/spine-forge runtime-smoke` with official 4.2.43 package — animation-state evaluation passed as detailed above.
- B1 inspection of complete source and target directories — both passed with matching skeleton attachment paths, one resolved atlas, and one resolved page texture.
- Tests cover deterministic output, source immutability, Bézier numerical equivalence, malformed curves, unknown timelines, missing linked-mesh parents, invalid constraint references, missing schema fields, invalid target requests, atlas semantics, and rejection of nonmatching runtime package identity.

## G. Git state

- Development branch: `codex/b2-conversion-engine`.
- Tested pre-hardening checkpoint: `74af8b33b9d7b3303b23762671a50283c417a9a9` (`Checkpoint B2 Spine 3.8 to 4.2 conversion`).
- Final implementation commit: recorded after this report and the qualification changes are committed.
- Working-tree status: recorded with the final commit.

## H. Remaining work

- Implement and route-test real migrations for 4.2->4.3, 4.1->4.2, 4.0->4.1, 3.8->4.0, 3.7->3.8, 3.6->3.7, and 3.5->3.6; verify any composed paths end to end.
- Add valid fixtures and negative cases for each new route. No route should be inferred from family recognition.
- Broaden 3.8 qualification with real assets for weighted and linked meshes, every supported constraint/timeline class, and companion atlases. Add an authentic 3.8.99 regression fixture when available.
- Keep runtime parsing/evaluation evidence distinct from rendered visual comparison; visual equivalence is not certified here.

## I. Freeze decision

**B2 OPEN / BLOCKED.** The initial migration is materially hardened and has exact matching runtime smoke evidence, but the planned version-family route matrix and corresponding per-route qualification are unfinished. This report does not claim B2 closure, runtime certification beyond the tested asset, or visual equivalence.
