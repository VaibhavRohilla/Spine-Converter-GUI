# B3 binary typing and contract hardening — 2026-10-28

This is a focused cleanup of the experimental binary implementation committed
at `993cff2f573e29bfbcfcf740895add5370eb944c`. It does not promote B3 to a
production-qualified freeze or change the supported wire features.

## Changes

- Added an immutable, slotted `BinaryProfile`. Capability serialization derives
  feature lists from this typed schema rather than embedding a second list in
  `to_dict`. Bone timeline parsing uses the same enum/profile as capability
  discovery. Attachment and slot categories use enums; other finite categories
  use `Literal` contracts.
- Capability input/output formats now reflect enabled directions. A decoder-only
  record advertises binary input and JSON output; a fully disabled record
  advertises neither. Altering a registered profile still fails construction.
- Replaced unrestricted curve strings/flat control arrays in bone timeline
  records with `Literal["stepped"] | BezierCurve | None`. Each Bézier channel is
  a fixed tuple of four finite, validated controls. Domain records are frozen
  and slotted; JSON remains the explicitly typed, validated boundary format.
- Declared rejection helpers as `Never`, removing unreachable assertion code.
- Replaced repeated linear string-table searches with an index dictionary while
  retaining deterministic insertion order and exactly the same encoded bytes.
- Made aggregate item and nesting limits explicit validated `BinaryLimits`
  fields: `max_total_items` and `max_depth`. They can be configured independently
  of per-collection limits. The default profile retains the previous defaults.
- Rejected uppercase timeline names previously admitted through `.upper()`;
  accepting them could disagree with official JSON interpretation. Rejected
  negative indices rather than accidentally using Python reverse indexing.
- Renamed `BINARY_HIERARCHY_VERSION` to `BINARY_EXPORT_VERSION` and updated every
  repository consumer. No deprecated alias or backward-compatibility shim was
  introduced. External Python imports of the removed name must be updated.
  `BinaryCapability` now requires its explicit `profile` field.

Format tags, exact export versions, and official schema defaults remain explicit
constants. Making those arbitrary or inferred would break deterministic wire
compatibility. No competing migration engine or general dynamic field decoder
was introduced. Existing B1/B2 conversion features are intentional functionality,
not deprecated scaffolding; they were preserved.

## Verification

`bash scripts/verify_b4.sh` passed: **494 Python tests**, **146 browser tests**,
Ruff, strict mypy (**61 files**), TypeScript typecheck/lint/build, Python wheel and
sdist builds, and whitespace checks. Strict mypy retains the existing explicit,
implicit-expression and unimported-`Any` prohibitions; no type ignores were added.

Five added regression cases cover directional formats, profile forgery,
case-sensitive timeline admission, configurable complexity bounds and negative
references. Existing binary corruption, bundle transaction and B4 policy tests
continue to pass.

The qualification driver evaluated the three specified JSON fixtures against
the official runtime: **168 pose samples**, **6,456 numerical comparisons**,
maximum absolute difference below **7.22e-7**. All three generated binaries remain
byte-identical to the preceding checkpoint. The installed wheel matches the
checkout modules, exposes the updated capability contract, and exports a binary
ZIP whose skeleton matches the independently evaluated fixture and whose PNG
matches the source bytes.

Evidence: [B3_binary_hardening](evidence/B3_binary_hardening/qualification.json),
[full gate log](evidence/B3_binary_hardening/verification.log), and
[installed wheel](evidence/B3_binary_hardening/installed-wheel.json).
The earlier evidence remains unchanged. Browser tests regenerate B4 evidence;
those incidental files were restored to their frozen originals after verification.

## Remaining qualification boundary

The architecture and typing improvements do not supply authentic animated
decoder evidence, expand constraint-heavy acceptance coverage, or prove every
implemented feature independently. **B3 PARTIAL — BINARY UNQUALIFIED** remains
accurate. B2 qualifications and B4 approved-binary admission are unchanged.
There is no defensible blanket “10/10” or production-complete claim.
