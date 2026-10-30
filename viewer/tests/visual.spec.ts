import { test, expect, type Browser, type Page } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { PNG } from "pngjs";
import { z } from "zod";
import { server } from "./server";
import { assetsSchema } from "../src/protocol";
import { pixelMetrics } from "../src/comparison";
import type { Capture } from "../src/contracts";

const directory = "docs/evidence/B4/candidate-references";
const output = "docs/evidence/B4/visual-comparisons";
const generate = process.env.B4_CAPTURE_CANDIDATES === "1";
let transport: Awaited<ReturnType<typeof server>>;
test.beforeAll(async () => {
  transport = await server();
  await mkdir(directory, { recursive: true });
  await mkdir(output, { recursive: true });
});
test.afterAll(async () => {
  if (transport) await transport.close();
});
const digest = (bytes: Buffer) =>
  createHash("sha256").update(bytes).digest("hex");
function compare(
  a: Buffer,
  b: Buffer,
  channelTolerance = toleranceConfig.default.channel,
) {
  const left = PNG.sync.read(a),
    right = PNG.sync.read(b);
  expect([right.width, right.height]).toEqual([left.width, left.height]);
  const metrics = pixelMetrics(
    new Uint8ClampedArray(left.data),
    new Uint8ClampedArray(right.data),
    channelTolerance,
  );
  const diff = new PNG({ width: left.width, height: left.height });
  const overlay = new PNG({ width: left.width, height: left.height });
  for (let i = 0; i < left.data.length; i += 4) {
    const alpha = Math.abs(left.data[i + 3]! - right.data[i + 3]!);
    for (let c = 0; c < 3; c++) {
      diff.data[i + c] = Math.max(
        alpha,
        Math.abs(left.data[i + c]! - right.data[i + c]!),
      );
      overlay.data[i + c] = Math.round(
        (left.data[i + c]! + right.data[i + c]!) / 2,
      );
    }
    diff.data[i + 3] = 255;
    overlay.data[i + 3] = 255;
  }
  return {
    metrics,
    diff: PNG.sync.write(diff),
    overlay: PNG.sync.write(overlay),
  };
}
async function capture(page: Page, index: number): Promise<Capture> {
  await page.goto(`${transport.url}frame.html?index=${index}`);
  await page.waitForFunction(() => window.fnxViewer?.state === "READY");
  return page.evaluate(async () => {
    const v = window.fnxViewer;
    v.setViewport({ width: 640, height: 640, pixelRatio: 1 });
    const animation =
      v.info().animations.find((a) => a.name === "walk") ??
      v.info().animations.find((a) => a.duration > 0);
    if (animation) {
      v.setAnimation(animation.name, 0);
      await v.seek(animation.duration * 0.25);
    }
    return v.captureFrame();
  });
}
const metadataSchema = z.object({
  status: z.literal("CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED"),
  sha256: z.string(),
  normalization: z.string(),
  sources: z.string(),
});
// Same software backend and deterministic simulation: allow <=2 levels per channel,
// <=0.1% changed pixels and <=0.1 mean RGBA error. These are regression budgets,
// not an artistic acceptance criterion or a cross-GPU tolerance.
const toleranceSchema = z
  .object({
    channel: z.number().int().min(0).max(255),
    changedFraction: z.number().min(0).max(1),
    meanAbsoluteError: z.number().min(0).max(255),
    alphaMeanError: z.number().min(0).max(255),
    maximumChannelError: z.number().min(0).max(255),
  })
  .strict();
const toleranceConfig = z
  .object({
    default: toleranceSchema,
    fixtures: z.record(z.string(), toleranceSchema),
  })
  .strict()
  .parse(
    JSON.parse(readFileSync("viewer/tests/visual-tolerances.json", "utf8")),
  );
const tolerance = toleranceConfig.default;
async function qualifyCapture(
  page: Page,
  browser: Browser,
  frame: Capture,
  index: string | number,
): Promise<void> {
  const tolerance =
    toleranceConfig.fixtures[String(index)] ?? toleranceConfig.default;
  const bytes = Buffer.from(frame.png.split(",")[1]!, "base64");
  const assets = await page.evaluate(() => window.fnxViewer.assets);
  const normalization = JSON.stringify({
    camera: frame.camera,
    width: frame.width,
    height: frame.height,
    dpr: frame.dpr,
    background: frame.background,
    animation: frame.pose.animation,
    time: frame.pose.time,
    skin: frame.pose.skin,
    runtime: frame.pose.runtime,
    version: frame.pose.exportVersion,
  });
  const sources = JSON.stringify({
    original: assets.checksums,
    renderedSkeleton: assets.resourceHashes[assets.skeleton],
  });
  const path = `${directory}/${index}`;
  if (generate) {
    const graphics = await page.evaluate(() => {
      const gl = window.fnxViewer.canvas.getContext("webgl")!;
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      return {
        renderer: ext
          ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL))
          : String(gl.getParameter(gl.RENDERER)),
        version: String(gl.getParameter(gl.VERSION)),
      };
    });
    await writeFile(`${path}.png`, bytes);
    await writeFile(
      `${path}.json`,
      JSON.stringify(
        {
          status: "CANDIDATE_NOT_INDEPENDENTLY_ACCEPTED",
          createdAt: new Date().toISOString(),
          sha256: digest(bytes),
          normalization,
          sources,
          sourceSkeleton: assets.assetId,
          sourceVersion: assets.exportVersion,
          runtimeRevision: assets.runtimeRevision,
          animation: frame.pose.animation,
          timestamp: frame.pose.time,
          skin: frame.pose.skin,
          viewport: {
            width: frame.width,
            height: frame.height,
            dpr: frame.dpr,
          },
          camera: frame.camera,
          background: frame.background,
          alphaPolicy: "RGBA transparent; authored atlas PMA",
          browser: browser.version(),
          graphics,
          tolerance,
          provenance:
            "viewer/fixtures/provenance.json and features/physics provenance.json; index 11 private authorized converted asset, no conversion equivalence",
          acceptance: "UNVERIFIED",
          conversionEquivalence: "UNVERIFIED",
        },
        null,
        2,
      ),
    );
  } else {
    const reference = await readFile(`${path}.png`);
    const metadata = metadataSchema.parse(
      JSON.parse(await readFile(`${path}.json`, "utf8")),
    );
    expect(digest(reference)).toBe(metadata.sha256);
    expect(normalization).toBe(metadata.normalization);
    expect(sources).toBe(metadata.sources);
    const result = compare(reference, bytes, tolerance.channel);
    await writeFile(`${output}/${index}-diff.png`, result.diff);
    await writeFile(`${output}/${index}-overlay.png`, result.overlay);
    await writeFile(
      `${output}/${index}.json`,
      JSON.stringify(
        {
          status: "CANDIDATE_REGRESSION_ONLY",
          independentAcceptance: "UNVERIFIED",
          metrics: result.metrics,
          tolerance,
          referenceSha256: metadata.sha256,
          candidateSha256: digest(bytes),
        },
        null,
        2,
      ),
    );
    expect(result.metrics.changedFraction).toBeLessThanOrEqual(
      tolerance.changedFraction,
    );
    expect(result.metrics.meanAbsoluteError).toBeLessThanOrEqual(
      tolerance.meanAbsoluteError,
    );
    expect(result.metrics.maximumChannelError).toBeLessThanOrEqual(
      tolerance.maximumChannelError,
    );
    expect(result.metrics.alphaMeanError).toBeLessThanOrEqual(
      tolerance.alphaMeanError,
    );
  }
  await page.evaluate(() => window.fnxViewer.dispose());
}
for (const index of [
  0,
  2,
  4,
  6,
  8,
  11,
  ...Array.from({ length: 20 }, (_, i) => i + 12),
  33,
  34,
])
  test(`candidate rendering regression fixture ${index}`, async ({
    page,
    browser,
  }) => {
    const frame = await capture(page, index);
    await qualifyCapture(page, browser, frame, index);
  });

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
const jsonSchema: z.ZodType<Json> = z.lazy(() =>
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.null(),
    z.array(jsonSchema),
    z.record(z.string(), jsonSchema),
  ]),
);
function object(value: Json | undefined): value is { [key: string]: Json } {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function corrupt(value: Json, kind: string): number {
  if (Array.isArray(value))
    return value.reduce<number>(
      (count, item) => count + corrupt(item, kind),
      0,
    );
  if (!object(value)) return 0;
  let edits = 0;
  if (kind === "uv" && Array.isArray(value.uvs)) {
    value.uvs = value.uvs.map((v) => (typeof v === "number" ? v + 0.3 : v));
    edits++;
  }
  if (kind === "clipping" && value.type === "clipping") {
    value.type = "boundingbox";
    delete value.end;
    edits++;
  }
  if (kind === "order" && Array.isArray(value.slots)) {
    value.slots.reverse();
    edits++;
  }
  if (kind === "blend" && Array.isArray(value.slots))
    for (const slot of value.slots)
      if (object(slot)) {
        slot.blend = "additive";
        edits++;
      }
  for (const item of Object.values(value)) edits += corrupt(item, kind);
  return edits;
}
for (const [kind, index] of [
  ["uv", 6],
  ["clipping", 12],
  ["order", 6],
  ["blend", 6],
  ["alpha", 12],
  ["atlas", 6],
] as const)
  test(`visual negative: broken ${kind} fails candidate comparison`, async ({
    page,
  }) => {
    const before = await capture(page, index);
    await page.evaluate(() => window.fnxViewer.dispose());
    let body: Buffer = Buffer.alloc(0),
      target = "";
    await page.route(`**/launch/${index}.json`, async (route) => {
      const response = await route.fetch();
      const assets = assetsSchema.parse(await response.json());
      if (kind === "alpha") {
        for (const p of Object.values(assets.pages)) p.pma = !p.pma;
      } else {
        target = kind === "atlas" ? assets.atlas : assets.skeleton;
        const original = await page.request.get(
          new URL(target, transport.url).href,
        );
        if (kind === "atlas") {
          const text = await original.text();
          const changed = text.replace(/rotate: (90|true)/g, "rotate: false");
          expect(changed).not.toBe(text);
          body = Buffer.from(changed);
        } else {
          const doc = jsonSchema.parse(await original.json());
          expect(corrupt(doc, kind)).toBeGreaterThan(0);
          body = Buffer.from(JSON.stringify(doc));
        }
        assets.resourceHashes[target] = digest(body);
      }
      await route.fulfill({ response, json: assets });
    });
    await page.route(`**/asset/${index}/**`, async (route) => {
      if (new URL(route.request().url()).pathname === target)
        await route.fulfill({ body });
      else await route.continue();
    });
    const after = await capture(page, index);
    const result = compare(
      Buffer.from(before.png.split(",")[1]!, "base64"),
      Buffer.from(after.png.split(",")[1]!, "base64"),
    );
    await writeFile(
      `${output}/negative-${kind}.json`,
      JSON.stringify(result.metrics, null, 2),
    );
    await writeFile(`${output}/negative-${kind}-diff.png`, result.diff);
    expect(
      result.metrics.changedFraction > tolerance.changedFraction ||
        result.metrics.meanAbsoluteError > tolerance.meanAbsoluteError ||
        result.metrics.alphaMeanError > tolerance.alphaMeanError ||
        result.metrics.maximumChannelError > tolerance.maximumChannelError,
    ).toBe(true);
    await page.evaluate(() => window.fnxViewer.dispose());
  });

// Explicitly derived variants: authentic geometry/animation, all slot blend modes
// changed for test coverage. These are not unmodified official artistic references.
for (const index of [12, 13, 22, 23])
  for (const blend of ["normal", "additive", "multiply", "screen"])
    test(`candidate blend ${index} ${blend}`, async ({ page, browser }) => {
      let changed = Buffer.alloc(0);
      await page.route(`**/launch/${index}.json`, async (route) => {
        const response = await route.fetch();
        const assets = assetsSchema.parse(await response.json());
        const original = await page.request.get(
          new URL(assets.skeleton, transport.url).href,
        );
        const doc = jsonSchema.parse(await original.json());
        if (!object(doc) || !Array.isArray(doc.slots))
          throw Error("Fixture slots absent");
        for (const slot of doc.slots) {
          if (!object(slot)) throw Error("Invalid slot");
          slot.blend = blend;
        }
        changed = Buffer.from(JSON.stringify(doc));
        assets.resourceHashes[assets.skeleton] = digest(changed);
        await route.fulfill({ response, json: assets });
      });
      await page.route(`**/asset/${index}/coin-pro.json`, (route) =>
        route.fulfill({ body: changed }),
      );
      await capture(page, index);
      const frame = await page.evaluate(async () => {
        const v = window.fnxViewer;
        await v.request({
          protocolVersion: 1,
          sessionId: v.sessionId,
          requestId: "background",
          command: "SET_BACKGROUND",
          payload: { rgba: [0.2, 0.3, 0.4, 1] },
        });
        return v.captureFrame();
      });
      await qualifyCapture(
        page,
        browser,
        frame,
        `derived-blend-${index}-${blend}`,
      );
    });
