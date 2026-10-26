import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
const revision = "8b4844bd4b193ba9e54487ed397a777993cbad56";
const hashes = {
  "spine-webgl.js":
    "4b108bad314c152bf0ff7a7f56fce5c98073f05a2bfa53e880d6c24b6f7c3aa5",
  "spine-webgl.d.ts":
    "2368fe614fe5983a625cf3cf2d317f1ed3712a588de988f9556b790f6f10f4bc",
  LICENSE: "6142ee6cc2c03d3a918793e4750ae772bd3755c534d4a35e559e301acf51ec39",
};
await mkdir("viewer/.runtime", { recursive: true });
for (const file of ["spine-webgl.js", "spine-webgl.d.ts", "LICENSE"]) {
  const path = file === "LICENSE" ? "LICENSE" : `spine-ts/build/${file}`;
  const res = await fetch(
    `https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/${revision}/${path}`,
  );
  if (!res.ok) throw Error(`Official runtime fetch failed: ${res.status}`);
  const text = await res.text();
  if (createHash("sha256").update(text).digest("hex") !== hashes[file])
    throw Error(`Official runtime checksum differs: ${file}`);
  await writeFile(
    `viewer/.runtime/${file}`,
    text + (file === "LICENSE" ? "" : "\nexport { spine };\n"),
  );
  console.log(file, createHash("sha256").update(text).digest("hex"));
}
