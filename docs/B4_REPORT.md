# B4 qualification report

**Decision: B4 PARTIAL — PLAYBACK CORE VERIFIED.**

Actual embedded official WebGL playback, pose/frame capture and independent sessions are implemented and tested for **3.8, 4.0, 4.1, 4.2 and 4.3**. This is not a complete production freeze: hostile binary allocation containment, exhaustive rendering-reference checks and extended stability qualification remain incomplete. No conversion route or custom binary codec is promoted by this work. No source-to-converted visual equivalence is certified.

## A. Architecture and baseline

Work started on `codex/b3-production-hardening`, clean at B3 qualification commit `0c2b3a315` following `659dbe465`. B2 freeze `a6173e32fb19d42b67e33b2113366f4006ab509d` was verified in ancestry. All 382 pre-existing Python tests remain passing.

Python `src/fnx_spine_forge/viewer/` contains `service.py` (immutable asset snapshots using B1 source controls and B3 bundle selection), `admission.py` (bounded rendering preflight), `registry.py`/`runtime_manifest.json` (runtime identity/capabilities), `session.py` (legal state transitions and generations), `protocol.py` (typed command admission), `server.py` (loopback capability transport), and `verification.py` (transactional capture evidence and policy-controlled comparison).

TypeScript `viewer/src/` contains `viewer.ts` (session/playback/camera/capture), `kernel.template` (statically generated per-version official API bindings), `clock.ts`, `resources.ts`, `contracts.ts`, `protocol.ts`, `diagnostics.ts`, `comparison.ts`, `bridge.ts`, and `component.ts`. `frame.ts` is the minimal standalone developer UI; `host.ts` embeds two separately selected runtime documents. Build scripts generate adapters and bundle local dependencies; no runtime CDN, PixiJS, Three.js or custom animation interpolator is used.

The only existing B1 implementation correction is attachment region lookup respecting an authored attachment `name` when `path` is absent. Authentic Goblins exports exposed that defect; a regression test covers it. B2/B3 conversion and binary implementation and qualification registries are unchanged.

## B. Runtime support matrix

All implemented backends use official spine-ts WebGL. Availability additionally requires a built local viewer with an exactly matching manifest; recognition alone does not imply installation. Package revision is recorded separately from the skeleton export version. Major/minor matching follows [official Spine versioning](https://esotericsoftware.com/spine-versioning).

| Family | Exact runtime revision | Tested export | JSON / binary | Evaluation / rendering / headless capture |
|---|---|---|---|---|
| 3.5 | None installed | None | Unsupported | NOT_IMPLEMENTED |
| 3.6 | None installed | None | Unsupported | NOT_IMPLEMENTED |
| 3.7 | None installed | None | Unsupported | NOT_IMPLEMENTED |
| 3.8 | Official source `8b4844bd4b193ba9e54487ed397a777993cbad56` | 3.8.55 | Both tested | All tested |
| 4.0 | `@esotericsoftware/spine-webgl@4.0.31` | 4.0.31 | Both tested | All tested |
| 4.1 | `@esotericsoftware/spine-webgl@4.1.56` | 4.1.17 | Both tested | All tested |
| 4.2 | `@esotericsoftware/spine-webgl@4.2.43` | 4.2.22, converted 4.2.43 | Both tested | All tested |
| 4.3 | `@esotericsoftware/spine-webgl@4.3.13` | 4.3.75-beta, converted 4.3.13 | Both tested | All tested |

Exact npm git identities: 4.0 `a6491f31bcd973e1a640d786913bf8f8cac1ae3c`; 4.1 `e27e6dacfdf7d9b04de7dce48fd857f7b5ead9ca`; 4.2 `8bca84f46e00d1d0d29ab0dc2406bef3b1248e17`; 4.3 `b7beb2ccbbce667a12c02f44d070644f59b04968`. npm lockfile integrity pins packages; 3.8 preparation verifies immutable source SHA256 values. The 3.8 wrapper only exposes the official namespace as a module; it does not alter parsing/version checks.

3.5–3.7 have no embedded adapter or verified external launcher. The official [libgdx Skeleton Viewer](https://github.com/EsotericSoftware/spine-runtimes/tree/3.7/spine-libgdx/spine-skeletonviewer) is a possible separate legacy reference, not implemented product support. No external launch is counted as embedded playback.

[Licensing and notices](B4_LICENSES.md) document the reviewed official terms, full per-family notices and fixture provenance. Spine runtimes are not treated as unrestricted permissive dependencies. Release redistribution remains subject to those terms and the distributor's applicable license; private production fixture authorization does not authorize public redistribution.

## C. Viewer functionality

Implemented animation listing/durations, selection and restart, play/pause/resume, stop/setup reset, looping, speed, explicit stepping, skin/default selection, transition mix duration, ordered native events and event-suppressed diagnostic seek. One animation track is exposed; arbitrary multitrack editing is unsupported. Seek recreates skeleton/animation state and discards mixing history, then simulates at 1/60 second with a final remainder. Long seeks yield for cancellation. Real-time deltas are capped at 50 ms and reset across visibility changes. Physics uses the official version-specific update order.

Camera supports fixed setup bounds, explicit common bounds, aspect-preserving fit, center/reset, pan/zoom, resize and bounded high DPI. Transparent/dark/white backgrounds are exposed. There is no per-frame automatic recentering, union-of-sampled-bounds camera or follow mode.

Official debug rendering is separate from clean captures: bones, region/mesh geometry, mesh triangles, clipping, paths and bounds as supported by the selected runtime. Pose inspection includes native local/world bone transforms and hierarchy, slots, attachments, draw order, world vertices, mesh topology/influences, colors, tracks and exposed constraint values. Unavailable internal solver/mixing fields are declared unsupported; they are not reconstructed with guessed formulas.

Explicit lifecycle includes inspecting/loading/initializing/ready/playing/paused/stopped/seeking/failed/disposing/disposed, legal transition validation, cancellation generation guards and explicit retry. Repeated PLAY owns one scheduler. Loading and texture completion precede READY. Context loss fails and releases resources; restoration permits explicit retry rather than claiming transparent state preservation.

## D. Rendering verification

Committed evidence is under [evidence/B4](evidence/B4). Actual PNGs are produced from the rendered canvas, with corresponding pose/runtime/camera/checksum JSON. Empty/placeholder output fails nontransparent-pixel assertions. Animation change, paused stability and repeated fixed-time pose/PNG equality are asserted separately.

| Evidence | Fixture and scope |
|---|---|
| [fixture-0.png](evidence/B4/fixture-0.png), fixture-0.json | Genuine official 3.8.55 Spineboy JSON |
| fixture-1 through fixture-9 | Spineboy JSON/binary pairs for all five families |
| [fixture-10.png](evidence/B4/fixture-10.png), fixture-10.json | Golden Ingot converted 4.2.43; source remains known-risk 3.8.75 |
| [fixture-11.png](evidence/B4/fixture-11.png), fixture-11.json | merged_multi converted 4.3.13, two texture pages, multiple animations, 151 bones/213 slots |
| feature-12 through feature-31 JSON and fixture PNGs | Official 4.2/4.3 Coin, Goblins, Raptor, Tank, Vine, paired straight/PMA exports |
| [physics-33.png](evidence/B4/physics-33.png), physics-34.png and JSON | Official Cloud Pot, 26 physics constraints, 4.2 and 4.3 |
| [paired-viewer.png](evidence/B4/paired-viewer.png) | Independent 3.8 and 4.3 sessions, controlled paired capture/difference UI |
| narrow-viewer.png | Narrow viewport and keyboard camera operation |

Authentic fixtures cover region, weighted and linked meshes/deform, clipping, IK/path/transform constraints, events, skins, draw order, two-color slots, rotated/trimmed atlases and alpha. The feature sweep records **40 animation samples and 28 skin selections** across 20 atlas/fixture combinations. Core 12 fixture cases capture setup, quarter and three-quarter duration plus repeat and pause checks. Production samples are not exhaustive event-boundary or full-animation fidelity sweeps.

Straight/PMA comparison has mean absolute channel error approximately 0.037 against a test tolerance of 1 (0–255 channel units), with a common camera. This is a paired encoding regression check, not artistic reference certification. Renderer APIs and output are exercised; there is no independently accepted reference covering every blend mode, edge bleeding, halo, clipping and two-color case. Do not infer universal rendering correctness from these samples.

## E. Animation fidelity and visual evidence

`CAPTURE_POSE` extracts official runtime state; `CAPTURE_FRAME` returns actual PNG data and SHA256, effective camera, viewport/DPR/background, simulation state and runtime revision. Repeated reset-and-step poses/frames match within the same fixture/runtime/environment, including both physics fixtures. This is scoped repeatability, not cross-driver bit identity or arbitrary stateful feature equivalence.

`ComparisonSession` independently selects two adapters, matches an animation name, reports both durations, synchronizes normalized time, applies a common explicit camera/viewport and captures both sides. Sampled synchronized playback advances both deterministic sessions. Structural/pose comparison guards missing bones and incompatible parent relationships and reports slot attachment/draw-order differences. A numerical world-transform difference alone does not establish semantic equivalence.

Image comparison produces changed pixels/percentage, mean and maximum RGBA error, alpha errors, overlay and diff. Python verification requires compatible normalization, accepted reference hash/provenance/reviewer and thresholds for frame-scoped `VISUALLY_VERIFIED`. No accepted authoritative original/converted baseline was available here, so all committed production evidence remains runtime/frame evidence. The paired UI reports `FRAMES_CAPTURED_NOT_VISUALLY_VERIFIED`.

The genuine original 3.8.75 fixture is retained unchanged. Its source risk is reported and the compatible official runtime rejects it; no version-string rewrite occurs. Original Golden Ingot playback and original-to-converted visual equivalence therefore remain unavailable. Converted-side evidence is retained independently. A genuine 3.8.55 export supplies valid 3.8 runtime qualification; it is not a relabeled 3.8.75 asset.

## F. B3 binary handoff

Existing authentic Spineboy `.skel` files load, evaluate and render through official 3.8/4.0/4.1/4.2/4.3 binary parsers. Odd-index fixture evidence 1/3/5/7/9 records these results and exact runtime identities. Explicit binary selection supplies the claimed export version and discovered atlas; the official parser validates actual version data.

This proves acceptance of those existing fixtures only. It neither uses nor qualifies FNX's experimental 4.2.43 custom hierarchy codec, binary encoder or cross-version binary migration. All evidence preserves `binaryCodecQualified: false`. B3 may reference these fixture/runtime records as a separately scoped reader reference.

## G. Security and resources

Selected source bytes are snapshotted through existing B1 archive/path controls and B3 associations. URLs reference selected mappings, not arbitrary paths. Loopback server uses an unpredictable capability, Host/Origin checks, CSP, no external runtime fetches, bounded request body/thread/session limits and socket timeouts. HTTP asset integrity is checked against snapshot SHA256. Texture admission currently accepts validated PNG only, at most 8192 per dimension, 16M pixels/page and 32M pixels/session; total source budget defaults to 256 MiB. JSON rendering admission limits traversal and feature counts. Ambiguous multi-skeleton selection is never automatically merged.

Tests exercise traversal, missing dependencies, invalid JSON/atlas/texture/binary, mismatched versions, bad names, nonfinite poses, missing transport, integrity failure, oversized resources, unsupported features, original 3.8.75, cancellation at loading/initialization/seek/capture, disposal and repeated playback. Context loss/restoration and explicit retry are exercised. GPU create/delete instrumentation checks texture/buffer/program/framebuffer balances after repeated unload, and animation listeners/schedulers are removed. Capture publication is atomic and refuses overwrite.

**Remaining safety gate:** official binary parsing is synchronous and can allocate from hostile declared counts before post-parse checks. An iframe provides runtime namespace/state separation, not a guaranteed OS memory budget or preemptible parser. Comprehensive hostile binary allocation containment and process-level recovery are not qualified. Do not expose this viewer as a service for arbitrary untrusted uploads. Finite fixture tests and size caps are not a claim of exhaustive hostile-input safety.

## H. B5 handoff and Qt

[viewer/README.md](../viewer/README.md) documents executable setup, session creation, asset descriptors, typed commands/events, cleanup and capture/report access. Built `component.js` exports `SpineViewer`, `createHostBridge`, `ComparisonSession`, schemas and types. The core has no PySide6 dependency. LOAD is the validated constructor/`load()` lifecycle API; the command protocol handles playback/camera/debug/capture/disposal. New assets use a fresh managed session, not a dynamic method dispatch channel.

The actual optional Qt smoke ran with **PySide6 6.10.3**, an off-record QWebEngineProfile, restricted local requests and no sandbox/debug bypass. It initialized WebGL, loaded local textures, executed typed asynchronous bridge commands, captured a 1024×1024 PNG from a 512×512 DPR2 viewport, and acknowledged DISPOSE. [qt-final/embedding.json](evidence/B4/qt-final/embedding.json) and its capture evidence record this result. This is one macOS Qt smoke, not cross-platform B5 desktop certification. Closing a production B5 host must dispose the viewer, close its server and release its profile/view.

## I. Test evidence and reproducibility

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | 422 passed (382 existing + 40 added) |
| `.venv/bin/ruff check src tests` | Passed |
| `.venv/bin/mypy` | Passed, 58 source files |
| `.venv/bin/python -m build` | Wheel and sdist built |
| `npm run typecheck` | Passed, all generated official version bindings |
| `npm run lint` | Passed |
| `npm run build` | Passed; repeated clean builds have identical file SHA256 values |
| `npm test` | 67 passed: 6 TS unit tests and 61 real-browser integration/hostile/rendering cases |
| `.venv/bin/python viewer/scripts/qt_smoke.py <fresh-output>` | Passed, actual Qt WebEngine capture and disposal |
| Installed wheel in isolated `/tmp` virtualenv | Imported viewer and prepared authentic 4.2.22 bundle |
| `git diff --check` | Passed before publication |

The full reproducible baseline gate is `scripts/verify_b4.sh`; setup/optional Qt commands are in the viewer README. Browser machine-readable results are [browser-results.json](evidence/B4/browser-results.json). Build hashes are [viewer-build.json](evidence/B4/viewer-build.json). Tests do not use mocks as the sole evidence of runtime operation. Fixture provenance files record immutable official source URLs/hashes, and distinguish private converted assets from authentic exports and the explicitly synthetic unit test.

Reference host: macOS Mac16,13, 16 GiB RAM. Chromium 156.0.8078.4 used **ANGLE SwiftShader software WebGL**, which executes the actual renderer but is not hardware-GPU qualification. [performance.json](evidence/B4/performance.json) records a two-second merged_multi run, CPU update/render submission timings, load/upload times and observed frame rate. Practical local budgets are load <10 seconds and update/render p95 <50 ms; these passed. Render timing is not GPU execution timing. The roughly 60 FPS sample is not a universal performance guarantee. No long-duration heap/driver-memory soak has been certified.

## J. Remaining qualification and freeze gates

B4 remains PARTIAL despite all minimum runtime families working. Required follow-up before a production restricted freeze:

1. Bound/preempt hostile synchronous binary parsing with an effective resource-isolation policy and exercise excessive-allocation recovery.
2. Expand accepted-reference rendering checks for blend modes, edge bleeding/halos, clipping and alpha across target graphics stacks. Current screenshots are evidence, not newly invented authoritative baselines.
3. Complete longer production load/unload/skin/animation soak and memory/driver resource observation, plus broader event-boundary/constraint sampling.

Explicit product restrictions remain: legacy 3.5–3.7 unavailable; PNG textures only; one controlled animation track; seek resets mix history; fixed/custom camera; runtime-exposed constraint fields only; capture repeatability scoped to the tested environment; source 3.8.75 reference unavailable. Arbitrary full 3.5–4.3 export/feature compatibility is not claimed. Final B5 desktop UI and B3 binary conversion qualification remain separately owned.

## K. Git publication

Branch: `codex/b3-production-hardening`. Implementation commit: `f60f0bff7e7c8d7f1912f8d7c302988b1af92f3a`. Qualification report commit: `7b96c34aca45313287ee605ae6c5f218b41ed90b`. Working tree was clean after that publication; this metadata-only follow-up records its immutable hash. There is no B4 freeze tag because the decision is PARTIAL. Frozen B1/B2/B3 boundaries remain in force.
