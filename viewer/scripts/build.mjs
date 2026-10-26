import { build } from "esbuild";
import { mkdir, copyFile, rm } from "node:fs/promises";
// Generated output only: remove obsolete hashed chunks before reproducible build.
await rm("viewer/dist", { recursive: true, force: true });
await mkdir("viewer/dist", { recursive: true });
await build({
  entryPoints: [
    "viewer/src/frame.ts",
    "viewer/src/host.ts",
    "viewer/src/component.ts",
  ],
  bundle: true,
  splitting: true,
  format: "esm",
  outdir: "viewer/dist",
  sourcemap: true,
  metafile: true,
});
for (const file of ["index.html", "frame.html", "viewer.css"])
  await copyFile(`viewer/${file}`, `viewer/dist/${file}`);
for (const family of ["40", "41", "42", "43"])
  await copyFile(
    `node_modules/spine${family}/LICENSE`,
    `viewer/dist/LICENSE-spine${family}.txt`,
  );
await copyFile("viewer/.runtime/LICENSE", "viewer/dist/LICENSE-spine38.txt");

await copyFile(
  "src/fnx_spine_forge/viewer/runtime_manifest.json",
  "viewer/dist/runtime-manifest.json",
);
