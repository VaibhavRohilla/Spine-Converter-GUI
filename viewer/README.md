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

Python `ViewerService.prepare(source, bundle_id, mappings=None, binary=None, pma=None, cancellation=None)` reuses B1/B3 inspection. `source` accepts the existing source selection contract (including folder/ZIP). `bundle_id` is the explicitly selected discovered skeleton path. Binary selection requires `BinarySelection(export_version, atlas)`; the official runtime confirms the unchanged bytes. A successful asset snapshot is immutable. `ViewerServer((asset, ...), Path('viewer/dist')).start()` returns a session-authorized URL; always call `close()` when the host exits.

`GET sessions.json` lists catalog descriptors; `GET launch/<index>.json` creates a managed session. These routes are relative to the capability URL. `frame.html?asset=<index>` hosts one renderer; `index.html` hosts two. Do not invent filesystem URLs or expose an unrestricted file handler.

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
