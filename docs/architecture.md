# B1 architecture

`AssetSource` is the bounded, read-only folder/ZIP adapter. `InspectionService` sequences discovery, typed classification, JSON and atlas parsing, version recognition, conservative dependency resolution, and manifest construction. `models.py` defines immutable application-facing contracts; `protocols.py` captures service seams. `versions.py` separates recognition and feature capability from migration availability. The migration registry remains explicit and empty until executable, tested transformers exist. The CLI is a presentation adapter over `InspectionService`.

Inspection does not decode texture pixels, fully decode binary skeletons, certify runtime behavior, or convert assets. ZIP contents are streamed/read in-place and never extracted. `SourceLimits` and `InspectionConfig` provide explicit resource limits that callers can configure.
