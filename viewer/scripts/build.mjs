import { build } from "esbuild";
import { mkdir, copyFile, rm, readFile } from "node:fs/promises";
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
const manifest = JSON.parse(
  await readFile("src/fnx_spine_forge/viewer/runtime_manifest.json", "utf8"),
);
for (const { family: dottedFamily } of manifest.runtimes.filter(
  (r) => r.embeddedImplemented && r.family !== "3.8",
)) {
  const family = dottedFamily.replace(".", "");
  await copyFile(
    `node_modules/spine${family}/LICENSE`,
    `viewer/dist/LICENSE-spine${family}.txt`,
  );
}
await copyFile("viewer/.runtime/LICENSE", "viewer/dist/LICENSE-spine38.txt");

await copyFile(
  "src/fnx_spine_forge/viewer/runtime_manifest.json",
  "viewer/dist/runtime-manifest.json",
);
