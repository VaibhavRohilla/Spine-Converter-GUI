// Restore only immutable, recorded official exports. Production fixtures are local
// authorized artifacts and are deliberately not downloaded from another source.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
for (const [manifest, root] of [
  ["viewer/fixtures/provenance.json", "viewer/fixtures"],
  ["viewer/fixtures/features/provenance.json", "viewer/fixtures/features"],
  ["viewer/fixtures/physics/provenance.json", "viewer/fixtures/physics"],
]) {
  const records = JSON.parse(await readFile(manifest, "utf8"));
  for (const record of records) {
    if (
      !/^https:\/\/raw\.githubusercontent\.com\/EsotericSoftware\/spine-runtimes\/[a-f0-9]{40}\//.test(
        record.url,
      )
    )
      throw Error("Fixture URL must pin the official source commit.");
    const directory = `${root}/${record.fixture ? record.family + "-" + record.fixture : record.family}`;
    await mkdir(directory, { recursive: true });
    const response = await fetch(record.url);
    if (!response.ok) throw Error(`Fixture fetch ${response.status}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (createHash("sha256").update(bytes).digest("hex") !== record.sha256)
      throw Error(`Fixture checksum mismatch: ${record.url}`);
    await writeFile(`${directory}/${record.file ?? record.name}`, bytes);
  }
}
