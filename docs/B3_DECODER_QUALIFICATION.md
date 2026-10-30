# B3 exact 4.2.22 decoder and encoder qualification

This report records the evidence-backed restricted profile frozen in
[B3_REPORT.md](B3_REPORT.md). The prior blocker findings have been corrected;
they are not the current release decision.

## Provenance and identity

Powerup Essentials JSON, binary, atlas, and PNG come from pinned official
`spine-runtimes` commit
`8bca84f46e00d1d0d29ab0dc2406bef3b1248e17`. The committed provenance manifest
contains URLs, sizes and SHA-256 values. The JSON declares Spine `4.2.22`, as
does the binary. Its Base64 editor hash decodes to the exact eight binary header
bytes `48 c2 99 58 a4 4b 83 0f`. No marker was rewritten. The official JSON
rounds one skeleton bound differently from the binary; each direction is
therefore compared to its own authentic source representation.

## Decoder and encoder

The test-only `scripts/compare_binary42.mts` uses the pinned
`@esotericsoftware/spine-core@4.2.43` reader. Binary decode comparison derives
expected semantics directly from authentic binary bytes and compares them with
the same bytes decoded by FNX and loaded through official `SkeletonJson`.
Encoder comparison loads unchanged official JSON through `SkeletonJson`, loads
FNX-generated binary through `SkeletonBinary`, then compares the typed runtime
models. It compares hierarchy, setup transforms, inheritance, slots, skins,
region attachment mappings/transforms/UVs/offsets, animation names and
durations, timeline owners/types, key times/values and evaluated Bézier tables.

| Direction | Numeric values | Exact values | Maximum numeric error | Tolerance |
|---|---:|---:|---:|---|
| Authentic binary → FNX decode → official runtime | 2,180 | 207 | 0 | `1e-6 + 2e-6 * abs(reference)` |
| Unchanged official JSON → FNX encode → official runtime | 2,180 | 207 | `7.63e-6` | `1e-6 + 2e-6 * abs(reference)` |

The authentic Powerup binary contains 17 bones, 13 slots, one default skin, 13
regions, one `bounce` animation, 49 timelines and 182 keyframes. It exercises
rotation, translation, scale, shear, slot RGBA and linear, stepped and Bézier
interpolation. It contains no mesh, deform frames, constraints or events.

The pose harness compares bone world matrices, slot state, region world
vertices, skin selection and animation evaluation. It samples a uniform grid,
keyframe boundaries, adjacent times and segment midpoints.

| Direction | Pose samples | Numeric pose comparisons | Maximum absolute error | Tolerance |
|---|---:|---:|---:|---|
| Authentic binary → FNX decoded JSON | 162 | 41,797 | 0 | `3e-4 + 2e-6 * abs(reference)` |
| Unchanged official JSON → FNX generated binary | 164 | 42,313 | `0.000159` | `3e-4 + 2e-6 * abs(reference)` |

Seven deliberate corruptions remain detected: hierarchy parent, setup
transform, region width, slot color, keyframe time, keyframe value and curve.
The test mutates curve controls and verifies that evaluated runtime behavior
changes and comparison rejects it.

## Bézier guarantee boundary

The official runtime exposes evaluated interpolation tables. It does not expose
the original serialized control handles. FNX's reader consumes serialized
handles, but using that same reader as the oracle would not independently prove
handle identity. No second general decoder was created for this claim.

The release therefore qualifies evaluated interpolation and representative
poses only. `raw_bezier_handle_identity_qualified` is false in the support
contract. No bit-exact serialized-handle preservation promise is made, and no
qualified operation requires that guarantee.

## Workflow and restrictions

The same exact 4.2.22 profile is exercised through public `BinaryCodecRegistry`,
`SkeletonConverter`, `BundleService`, and installed `spine-forge bundle convert`
commands. The installed checks cover folder and ZIP sources in both directions,
atlas/PNG associations, final reinspection, texture hashes, deterministic
publication, atomic output, and source immutability. Unqualified profiles reject
mesh/deform and other features outside the recorded subset. Experimental
execution still requires explicit opt-in.

4.2.43 remains its separately implemented experimental profile. No migration
edge between 4.2.22 and 4.2.43 was added. B2 migration routes and B4's
approved-binary-only admission policy are unchanged. The freeze does not
qualify other attachments, constraints, events/draw-order, separate-axis
bone timelines, slot attachment timelines, other slot-color kinds, slot-color
Bézier channels, unverified bone extensions/inheritance, visual fidelity, or raw
Bézier handle identity.

Reproduce the full local and installed evidence:

```sh
./.venv/bin/python scripts/qualify_authentic_binary.py /tmp/b3-authentic-run
./.venv/bin/python -m build
./.venv/bin/python -m venv /tmp/b3-wheel-venv
/tmp/b3-wheel-venv/bin/python -m pip install --no-deps dist/fnx_spine_forge-0.2.0-py3-none-any.whl
/tmp/b3-wheel-venv/bin/python scripts/verify_b3_installed.py /tmp/b3-wheel-run
bash scripts/verify_b4.sh
```

The final metrics, hashes and installed command/API outputs are retained in
[restricted profile evidence](evidence/B3_restricted_4222/).
