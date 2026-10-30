# B4 dependency and fixture licensing

Runtime source: [official Esoteric Software repository](https://github.com/EsotericSoftware/spine-runtimes).
The full notices for each integrated family are preserved under `docs/licenses/` and
copied into every production viewer build. The 3.8 namespace distribution is fetched
from an immutable official commit, checksum checked, and receives only an ESM export
wrapper. Skeleton bytes and version metadata are never rewritten by the viewer.

The [Spine Runtimes License](https://github.com/EsotericSoftware/spine-runtimes/blob/4.3/LICENSE)
and [Editor License](https://esotericsoftware.com/spine-editor-license) govern integration
and redistribution. This engineering tool is supplied under the runtime agreement's
user-license condition: users integrating or using the runtimes must obtain their own
Spine Editor license. Include all applicable notices with redistributions. This repository
does not establish an organization's commercial license ownership or grant a Spine license.

Official example assets are authentic exported examples from the same repository.
Fixture provenance manifests contain immutable source URLs and SHA-256 hashes; each
fixture directory retains the applicable official license. They are evaluation/reference
fixtures, not authored FNX content. Production Golden Ingot and merged_multi inputs came
from the user's existing authorized workspace; provenance is recorded separately and
these private assets must not be republished outside authorized project distribution.

Modern npm dependencies and transitive core runtimes are pinned by `package-lock.json`.
Zod is MIT; esbuild, Playwright, TypeScript, ESLint, Prettier and pngjs retain their package
licenses. Pillow is an optional Python verification dependency. PySide6 is used only in
the optional embedding smoke harness; its LGPL/GPL/commercial licensing is separate from
Spine. It is not a dependency of the converter or the viewer core.
