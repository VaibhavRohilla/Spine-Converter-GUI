# Version and qualification registries

`VersionRegistry` recognizes Spine families 3.5–3.8 and 4.0–4.3 for inspection.
Recognition does not establish writer support.

`conversion/registry.py` owns exact-patch migration edges and their writer kinds.
Writers call `require_route()` to admit a requested source/target pair. Bone-mode
field selection and runtime/atlas operational policies also have explicit owners
in that registry. Registering an edge does not qualify its features.

`ConversionQualificationRegistry` loads exact complete-path records from the
packaged `qualification_evidence.json`. Feature coverage, fixture identities,
SHA-256 values and evidence references are data, not route-specific conditionals
in the qualification service. Malformed evidence fails closed. Unrecorded paths
remain unqualified, including compositions of individually implemented edges.

`ConversionPlanner.plan()` consumes source features and returns typed
qualification. Without inspected source features it cannot claim qualified
executability. `structural_plan()` and `candidate_routes()` expose implementation
connectivity for explicit experimental use.

Candidate routes are obtained from `ConversionPlanner.candidate_routes()`;
qualification comes from the packaged evidence registry rather than duplicated
counts in application code. Only the seven documented direct 3.8.99
hierarchy/setup-only records qualify semantically. Route inventory is not a
production compatibility matrix. Authored bone
inheritance, bone extensions, attachments, animation and full asset sets remain
outside qualified execution. See [B2_REPORT.md](B2_REPORT.md) for exact paths,
restrictions and executed checks. Runtime and visual certification are absent.
