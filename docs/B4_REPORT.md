# B4 qualification report

## Final publication — 2026-10-27

**Restricted engineering checkpoint: QUALIFIED. Full B4: PARTIAL.**

Implementation checkpoint: `ca81353421b17f2d9a5019dbabef7f6bbba52ce0` on
`codex/b3-production-hardening`. This report and its evidence are published in the
following report commit (obtain the exact publication SHA with `git rev-parse HEAD`).
The existing full-freeze contract still requires independently accepted rendering
references. No full B4 freeze tag, production certification or visual-equivalence
claim is made. No critical unresolved correctness/security defect was identified
within this restricted qualification scope.

### Final checks

| Check against final implementation | Result |
|---|---|
| `bash scripts/verify_b4.sh` | PASS: 465 Python tests, Ruff, strict mypy (59 files), wheel/sdist, TypeScript typecheck, lint, viewer build, 146 TypeScript/browser tests, diff check |
| Fresh installed wheel, isolated Python `-I` fixture server | PASS: all 146 tests; service imported from isolated site-packages |
| Qt WebEngine 6.10.3 capture/bridge/disposal | PASS: real 1024×1024 DPR2 capture; DISPOSE acknowledged; no sandbox overrides |
| Binary rejection | PASS: Python pre-inspection admission, folder/ZIP and renamed explicit selection; browser forged metadata/actual bytes; CLI folder/ZIP rejection before server startup |
| Runtime selection, animation, frame/pose capture, cleanup | PASS across declared 3.8/4.0/4.1/4.2/4.3 adapters in the suite |
| Visual regressions | PASS: 44 retained candidates and six deliberately broken rendering cases detected |
| Controlled extended stability | PASS: 200 real load/dispose cycles plus 1809.414 seconds sustained paired 3.8/4.3 playback |
| Final source/build identity check | PASS: pinned manifest, trust policy, lockfile and built viewer hashes unchanged throughout soak |

Evidence: [closure summary](evidence/B4/closure-20261027/closure.json),
[verification log](evidence/B4/closure-20261027/verify.log),
[installed-wheel log](evidence/B4/closure-20261027/installed-wheel-browser.log),
[Qt record](evidence/B4/closure-20261027/qt/embedding.json), and
[build/dependency identities](evidence/B4/closure-20261027/identities.json).
Two newly added browser tests initially read state before initialization; the test
wait was corrected, then the full suite and installed-wheel suite passed. Failed
logs are retained. Incoming files and complete diff were preserved before edits in
`incoming-snapshot.tar.gz`; log trailing whitespace was normalized for diff checks.

### Controlled extended stability

Command: `B4_SOAK_SECONDS=1800 B4_SOAK_CYCLES=200
B4_SOAK_OUTPUT=docs/evidence/B4/closure-20261027/soak-awake
caffeinate -i -s node viewer/scripts/soak.mjs`.
No heavy build/test workload was launched alongside it. Sleep-prevention assertions
were confirmed. Total duration: 1823.100s; playback samples:
180; maximum sample interval: 10.146s.
The two sessions rendered 108726 / 108725
frames. Each interval advanced both renderers. The cycle phase exercised real
animation, skins, seek, frame/pose capture, stop and disposal across runtime families.

| Measurement | Observed |
|---|---:|
| Late-cycle heap growth | 392156 bytes |
| Late-cycle RSS growth | -44352 KiB |
| Late-cycle heap slope | 2938.27 bytes/cycle |
| Late-cycle RSS slope | -837.86 KiB/cycle |
| Playback heap growth | 210608 bytes |
| Playback RSS growth | 12480 KiB |
| Playback heap/RSS fitted slopes | 53.64 bytes/s / -4.15 KiB/s |

Original budgets and cycle window (samples at cycle >=50) are unchanged: load
<=10s, heap growth <=64 MiB, RSS growth <=512 MiB, late slopes <=262144 bytes/cycle
and <=2048 KiB/cycle. No exclusions were added. Zero budget failures. Per-PID
Node/Python/browser-tree RSS and post-GC JS heap are retained in every sample.
RSS includes the transient `ps` sampler (classified among descendants), is an
aggregate host observation, and does not isolate GPU-driver memory or enforce a cap.

Final allocations/deletions balance: textures 213/213, buffers 404/404, programs
404/404, shaders 808/808; framebuffers and renderbuffers 0/0. Both sessions are
DISPOSED; active viewer sessions, live GPU objects, tracked listeners, schedulers
and subscribers are zero. Lifecycle acknowledgments completed; server exit 0,
no kill signal, no runtime errors or runtime warnings. Four browser WebGL
`GPU stall due to ReadPixels` performance warnings are recorded. Listener accounting
covers context-loss/restoration and visibility listeners, not every browser listener.
A finite passing soak does not prove leak-free behavior.

[Full result](evidence/B4/closure-20261027/soak-awake/result.json).
The earlier fresh run reported harness PASS but contained 88.874s and 603.371s
sampling gaps with little rendering; it is **not accepted as sustained playback**.
Its raw result and [continuity review](evidence/B4/closure-20261027/soak-continuity-review.json)
are preserved alongside all earlier failing and passing evidence. Suspected host
sleep/suspension was addressed with sleep prevention, not threshold changes.

### Binary trust and B5 contract

Only the five packaged official fixture identities are admitted by actual SHA256,
exact byte length and export version. Admission occurs before B1/B3 inspection in
`ViewerService`, including `.skel` siblings and explicit binary selections with
renamed extensions; folder/ZIP source controls remain canonical. The browser
independently hashes bytes before the official binary reader. Forged transport
hashes, modified headers/lengths and version claims cannot grant approval. A false
JSON format claim selects the JSON parser and cannot select the binary reader.
The viewer CLI routes through the same service and exposes no explicit binary
selection flag. Standalone B3 codec commands remain separately experimental;
this policy does not claim to sandbox them or qualify their custom codec.

B5 can query `RuntimeFeature.APPROVED_BINARY_ONLY` in Python or exported
`runtimeCapabilities[family]` in TypeScript without attempting a load. Both derive
from the existing manifest. No new decoder, adapter layer or alternative renderer
was introduced. Untrusted binary support and OS-enforced memory containment remain
unqualified on every platform. B3 decoding/encoding/conversion fidelity and
source-to-converted visual equivalence remain unqualified.

B5 must use immutable service snapshots, validate descriptors and protocol messages,
keep the capability-token server local, forward ordered lifecycle states and await
DISPOSED acknowledgment, dispose viewers/subscriptions and close the server.
Capture pauses playback; explicitly resume when appropriate. Retain the byte,
texture and session limits and report binary restrictions before user selection.
The final B5 desktop application is outside this checkpoint.

### Visual review, supported scope and remaining blocker

[Visual review queue](B4_VISUAL_REVIEW.md) and its linked machine-readable manifest
bind all 44 candidates to verified source/frame hashes, pinned runtime revision,
animation/time/skin, camera/viewport/DPR, explicit background/alpha policy, expected
features, thresholds and actual comparisons. The six negative regression results
are included. Reviewer identity/date, evaluated criteria, decision and exclusions
remain pending. No reviewer or approval was fabricated. Status is
**CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED**. Repeatability, artistic acceptance and
source-to-converted equivalence are separate decisions.

Supported embedded families: 3.8 (revision
`8b4844bd4b193ba9e54487ed397a777993cbad56`), 4.0.31, 4.1.56, 4.2.43 and 4.3.13
runtime builds. These are fixture/feature-scoped results, not universal export
support. Families 3.5–3.7 are recognized but unsupported; other undeclared families
are unsupported. PNG-only textures and existing animation/camera restrictions remain.

Verified host: macOS 26.6.2 / Darwin 25.6.0 arm64, Mac16,13, 16 GiB RAM,
Python 3.12.15, Node 24.21.0, Chromium 156.0.8078.4. Chromium uses **ANGLE SwiftShader
software WebGL**. Qt has real local capture/disposal evidence but no separately
recorded hardware-renderer identity. Hardware GPU, Linux and Windows qualification
are not claimed. Dependency/build identities are recorded; no runtime dependency
upgrade was made. Python packaging declares some version ranges; the tested tool
versions are recorded rather than claiming those declarations are exact locks.

**Remaining full-B4 release blocker: independent visual acceptance by an authorized
reviewer of the exact candidate references and documented criteria/exclusions.**
Hardware/cross-platform qualification and B3 custom binary fidelity remain outside
this restricted engineering checkpoint, not silently certified by it.

---

## Historical evidence — not current release status

The sections below retain earlier counts, Git states and pending gates as history.
The final publication above supersedes their release-status statements.

## Historical boundary and lifecycle hardening follow-up — 2026-10-27

The following changes extend the current uncommitted candidate without changing
runtime adapters, the B5 API, rendering algorithms or conversion qualification:

- Python binary approvals are immutable `ApprovedBinary` domain records. The full
  packaged policy is validated before admission: lowercase SHA256, exact keys,
  bounded integer length (booleans rejected), valid version syntax and HTTPS
  provenance without credentials. Malformed unrelated records fail the policy;
  raw recursive JSON values do not escape into binary admission logic.
- Resource downloads validate byte budgets before network access, cancel rejected
  HTTP bodies, release reader locks on success/failure, normalize read failures to
  ASSET_TRANSPORT_FAILED and retain the original typed diagnostic if cancellation
  itself throws. No cleanup error replaces a resource-limit failure.
- The typed browser-test server owner observes process close before startup,
  handles spawn errors, bounds captured stderr, makes close idempotent and sends
  SIGKILL after a five-second graceful shutdown deadline. Real subprocess tests
  cover missing executable, already-exited child, repeated/concurrent shutdown and
  a child ignoring SIGINT. This is harness lifecycle proof, not binary sandboxing.
- Soak startup failures now enter cleanup/reporting; browser-close failure cannot
  skip server cleanup. Trend-sample admission occurs before arithmetic, nonfinite
  measurements fail, and budget failures identify metric/value/limit. Unused
  allocation-map and Performance-domain instrumentation were removed.
- The Python fixture server derives embedded runtime families from RuntimeRegistry;
  its duplicate five-family list was removed. Required historical-version adapters
  remain legitimate implementations.

Fresh `bash scripts/verify_b4.sh` passed **454 Python tests**, Ruff, strict mypy
(59 source files), Python wheel/sdist, TypeScript typecheck, lint, build, and the
then-current **141 browser tests**. Two additional real-process shutdown tests
subsequently passed; typecheck and lint passed again. The final rebuilt viewer
then passed all **143 browser tests** against the freshly reinstalled wheel via
`B4_VIEWER_PYTHON=/tmp/fnx-b4-wheel-final/bin/python npm test`. See
`evidence/B4/logs/hardening-installed-wheel-browser.log`. A fresh real Qt smoke
also passed capture and DISPOSE acknowledgment with no sandbox overrides; see
`evidence/B4/qt-hardening/embedding.json`. Its capture hash remains
`596ac66302b259c7933e8ea5102c003078154e97c110c23ddda04bff48bd42e8`. See
`evidence/B4/logs/hardening-verification.log`.

The fresh `B4_SOAK_SECONDS=120 B4_SOAK_CYCLES=200
B4_SOAK_OUTPUT=docs/evidence/B4/soak-hardening node viewer/scripts/soak.mjs`
completed as **DIAGNOSTIC_PASSED** in 134.545 seconds with unchanged budgets.
Late-cycle heap growth was 392536 bytes; RSS growth 43856 KiB; slopes were
2932.31 bytes/cycle and -7.31 KiB/cycle. Playback heap growth was 91672 bytes,
RSS growth -64288 KiB. There were no budget failures or runtime errors. Both
sessions disposed; tracked GPU objects, schedulers, listeners and subscribers
were zero; server exit was zero. The full verification suite ran concurrently,
so this is observed shared-host diagnostic evidence, not a controlled timing
benchmark. The earlier 30-cycle failure is retained. Longer-cycle measurements
do not demonstrate continuing RSS growth, but a fresh 30-minute final-candidate
soak remains outstanding. See `evidence/B4/soak-hardening/result.json`.

**Decision remains B4 PARTIAL.** No accepted visual baseline, hardware-GPU proof,
new extended qualification, commit, clean-tree claim or freeze was manufactured.

## Historical qualification — 2026-10-27

### A. Security policy and process containment

The actual starting HEAD was `b729bedfb7311ca9f64cf3c3862421a1fa031157`, on
`codex/b3-production-hardening`. Contrary to the supplied clean-tree baseline, the
binary policy, animation/visual tests and soak evidence were already uncommitted.
They were preserved and reviewed, not attributed to a newly created commit.

Untrusted binary parsing is **disabled on every platform**. Python admission runs
before B1 inspection, including binary siblings; the browser independently hashes
actual bytes before creating WebGL resources or calling the official binary reader.
The packaged trust manifest admits exactly five official Spineboy binaries by
SHA256, length and export version. The 32 MiB read/stream cap is enforced before
parsing. Transport hashes and caller-supplied version claims cannot grant trust.
Changed headers, truncations, strings, declared counts, indices and geometry fail
approval rather than reaching a speculative second binary decoder. Trusted-local
mode is not safe arbitrary-upload mode. Runtime manifest warnings document this
restriction. No source version metadata or Chromium/Qt sandbox setting is changed.

A disposable browser process alone does not establish a memory ceiling. Evaluated
platform mechanisms:

- Linux [cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html):
  memory.max and group OOM handling are relevant, but delegation, renderer-child
  membership, external deadlines and recovery were not implemented or tested here.
- Windows [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
  and [job memory limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information):
  job-wide committed memory and tree termination are relevant; no Windows host or
  validated sandbox-compatible assignment was available.
- macOS [setrlimit documentation](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/setrlimit.2.html)
  describes RSS pressure behavior, not evidence of an enforced browser-tree ceiling.
  No suitable process containment has been qualified on this host.

Consequently no untrusted worker is launched. Worker timeout, forced worker death,
worker crash recovery and OS memory-budget enforcement are **not qualified**.
Hostile tests instead prove rejection before parsing, no false READY, repeated
rejection and a surviving JSON session. This satisfies the restricted admission
alternative, not the worker-containment alternative. Oversized HTTP responses now
explicitly cancel their body streams before returning the resource-limit diagnostic.

### B. Rendering evidence

The fresh browser suite passes candidate comparisons for 44 captures, including
16 explicitly derived Coin blend-mode cases. Metadata records source hashes,
export/runtime identity, animation/time/skin, viewport/camera/DPR, background,
image hash and **CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED** status. Tolerances are
fixture-specific; comparisons emit pixel/alpha/mean/maximum deviations, masks and
overlays in `evidence/B4/visual-comparisons`. Six negative cases detect deliberately
broken rendering. Official feature/physics fixtures exercise alpha, atlas geometry,
mesh/deform, clipping, skins and constraints through the original official adapters.

These are regression candidates, not accepted references. No independent reviewer
or authoritative expected-image set was supplied. Required accepted-reference
coverage therefore remains OPEN, including complete per-feature visual fidelity.
Capture success, candidate repeatability and original-to-converted equivalence
remain separate; the latter is unverified. No baseline was automatically accepted.
Only Chromium ANGLE SwiftShader software WebGL is qualified by these comparisons;
hardware GPU and other operating systems remain unqualified.

### C. Stability evidence and limits

The pre-existing `evidence/B4/soak/result.json` records PASSED: 200 load/dispose
cycles and 1800 seconds requested paired 3.8/4.3 physics playback, 1821.016 seconds
total, on Darwin 25.6.0 arm64 / Chromium 156.0.8078.4 / SwiftShader. This evidence
was inspected in this pass, not rerun as a fresh 30-minute execution.

Budgets were recorded before execution: load <10 seconds, heap growth <=64 MiB,
process-tree RSS growth <=512 MiB, late-cycle heap slope <=262144 bytes/cycle,
RSS slope <=2048 KiB/cycle, no runtime errors and zero tracked live GPU objects.
Measured late-cycle growth: heap 346608 bytes, RSS 159408 KiB; slopes 2612.61
bytes/cycle and 1052.90 KiB/cycle. Playback heap grew 234424 bytes and RSS fell
557824 KiB. Both sessions ended DISPOSED; GPU objects, tracked listeners,
schedulers and subscribers were zero; server exit was zero; errors were empty.

Positive cycle RSS slope is explicitly retained: passing this finite host budget
does not prove asymptotically leak-free operation. RSS includes the Node/browser/
server process tree and is not a ceiling or isolated GPU-memory measurement.
Load/animation/skin/seek/capture/disposal work uses real official adapters.
Context-loss/retry and cancellation are separately covered by browser tests.
The harness now refuses insufficient trend samples and labels workloads below
200 cycles or 1800 seconds DIAGNOSTIC_PASSED, never an extended-gate pass.
No new extended-soak claim is made for that reporting-only harness change. A fresh
30-cycle / 20-second diagnostic FAILED the stability budget; see
`evidence/B4/soak-final-diagnostic/result.json`. Its late-cycle RSS slope was
2755.31 KiB/cycle against the 2048 KiB/cycle limit.
Tracked GPU objects, schedulers, listeners and subscribers were nevertheless zero
after disposal and server exit was zero. This short cold-start workload does not
replace the retained 200-cycle soak, but its failure is retained without widening
budgets. Fresh extended stability confirmation remains outstanding.

### D. Animation and typed-contract audit

The added real-adapter tests cover start/end, loop wrap, repeated seek, interrupted
mix, playback skin changes, stepping, pending-callback disposal and 4.2/4.3 physics.
An official 4.2 runtime test compares event ordering at exact keyframe boundaries
across update partitions. Runtime evaluation remains authoritative. Seeking resets
mixing history and fixed-step replays physics; arbitrary random-access equivalence
is not claimed. See `evidence/B4/animation` and `viewer/tests/animation.spec.ts`.

Application type/lint gates pass. Canonical runtime registration and all five
version-specific implementations remain intact. No unconstrained Any domain
contract, compatibility shim or second renderer was introduced. No genuinely dead
adapter was identified for removal. Existing literal `as const` declarations are
not treated as unsafe external-data conversions. Existing validated protocol,
cancellation generations, host callback isolation and typed event contracts remain.

### E. Qt and B3/B5 boundaries

A fresh real PySide6 6.10.3 smoke passed with an off-record profile, no sandbox
overrides, asynchronous replies, a 1024x1024 DPR2 capture and DISPOSE acknowledgment.
See `evidence/B4/qt-final-current/embedding.json`; capture SHA256 is
`596ac66302b259c7933e8ea5102c003078154e97c110c23ddda04bff48bd42e8`.
This is macOS embedding evidence, not cross-platform desktop qualification.
B5 remains unstarted. The five approved binary fixtures test official loading only;
FNX custom binary decoding, encoding and cross-version conversion remain unqualified.

### F. Fresh verification and Git

`bash scripts/verify_b4.sh` executed the requested pytest, Ruff, strict mypy,
Python wheel/sdist build, npm typecheck/lint/build/test and diff checks. Results:
**435 Python tests, 133 TypeScript/browser tests, all passed**; mypy checked 59 files.
Full output: `evidence/B4/logs/final-verification.log`. The initial sandboxed run
could not bind local sockets. The first unrestricted run also exposed relocated
virtualenv entrypoints/editable metadata referencing the old workspace; reinstalling
this checkout and repairing those local entrypoints resolved the failures without
weakening tests. Typecheck/lint/build were rerun after the stream-cleanup edit.

Installed-wheel verification also passed all **133 browser tests** after the final
stream-cleanup edit: `B4_VIEWER_PYTHON=/tmp/fnx-b4-wheel-final/bin/python npm test`.
The wheel was installed without dependencies into a fresh system-site-packages
virtualenv; `python -I` confirmed the service module came from that environment's
site-packages, and the packaged trust policy admitted the approved 4.2 fixture.
Log: `evidence/B4/logs/final-installed-wheel-browser.log`.

Current implementation and report changes are **uncommitted**. HEAD remains the
verified baseline above; no report commit or freeze tag was created. The working
tree is **dirty**, including preserved incoming work. Historical commit identifiers
below do not describe this candidate. No clean-tree or release publication claim is
made. Accepted-reference review and clean publication remain prerequisites for any
restricted freeze. Decision: **B4 PARTIAL — PLAYBACK CORE VERIFIED**.

---

The following sections describe earlier implementation and qualification history.

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


## Typed-contract hardening follow-up

The subsequent production-hardening pass retains the PARTIAL decision and the outstanding gates in section J. Current regression totals are **428 Python tests and 69 TypeScript/browser tests**, all passing. Ruff, strict mypy, stricter TypeScript checking, lint, production build, Python wheel/sdist build and repeated-build identity checks passed. Qt WebEngine capture/bridge/disposal passed again with the same image checksum; see `evidence/B4/qt-typed` and `logs/typed-*.log`. Browser/fixture evidence has been refreshed for this revision; the original qualification counts above describe the initial implementation commit.

Changes: fixed-size bone-transform/RGBA tuples; finite lifecycle state type; discriminated event payloads; unsubscribe/disposal-aware typed host subscriptions; complete bridge event forwarding including frame capture; host observer exception isolation; generated runtime factories/family schemas from the canonical manifest; enum-backed Python runtime features with rejection of duplicate/contradictory capabilities and incomplete identities. Redundant runtime-family declarations and the bridge's unchecked CustomEvent cast were removed. TypeScript now enforces exact optional properties, explicit returns, switch fallthrough checks and override checks. Lint disallows explicit `any` and `unknown` in application code. Caught foreign exceptions remain untrusted until narrowed to Error; no unsafe casts replace that validation.

Required 3.8/4.0/4.1 adapters are retained as supported product features, not backward-compatibility fallbacks. Each implements its official API directly. No deprecated runtime API or unused compatibility shim was found that could be removed without losing requested playback coverage. Version-specific behavior and bounded security limits remain explicit; making them arbitrary dynamic inputs would weaken correctness. No claim of universal production readiness or a subjective “10/10” replaces the remaining qualification work.
