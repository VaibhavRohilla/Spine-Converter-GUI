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
