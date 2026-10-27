# Restricted B3 binary test vector

`hierarchy_4_2_43.hex` is hand-authored from the exact official
`@esotericsoftware/spine-core@4.2.43/dist/SkeletonBinary.js` reader contract.
It is NOT an authentic Spine Editor export and is not evidence for animation
conversion qualification. The vector was authored independently of the FNX
encoder. It contains a zero hash, version string, bounds (0,0,64,32), reference
scale 100, no nonessential fields, no string-table entries, one root bone
(rotation 10, x 2, y -3, scales 1, shears 0, length 5, normal inheritance,
skinRequired false), and nine empty record collections.

The independent official reader check is reproducible with:

```
node scripts/verify_binary_reference.mjs /path/to/spine-core-4.2.43/package /path/to/input.skel
```

This verifies parsing and hierarchy data only; it does not render or certify
runtime animation playback. Unsupported collections are rejected by FNX.

## Animated profile fixtures (2026-10-27)

`animated_region_4_2_43.json`, `animated_mesh_4_2_43.json`, and
`animated_ik_4_2_43.json` are independently specified test documents, **not
exports from the Spine editor**. Their version declares the intended input
schema; no authentic export was relabeled. The atlas is a hand-authored 64×32
region; bundle tests create a corresponding white PNG.

- Region: hierarchy, setup dark color, region, rotate/translate/scale/shear,
  linear/stepped/per-channel Bézier, RGBA animation.
- Mesh: weighted quadrilateral, alternate linked skin, inherited deform with a
  Bézier curve, positive and negative draw-order offsets, two slots.
- IK: one-bone setup IK driven by animated target translation. This is **not**
  evidence for two-bone IK, animated constraint parameters, path/transform
  constraints, or physics.

The independent hand-specified animated wire vector lives in
`test_independent_animated_wire_vector`; it does not call FNX's writer. It covers
region/slot/default-skin parsing and a linear rotate timeline. It is not an
independent decoder reference for meshes, linked meshes, deform or IK.

Generated `.skel` evidence lives in `docs/evidence/B3_binary`; checksums and
source provenance are in `qualification.json`. These files are **not** added
to the production viewer's approved binary manifest. Reproduce encoder checks:

```sh
.venv/bin/python scripts/qualify_b3_binary.py /tmp/new-b3-evidence
```
