# B3 final targeted decoder qualification — 2026-10-28

**B3 PARTIAL — BINARY QUALIFICATION BLOCKED. No restricted freeze.**

Authentic animated decoding now has independent evidence. A useful qualified
public binary workflow still does not: unchanged official JSON encoding and
binary bundle publication fail the concrete gates below. No B5 work was started.
The frozen JSON bundle subsystem and B4 production trust policy retain their
previous status. This is not full-format Spine 4.2 compatibility.

## Release blockers observed through the real system

1. The unchanged official Powerup JSON declares `4.2.22` and uses the editor's
   base64 hash `SMKZWKRLgw8`. The existing writer rejects it with `BINARY_HASH`:
   its contract accepts only an explicit eight-byte hexadecimal representation.
   The source was not rewritten to make this test pass. Its nonessential export
   metadata also lacks the explicit `fps`, bone color and visibility required by
   the existing writer; that remains an additional contract gap, not an executed
   second failure after the first rejection.
2. Authentic binary → custom decoder succeeds. Passing that decoded document
   through `BundleService`, however, fails with
   `Unknown semantic bone fields for 4.2.22: visible`. The codec's internal B2
   validation projection excludes editor visibility, whereas the actual bundle
   path passes the retained field to B2. Experimental API and installed CLI
   reproduce this integration defect and publish no output.
3. The qualification registry contains no evidence-backed same-version animated
   binary bundle profile. Default API/CLI admission remains `BINARY_UNQUALIFIED`.
   No feature category has been promoted to qualified mode in this pass.
4. The official runtime exposes evaluated Bézier tables, not the original
   serialized control handles. Tables and sampled interpolation match exactly;
   raw-handle independent verification remains absent. Bone icon/visibility and
   header/nonessential metadata are explicitly outside this runtime comparison.

These are concrete remaining defects/evidence gaps, not a requirement to buy a
Spine license or to qualify every advanced feature. This pass stops at that
release decision rather than changing the frozen B2 metadata model, writer
metadata policy or qualification contract as an unrelated hardening exercise.

## Exact source and implementation scope

Baseline: clean `3a5fb5214ff6d114ab56604283c6333a38c0a888`.

The existing B4 inventory contains five authenticated Spineboy binaries:
3.8.55, 4.0.31, 4.1.17, **4.2.22**, and 4.3.75-beta. Their local SHA256 values were
rechecked against the existing provenance manifest. The 4.2 mesh/path/physics
feature infrastructure previously contained JSON exports, not corresponding
binary files. No Spine executable was found on PATH or in the inspected
`/Applications` listing; no licensed-editor export was generated or claimed.

The new fixture set contains unchanged official Powerup Essentials, Spineboy
Essentials, Coin Pro and Vine Pro JSON/binary exports, plus Powerup atlas/PNG and
the runtime license, from pinned official repository commit
[`8bca84f46e00d1d0d29ab0dc2406bef3b1248e17`](https://github.com/EsotericSoftware/spine-runtimes/tree/8bca84f46e00d1d0d29ab0dc2406bef3b1248e17/examples).
Every URL, byte count and SHA256 is in
[fixture provenance](../tests/fixtures/binary/official42/provenance.json).
All four new binaries declare **4.2.22**. No binary marker was modified.

Powerup binary SHA256:
`0e739e50f3e44e8bacd481649a8e9deee3ed3722c4813ba673f1a862dbc65d0b`.
Its JSON editor hash decodes to the same eight header bytes. This supports common
content identity, but not identical export precision/settings: binary bounds Y
is `119.40846252441406`, JSON is `119.41`. The strict reference comparison rejects
that difference. The JSON is retained as provenance and as an unchanged encoder
input; it is **not** used as a supposedly exact expected decoder result.

The registry now admits **exact 4.2.22 experimentally**, using the existing
`BinaryProfile`, reader and writer. Its exact bone semantic schema is recognized
for validation. No migration edge, B2 qualification record, atlas route, B4
approval identity, or broad 4.2 family admission was added. Tests reject both
directions between 4.2.22 and existing migration patches. The original 4.2.43
writer output is unchanged. Capability text distinguishes the new decoder proof
from the still-unqualified encoder and release state; qualification booleans
remain false. Existing feature lists describe implementation, not certification.

## Independent comparison and actual coverage

The test-only [typed comparator](../scripts/compare_binary42.mts) builds its
expected model directly from **original authentic binary bytes → official
`SkeletonBinary`**, independently of FNX output. The candidate is **the same
bytes → FNX decoder → official `SkeletonJson`**. The model has explicit typed
bone, slot, region, skin and timeline records. Unsupported attachments,
constraints, events, sequences and timeline classes are rejected by the
comparator, never silently omitted.

Compared fields include hierarchy/names, setup transforms/inheritance, bone and
slot colors, slot bone/attachment/blend/visibility, skin/attachment mappings,
region names/paths/transforms/dimensions/colors/UVs/offsets, animation
names/durations, timeline owners/types, all actual frame times/values, and all
runtime Bézier interpolation-table values. Names, references, counts and flags
use exact equality. Numeric semantics use `1e-6 + 2e-6 * abs(reference)` for
float32 representation; observed maximum error is **zero**. The separate pose
harness retains its previous `3e-4 + 2e-6 * abs(reference)` tolerance and also
observes **zero** error for Powerup.

Powerup exercises 17 bones, 13 slots, one default skin, 13 regions, one animated
`bounce` sequence of 1.4000000953674316 seconds, and **182 keyframes**:
13 rotate, 13 translate, 11 scale, 2 shear and 10 RGBA timelines (**49 total**).
Rotate, translate, scale and shear all contain nontrivial values. Bone curves
include linear, stepped and Bézier; slot RGBA exercises linear/stepped only.
There are no meshes, constraints, deform frames or events in this fixture.

- **2,180 numeric + 207 exact semantic leaves** compared; maximum error **0**.
- **42 pose samples, 10,837 numeric comparisons**; maximum error **0**.
- Seven deliberate corruptions are detected: parent, setup position, region
  width, slot color, keyframe time, keyframe value and Bézier data.
- Reencoding FNX-decoded Powerup data loads in the official binary reader and
  matches the original binary's independent runtime model. This is useful
  binary-derived-input evidence, **not independent authentic-JSON encoder proof**.

| Authentic binary | Bones / slots | Attachments | Constraints | Animations / keys | Mesh vertices / influences | Deform / event frames | FNX result |
|---|---:|---|---|---:|---:|---:|---|
| Powerup Essentials | 17 / 13 | 13 region | None | 1 / 182 | 0 / 0 | 0 / 0 | Independent restricted comparison passes |
| Spineboy Pro | 67 / 52 | 66 region, 12 mesh, 1 bounding box, 1 clipping | 7 IK, 8 transform | 11 / 1791 | 322 / 396 | 9 / 5 | Rejects transform constraints |
| Spineboy Essentials | 18 / 20 | 26 region, 1 bounding box | None | 8 / 744 | 0 / 0 | 0 / 5 | Rejects unsupported attachment |
| Coin Pro | 7 / 6 | 7 region, 1 clipping | None | 1 / 69 | 0 / 0 | 0 / 0 | Rejects unsupported attachment |
| Vine Pro | 18 / 2 | 1 mesh, 1 path | 1 path | 1 / 40 | 81 / 302 | 0 / 0 | Rejects path constraint |

The counts above are extracted by the official runtime. Advanced fixture
inventories do **not** imply FNX comparison success. Their independently
compared FNX values and numerical deviation are **not available**, not zero.
Per-fixture versions, hashes, skins, timeline-type counts, event definitions,
rejections and unverified fields are in [executed evidence](evidence/B3_decoder/qualification.json).
No authentic linked-mesh, mesh/deform or constraint decoder category is certified.

## Feature decision

| Feature | Decoder | Encoder | Runtime | Qualified |
|---|---|---|---|---|
| Hierarchy/setup | Authentic Powerup 4.2.22 values compared | Existing specified 4.2.43 fixtures; original official JSON rejected | Independent setup and poses pass for tested inputs | No: integration/profile gates open |
| Region attachments | 13 authentic regions; transforms/UVs/mappings compared | Existing specified region fixture; binary-derived Powerup input also loads | Region semantics and world vertices pass | No: restricted decoder evidence only |
| Bone timelines | Authentic rotate/translate/scale/shear, actual keys | Existing specified combined-channel fixtures | Timelines/durations and sampled animation pass | No; separate-axis categories remain unverified |
| Bézier curves | Runtime curve tables and sampled interpolation match | Existing specified bone/deform curves | Tested tables/poses pass | No: raw handles unverified; RGBA Bézier unexercised |
| Mesh/deform | No authentic custom-decoder comparison | Specified weighted/linked/deform fixture only | Existing generated-fixture poses pass | No |
| Constraints | No authentic custom-decoder comparison | Specified one-bone IK setup only | Existing generated IK poses pass | No |

Implemented but unverified categories remain those documented in
[B3_BINARY_REPORT.md](B3_BINARY_REPORT.md): separate-axis bone timelines, slot
attachment timelines, RGBA Bézier, unweighted mesh, broader IK setup and all
mesh/deform authentic decoding. Unsupported categories still fail closed:
bounding box/clipping/path/point attachments, transform/path/physics constraints,
constraint timelines, sequences, events and unsupported slot timelines.

## Regression, installed package and release boundary

`bash scripts/verify_b4.sh` passed: **507 Python tests**, **146 browser tests**,
Ruff, strict mypy (61 files), TypeScript including the new strict comparator,
viewer lint/build, Python wheel/sdist, and `git diff --check`.
The sandboxed first run failed only at a forbidden loopback bind; the authorized
run passed. No extended B4 soak was run because viewer lifecycle/memory ownership
was unchanged. Regenerated incidental B4 evidence was restored.

The original three independently specified encoder fixtures retain **168 samples,
6,456 numerical comparisons**, maximum error below **7.22e-7**, and byte-identical
output. Their evidence validates **encoding/runtime evaluation**, not authentic
decoding. Existing security, invalid input, oversized input, packaging, rollback
and B4 trust-policy regression tests remain green. New tests cover authentic
truncation/size rejection, advanced-content rejection and semantic mutations.

An isolated installed wheel repeats authentic decoding and the official semantic
and pose comparisons. Installed API/CLI also confirm the existing experimental
4.2.43 JSON → binary ZIP → JSON folder/ZIP workflow, deterministic ZIP/binary
output, inspection, atlas dependency resolution, unchanged PNG SHA256, source
immutability and no output on rejection. The binary ZIP bytes match the retained
independently evaluated region fixture. The **authentic qualified 4.2.22 workflow
fails**, as recorded above; these 4.2.43 checks are not substituted for it.

Evidence: [full gate](evidence/B3_decoder/verification.log),
[authentic tests](evidence/B3_decoder/authentic-tests.log),
[encoder recheck](evidence/B3_decoder/encoder-recheck.json),
[installed decoder](evidence/B3_decoder/installed-decoder.json), and
[installed API/CLI](evidence/B3_decoder/installed-wheel.json).

Reproduce from the checkout or installed-wheel Python:

```sh
python scripts/qualify_authentic_binary.py /tmp/new-authentic-evidence
python scripts/qualify_b3_binary.py /tmp/new-encoder-evidence
# Run this one with the isolated wheel interpreter:
/path/to/wheel-venv/bin/python scripts/verify_b3_installed.py /tmp/new-wheel-evidence
bash scripts/verify_b4.sh
```

B4 still admits only its existing approved identities. Neither these newly
acquired official binaries nor FNX-generated output was registered as trusted.
The isolated official-runtime qualification tools are not production viewer
admission or a claim of OS sandboxing. B2's cross-version support matrix and
qualification evidence are unchanged. No freeze or B5 transition is authorized
by the evidence produced here.
