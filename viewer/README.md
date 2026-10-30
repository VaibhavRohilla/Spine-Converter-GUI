# B4 developer viewer

Run from the repository root. Read [runtime licensing](../docs/B4_LICENSES.md) before use or redistribution.

```sh
.venv/bin/python -m pip install -e '.[viewer]'
npm ci
npm run prepare:runtime
npm run build
npx playwright install chromium
.venv/bin/python -m fnx_spine_forge.viewer.server \
  --source viewer/fixtures/4.2 --bundle spineboy-pro.json
```

Open the printed loopback capability URL. Keep that URL private. Assets and runtime code stay local; the build preparation downloads pinned official dependencies. Select a second catalog asset for comparison by supplying another `--source`/`--bundle` pair. The full fixture catalog is available through `.venv/bin/python viewer/scripts/test_server.py`.

The host keeps two independent iframe documents active. Each owns its official runtime, skeleton instances, clock, WebGL context and GPU resources. Use animation/skin selectors, playback controls, seek, step, speed, mix duration, background and debug controls. Drag to pan, scroll to zoom; focused canvas supports arrow keys, +/- and 0 to reset. Capture downloads the actual canvas PNG. The comparison panel uses a common viewport/camera and deterministic normalized times; it reports duration differences and never grants conversion qualification.

## Reusable B5 API

Python `ViewerService.prepare(source, bundle_id, mappings=None, binary=None, pma=None, cancellation=None)` reuses B1/B3 inspection. `source` accepts the existing source selection contract (including folder/ZIP). `bundle_id` is the explicitly selected discovered skeleton path. Binary selection requires `BinarySelection(export_version, atlas)` and exact bytes approved in the packaged `trusted_binary.json`. Untrusted binary is disabled on every platform with `UNTRUSTED_BINARY_DISABLED`; see the trust policy below. The official runtime still confirms the unchanged version. A successful asset snapshot is immutable. `ViewerServer((asset, ...), Path('viewer/dist')).start()` returns a session-authorized URL; always call `close()` when the host exits.

`GET sessions.json` lists catalog descriptors; `GET launch/<index>.json` creates a managed session. These routes are relative to the capability URL. `frame.html?index=<index>` hosts one renderer; `index.html` hosts two. Do not invent filesystem URLs or expose an unrestricted file handler.

Import `SpineViewer`, `createHostBridge`, `ComparisonSession` and types from the built `component.js`. Construct `new SpineViewer(canvas, assetDescriptor, sessionId)`, then `await viewer.load()`. Direct APIs and their exact types are in `src/viewer.ts` and `src/contracts.ts`. Asset descriptors are validated by `src/protocol.ts`; Python creates them with `ViewerAssetSet.descriptor`. `viewer.dispose()` cancels work and releases resources.

The version 1 command envelope is `{protocolVersion: 1, sessionId, requestId, command, payload}`. `await viewer.request(envelope)` returns a typed reply with the request ID, result or diagnostics. Commands: PLAY, PAUSE, RESUME, STOP, SEEK, STEP, SET_ANIMATION, SET_SKIN, SET_LOOP, SET_SPEED, SET_CAMERA, RESET_CAMERA, SET_DEBUG, SET_VIEWPORT, SET_BACKGROUND, CAPTURE_POSE, CAPTURE_FRAME, GET_RUNTIME_INFO, DISPOSE. Loading is the separate validated `load` API; unload uses dispose, followed by a new session. Unsupported track controls are not advertised.

For Qt, `createHostBridge(viewer)` exposes `submit(serializedEnvelope)`, `takeReplies()` and `takeEvents()`. Submit accepts only validated commands for that session; it returns false for malformed/full/duplicate pending requests. Poll and drain replies/events. The developer frame exposes this object as `window.fnxBridge`. The Qt harness uses JSON serialization for JavaScript arguments, an off-record profile and an origin-restricted request interceptor. No PySide6 dependency enters the rendering core.

Events include LOAD_STARTED, RUNTIME_READY, ASSETS_LOADED, VIEWER_READY, PLAYBACK_CHANGED, ANIMATION_COMPLETE, ANIMATION_EVENT, RUNTIME_WARNING, RUNTIME_ERROR and SESSION_DISPOSED. Capture results contain image checksum, runtime/export identities, camera, viewport, background and animation timing. `VerificationService.record_capture` publishes evidence transactionally; image comparisons require explicit normalization and accepted reference policy for any frame-level visual certification. Conversion qualification remains outside this API.

```sh
./scripts/verify_b4.sh
.venv/bin/python -m pip install -e '.[qt-smoke]'
.venv/bin/python viewer/scripts/qt_smoke.py /tmp/fnx-b4-qt-new
```

Qt output must be a fresh path. The Python wheel contains orchestration and the runtime registry; distribute the separately built `viewer/dist` with matching manifest and license notices. The source archive includes frontend source/fixtures, not installed npm dependencies. Restore authentic official fixtures using `node viewer/scripts/fixtures.mjs` (pinned hashes); private production fixtures are never downloaded by that script.

See [B4 qualification](../docs/B4_REPORT.md) for tested coverage and remaining restrictions. This developer viewer is not the B5 desktop UI.

## Typed host subscriptions

`viewer.subscribe(listener)` receives a discriminated `[eventName, payload]` union and returns an unsubscribe function. Narrow on the name to obtain the exact payload type. Subscriptions are released at disposal; host observer errors are reported to the browser without failing the renderer. The polling bridge forwards all defined events, including FRAME_CAPTURED and VIEWER_UPDATED. Bone transforms and RGBA values have fixed-length tuple types. Runtime factories, family types and runtime-family validation derive from the canonical manifest. Version-specific official API bindings remain explicit: they are required runtime implementations, not deprecated compatibility fallbacks.


## Restricted binary trust policy

No OS resource-contained binary worker is qualified in this release. Arbitrary binary
uploads are disabled on macOS, Linux and Windows. The five previously verified official
Spineboy exports are admitted by SHA256, byte length and exact export version from
`src/fnx_spine_forge/viewer/trusted_binary.json`. This file is packaged in the wheel and
compiled into each browser build. It is not a session setting or upload-provided claim.
Adding an approved asset requires a reviewed release change and corresponding runtime
verification. Do not add an unknown file merely to get past an admission failure.

Both Python and browser hash the actual bytes. Python rejects unapproved `.skel` siblings
before B1 inspection; use an explicit source selection when a directory also contains
unapproved files. Binary reads are capped at 32 MiB; approved bytes have fixed known
sizes. The browser checks before allocating renderer resources or invoking the binary
reader. Modified headers, counts, strings, geometry, indices and truncations cannot
match the approved bytes. This is a trusted-local fixture policy, not a claim that a
preflight decoder, iframe, RSS sampler or JavaScript heap flag safely contains hostile
parsing. No source version is rewritten. B3 custom codecs remain unqualified.

## Qualification commands and candidate references

`npm test` compares 44 explicitly **unaccepted candidate** images in
`docs/evidence/B4/candidate-references` and runs six visual negative tests. Fixture-specific
tolerances are validated from `viewer/tests/visual-tolerances.json`; stricter Coin budgets
protect small alpha/clipping details. The same software backend is required for these
regression budgets. Differences and overlays go to `docs/evidence/B4/visual-comparisons`.

To deliberately regenerate candidates after a reviewed rendering change, run
`B4_CAPTURE_CANDIDATES=1 npm test -- viewer/tests/visual.spec.ts`, review the image and
metadata diff, then run the same test without that variable. Generation never sets
acceptance to verified. The 16 `derived-blend-*` cases retain official Coin geometry and
animation but explicitly modify slot blend modes over a gray background; they are not
unmodified official reference images. Capture, candidate regression, independent visual
acceptance and source-to-converted equivalence remain distinct outcomes.

Run `node viewer/scripts/soak.mjs` for 200 load/dispose cycles plus 1800 seconds of paired
3.8/4.3 physics playback. Budgets are written before execution. The harness samples the
Node/browser/server process tree RSS (not a memory ceiling), post-GC JS heap and native
resource counts; checks listener/scheduler/subscriber disposal; forwards and checks server
lifecycle acknowledgments; and resumes playback after each capture. Optional
`B4_SOAK_SECONDS`, `B4_SOAK_CYCLES`, `B4_SOAK_OUTPUT` configure a diagnostic workload;
a shorter run does not qualify the extended gate. The current RSS collector uses POSIX
`ps`, so this harness itself is not a Windows qualification.

`B4_VIEWER_PYTHON=/absolute/installed/venv/bin/python npm test` runs the fixture server
through that installed interpreter in isolated (`-I`) mode. Hosts creating sessions via
`launch/` must forward ordered PLAYBACK_CHANGED states to `state/<sessionId>` and await
DISPOSED acknowledgment before releasing transport ownership. A capture pauses playback;
resume explicitly when appropriate. No B5 desktop shell is included.


Qualification lifecycle hardening: binary policy metadata is validated into immutable
Python records before admission. Download failures preserve typed diagnostics and
release their stream readers. Browser test servers handle spawn errors and repeated
shutdown, escalating an unresponsive child after five seconds. Soak results include
explicit `budgetFailures` and reject nonfinite or insufficient trend samples. Short
workloads report `DIAGNOSTIC_PASSED` only when their measured budgets pass; they do
not qualify the extended release gate. The 200-cycle / 120-second hardening run is
retained under `docs/evidence/B4/soak-hardening`; the earlier failed short run is also
retained. Neither is an independent accepted rendering reference.

B5 can query the binary restriction before loading: Python
`RuntimeFeature.APPROVED_BINARY_ONLY in runtime.capabilities`, or the exported
TypeScript `runtimeCapabilities[family]` from `component.js`. This typed capability
is manifest-derived and mandatory whenever binary loading is implemented. It does
not authorize arbitrary binary input. Explicit binary selections are gated even
when their filename extension is changed; ordinary renamed JSON input cannot select
the binary reader. The viewer CLI routes through `ViewerService` and does not expose
an explicit binary-selection switch. Standalone B3 codec tooling is separately
experimental and is not an approved viewer admission path.

See [the pending visual review queue](../docs/B4_VISUAL_REVIEW.md). Run
`.venv/bin/python viewer/scripts/visual_review.py` after regression checks to verify
retained frame/source identities and refresh the unapproved review manifest.
