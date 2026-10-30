# FNX Spine Forge — B3 release report

**Decision: B3 CLOSED / FROZEN — RESTRICTED 4.2.22 BINARY PROFILE.**

This freeze covers one exact editor export patch, **Spine 4.2.22**, and only
the feature subset exercised by the authentic Powerup Essentials export. The
independent runtime used for comparisons is the pinned
`@esotericsoftware/spine-core@4.2.43` reader; that runtime package version does
not change the 4.2.22 source/export identity. No 4.2.22 → 4.2.43 migration or
general 4.2.x support is advertised. The separately implemented 4.2.43 codec
remains experimental.

The release evidence is in
[qualification.json](evidence/B3_restricted_4222/qualification.json),
[encoder-runtime.json](evidence/B3_restricted_4222/encoder-runtime.json),
[installed-wheel.json](evidence/B3_restricted_4222/installed-wheel.json),
and [verification.json](evidence/B3_restricted_4222/verification.json).
The earlier implementation checkpoints remain historical; current decoder,
encoder and Bézier evidence is detailed in
[B3_DECODER_QUALIFICATION.md](B3_DECODER_QUALIFICATION.md).

## Qualified profile

| Feature category | Qualified 4.2.22 subset |
|---|---|
| Hierarchy and setup | Names, parent links, setup transforms and default inheritance |
| Bone and slot state | Runtime setup fields present in Powerup; nonessential editor fields are preserved but are not runtime semantics |
| Attachments and skins | Region attachments and the exercised default skin |
| Bone timelines | Rotation, translation, scale and shear; the combined-channel forms exercised by Powerup |
| Slot timelines | RGBA color timelines with linear and stepped interpolation |
| Bézier | Evaluated interpolation semantics and resulting poses; raw serialized control-handle identity is explicitly unqualified |
| Bundles | Powerup skeleton/atlas/PNG association, source immutability, texture-byte identity, deterministic ZIP, reinspection and atomic publication |

The registry admits only semantic inputs whose detected features fit that
profile. Unknown semantic fields, unsupported attachments/timelines, meshes,
deform, constraints, events/draw-order semantics, unverified inheritance or
bone extensions, separate-axis timelines, slot attachment timelines, other
slot-color timeline kinds, and slot-color Bézier channels fail closed in
qualified mode. Experimental execution remains available only by the existing
explicit opt-in. Exact serialized Bézier-handle preservation is not a
qualified operation; the contract records
`raw_bezier_handle_identity_qualified: false`.

## Hash and nonessential fields

The unchanged official Powerup JSON is pinned at
`8bca84f46e00d1d0d29ab0dc2406bef3b1248e17`; its recorded SHA-256 is
`6ff51b2fa2b47e339399391a11f1523896defbd7e62a7cb9f69f8021315e1785`. Its hash
`SMKZWKRLgw8` decodes to `48c29958a44b830f`, exactly the first eight bytes of
the independently pinned official Powerup binary. For exact 4.2.22, the writer
accepts canonical 8-byte Base64 and the established 16-hex-digit form. The
4.2.43 experimental writer retains its hexadecimal contract. Invalid alphabet,
padding, decoded size and unsupported-version encodings reject; values are
never truncated or guessed. The source JSON and metadata mappings are not
mutated.

The pinned 4.2 reader defines omitted nonessential defaults: FPS `0`, bone
color `00000000`, missing bone icon, bone visibility `false`, and slot
visibility `true`. Those defaults are applied only for exact 4.2.22. Missing
optional metadata is accepted, and present metadata is validated and preserved.
The exact 4.2.43 metadata requirements remain unchanged.

Decoded 4.2.22 bone `visible` is nonessential editor metadata. The lossless
source document retains it, while B2 runtime validation receives the shared,
version-aware semantic projection. Unknown semantic fields continue to reject;
the B2 behavior for every other patch remains unchanged.

## Independent comparisons

The unchanged binary decodes through FNX and is compared to the pinned official
binary reader. Results: **2,180 numeric values**, **207 exact semantic values**,
maximum numeric error **0**, using `1e-6 + 2e-6 * abs(reference)`. Runtime pose
comparison of authentic binary versus FNX-decoded JSON passed **162 samples**
and **41,797 numeric comparisons**, maximum error **0**, within
`3e-4 + 2e-6 * abs(reference)`. The denser sample set includes uniform times,
keyframe boundaries, adjacent times, and segment midpoints.

The encoder uses the **unchanged official JSON** as its reference. Generated
binary loaded by the official reader matched setup, attachments, skins,
animation keys and evaluated curves: **2,180 numeric values**, **207 exact
values**, maximum error **7.63e-6**, within the same float comparison tolerance.
The independent pose check passed **164 samples** and **42,313 numeric
comparisons**, maximum error **0.000159**, within pose tolerance. The JSON export
rounds a skeleton bound that differs from the separately exported binary; the
encoder comparison therefore uses the JSON itself as reference and does not
rewrite its bounds or claim identical export settings.

The runtime exposes evaluated interpolation tables, not original serialized
Bézier control handles. Table/pose behavior is qualified and deliberate curve
corruption is detected. Raw handle identity is not claimed and is not required
by any qualified workflow.

## Public workflow evidence

Both directions passed through public `BundleService`, installed Python API,
and installed `spine-forge bundle convert` commands, using folder and ZIP
inputs:

- Authentic `.skel` → FNX decoder → validated 4.2.22 JSON bundle.
- Unchanged official 4.2.22 JSON → FNX encoder → official-reader-accepted binary bundle.
- Atlas and PNG references resolve; final bundles re-inspect successfully.
- Texture SHA-256 is preserved, output is deterministic, and source files remain
  unchanged. Publication remains atomic and no-overwrite.
- The installed wheel imports from its isolated site-packages directory and
  its binary module bytes match the tested checkout.

The official comparison harness also verifies source provenance and catches
deliberately modified setup, attachment, slot, keyframe, value and curve data.
Malformed hash/metadata, unknown semantic fields, unqualified advanced features,
transactional rollback, and existing 4.2.43 byte-identity fixtures are covered
by the passing Python suite.

## Release and security boundary

Supported export patches: **4.2.22 qualified restricted profile** and
**4.2.43 experimental implementation**. No other patch is admitted by B3.
B4 production viewing remains approved-binary-only. Its trusted manifest and
viewer policy files are byte-identical to the baseline; no B3-generated binary
was added to B4 admission. The B4 lifecycle soak was not rerun because no
runtime-lifecycle code changed.

Final verification on the implementation candidate: **522 Python tests**,
**146 browser tests**, Ruff, strict mypy, TypeScript typecheck/lint/build,
wheel/sdist build, isolated installed-wheel API/CLI checks, and
`git diff --check` passed. The complete run was repeated after the typed policy
cleanup commit `7c620e4837bcda68713e7259cc7ba3278bcbcdca`; it again passed all
522 Python and 146 browser tests, Ruff, strict mypy, builds, and viewer checks.
The detailed B3 evidence and package hashes remain in
`evidence/B3_restricted_4222/verification.json`.

Qualification implementation commit SHA: `f0094d83758673ad6a8edc19b5c725456253b059`.
Typed policy cleanup commit SHA: `7c620e4837bcda68713e7259cc7ba3278bcbcdca`.
No B5 implementation is included in this freeze.
