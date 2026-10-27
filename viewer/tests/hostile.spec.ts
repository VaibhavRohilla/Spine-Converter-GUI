import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { server } from "./server";
import { assetsSchema } from "../src/protocol";
declare global {
  interface Window {
    gpuLedger: {
      textures: Set<WebGLTexture>;
      buffers: Set<WebGLBuffer>;
      programs: Set<WebGLProgram>;
      framebuffers: Set<WebGLFramebuffer>;
    };
  }
}
let transport: Awaited<ReturnType<typeof server>>;
test.beforeAll(async () => {
  transport = await server();
});
test.afterAll(async () => {
  if (transport) await transport.close();
});
for (const stage of ["skeleton", "atlas", "texture"] as const)
  test(`cancel during ${stage} delivery`, async ({ page }) => {
    const suffix =
      stage === "skeleton"
        ? "spineboy-pro.json"
        : stage === "atlas"
          ? "spineboy.atlas"
          : "spineboy.png";
    let reached: () => void = () => {};
    const pending = new Promise<void>((resolve) => {
      reached = resolve;
    });
    await page.route(`**/asset/6/${suffix}`, async (route) => {
      reached();
      await new Promise((r) => setTimeout(r, 200));
      await route.continue().catch(() => {});
    });
    await page.goto(`${transport.url}frame.html?index=6`, {
      waitUntil: "commit",
    });
    await pending;
    await page.evaluate(() => window.fnxViewer.dispose());
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => window.fnxViewer.state)).toBe("DISPOSED");
  });
for (const [resource, code] of [
  ["skeleton", "SKELETON_PARSE_FAILED"],
  ["atlas", "ATLAS_LOAD_FAILED"],
  ["texture", "TEXTURE_DECODE_FAILED"],
] as const)
  test(`corrupt ${resource} with admitted transport hash fails visibly`, async ({
    page,
  }) => {
    const bytes = Buffer.from(
      resource === "atlas" ? "missing.png\nsize: 1,1\n" : "invalid data",
    );
    const hash = createHash("sha256").update(bytes).digest("hex");
    let target = "";
    await page.route("**/launch/6.json", async (route) => {
      const response = await route.fetch();
      const assets = assetsSchema.parse(await response.json());
      target =
        resource === "skeleton"
          ? assets.skeleton
          : resource === "atlas"
            ? assets.atlas
            : Object.values(assets.pages)[0]!.url;
      assets.resourceHashes[target] = hash;
      if (resource === "texture") Object.values(assets.pages)[0]!.sha256 = hash;
      await route.fulfill({ response, json: assets });
    });
    await page.route("**/asset/6/**", async (route) => {
      if (new URL(route.request().url()).pathname === target)
        await route.fulfill({
          status: 200,
          body: bytes,
          contentType: "application/octet-stream",
        });
      else await route.continue();
    });
    await page.goto(`${transport.url}frame.html?index=6`);
    await expect
      .poll(() => page.evaluate(() => window.fnxViewer?.state))
      .toBe("FAILED");
    await expect(page.locator("#diagnostics")).toContainText(code);
  });
test("hash mismatch prevents modified resource from reaching parser", async ({
  page,
}) => {
  await page.route("**/asset/6/spineboy-pro.json", (route) =>
    route.fulfill({ body: "{}", contentType: "application/json" }),
  );
  await page.goto(`${transport.url}frame.html?index=6`);
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer?.state))
    .toBe("FAILED");
  await expect(page.locator("#diagnostics")).toContainText(
    "ASSET_INTEGRITY_FAILED",
  );
});
test("failed asset transport produces typed failure", async ({ page }) => {
  await page.route("**/asset/6/spineboy.png", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  await page.goto(`${transport.url}frame.html?index=6`);
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer?.state))
    .toBe("FAILED");
  await expect(page.locator("#diagnostics")).toContainText(
    "ASSET_TRANSPORT_FAILED",
  );
});
test("runtime identity mismatch rejects before asset loading", async ({
  page,
}) => {
  await page.route("**/launch/6.json", async (route) => {
    const response = await route.fetch();
    const assets = assetsSchema.parse(await response.json());
    assets.runtimeRevision = "4.1.56";
    await route.fulfill({ response, json: assets });
  });
  await page.goto(`${transport.url}frame.html?index=6`);
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer?.state))
    .toBe("FAILED");
  await expect(page.locator("#diagnostics")).toContainText(
    "RUNTIME_VERSION_MISMATCH",
  );
});
test("genuine 3.8.75 source remains rejected by official runtime without rewriting", async ({
  page,
}) => {
  await page.goto(`${transport.url}frame.html?index=32`);
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer?.state))
    .toBe("FAILED");
  await expect(page.locator("#diagnostics")).toContainText(
    "SOURCE_EXPORT_KNOWN_BUG",
  );
  expect(await page.evaluate(() => window.fnxViewer.assets.exportVersion)).toBe(
    "3.8.75",
  );
});
test("dispose during long deterministic simulation cancels before completion", async ({
  page,
}) => {
  await page.goto(`${transport.url}frame.html?index=6`);
  await page.waitForFunction(() => window.fnxViewer?.state === "READY");
  const result = await page.evaluate(async () => {
    const v = window.fnxViewer;
    v.setAnimation("walk", 0);
    const seeking = v.seek(600);
    v.dispose();
    try {
      await seeking;
      return false;
    } catch {
      return v.state === "DISPOSED";
    }
  });
  expect(result).toBe(true);
});
test("GPU allocations are released on dispose", async ({ page }) => {
  await page.addInitScript(() => {
    const live = {
      textures: new Set<WebGLTexture>(),
      buffers: new Set<WebGLBuffer>(),
      programs: new Set<WebGLProgram>(),
      framebuffers: new Set<WebGLFramebuffer>(),
    };
    Object.defineProperty(window, "gpuLedger", { value: live });
    const p = WebGLRenderingContext.prototype;
    const ct = p.createTexture,
      dt = p.deleteTexture,
      cb = p.createBuffer,
      db = p.deleteBuffer,
      cp = p.createProgram,
      dp = p.deleteProgram,
      cf = p.createFramebuffer,
      df = p.deleteFramebuffer;
    p.createTexture = function () {
      const v = ct.call(this);
      if (v) live.textures.add(v);
      return v;
    };
    p.deleteTexture = function (v) {
      if (v) live.textures.delete(v);
      dt.call(this, v);
    };
    p.createBuffer = function () {
      const v = cb.call(this);
      if (v) live.buffers.add(v);
      return v;
    };
    p.deleteBuffer = function (v) {
      if (v) live.buffers.delete(v);
      db.call(this, v);
    };
    p.createProgram = function () {
      const v = cp.call(this);
      if (v) live.programs.add(v);
      return v;
    };
    p.deleteProgram = function (v) {
      if (v) live.programs.delete(v);
      dp.call(this, v);
    };
    p.createFramebuffer = function () {
      const v = cf.call(this);
      if (v) live.framebuffers.add(v);
      return v;
    };
    p.deleteFramebuffer = function (v) {
      if (v) live.framebuffers.delete(v);
      df.call(this, v);
    };
  });
  await page.goto(`${transport.url}frame.html?index=11`);
  await page.waitForFunction(() => window.fnxViewer?.state === "READY");
  const result = await page.evaluate(() => {
    const ledger = window.gpuLedger;
    const before = {
      textures: ledger.textures.size,
      buffers: ledger.buffers.size,
      programs: ledger.programs.size,
    };
    window.fnxViewer.dispose();
    return {
      before,
      after: {
        textures: ledger.textures.size,
        buffers: ledger.buffers.size,
        programs: ledger.programs.size,
        framebuffers: ledger.framebuffers.size,
      },
    };
  });
  expect(result.before.textures).toBe(2);
  expect(result.before.buffers).toBeGreaterThan(0);
  expect(result.after).toEqual({
    textures: 0,
    buffers: 0,
    programs: 0,
    framebuffers: 0,
  });
});
test("non-finite world transforms reject initialization", async ({ page }) => {
  let changed = "";
  let digest = "";
  await page.route("**/launch/6.json", async (route) => {
    const response = await route.fetch();
    const assets = assetsSchema.parse(await response.json());
    const source = await page.request.get(
      new URL(assets.skeleton, transport.url).href,
    );
    const doc = (await source.json()) as {
      bones: { name: string; x?: number; scaleX?: number }[];
    };
    doc.bones[0]!.scaleX = 1e308;
    doc.bones[1]!.x = 1e308;
    changed = JSON.stringify(doc);
    digest = createHash("sha256").update(changed).digest("hex");
    assets.resourceHashes[assets.skeleton] = digest;
    await route.fulfill({ response, json: assets });
  });
  await page.route("**/asset/6/spineboy-pro.json", (route) =>
    route.fulfill({ body: changed, contentType: "application/json" }),
  );
  await page.goto(`${transport.url}frame.html?index=6`);
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer?.state))
    .toBe("FAILED");
  await expect(page.locator("#diagnostics")).toContainText("NON_FINITE_POSE");
});
test("malformed binary is rejected before official reader", async ({
  page,
}) => {
  const bytes = Buffer.from([0, 0, 0, 0]);
  const hash = createHash("sha256").update(bytes).digest("hex");
  await page.route("**/launch/7.json", async (route) => {
    const response = await route.fetch();
    const asset = assetsSchema.parse(await response.json());
    asset.resourceHashes[asset.skeleton] = hash;
    await route.fulfill({ response, json: asset });
  });
  await page.route("**/asset/7/spineboy-pro.skel", (route) =>
    route.fulfill({ body: bytes }),
  );
  await page.goto(`${transport.url}frame.html?index=7`);
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer?.state))
    .toBe("FAILED");
  await expect(page.locator("#diagnostics")).toContainText(
    "UNTRUSTED_BINARY_DISABLED",
  );
});
test("dispose at the asset initialization boundary cannot publish READY", async ({
  page,
}) => {
  await page.route("**/asset/6/spineboy-pro.json", async (route) => {
    await new Promise((r) => setTimeout(r, 150));
    await route.continue();
  });
  await page.goto(`${transport.url}frame.html?index=6`, {
    waitUntil: "commit",
  });
  await page.waitForFunction(
    () => window.fnxViewer?.state === "LOADING_ASSETS",
  );
  await page.evaluate(() => {
    const v = window.fnxViewer;
    v.addEventListener("ASSETS_LOADED", () => v.dispose(), { once: true });
  });
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.fnxViewer.state)).toBe("DISPOSED");
});

for (const mutation of [
  "truncated",
  "counts",
  "strings",
  "indices",
  "geometry",
  "offsets",
] as const)
  test(`binary ${mutation}: forged transport approval fails, JSON session survives`, async ({
    page,
    context,
  }) => {
    const control = await context.newPage();
    await control.goto(`${transport.url}frame.html?index=6`);
    await control.waitForFunction(() => window.fnxViewer?.state === "READY");
    await control.evaluate(() => window.fnxViewer.play());
    let changed = Buffer.alloc(0);
    await page.route("**/launch/7.json", async (route) => {
      const response = await route.fetch();
      const assets = assetsSchema.parse(await response.json());
      const original = await page.request.get(
        new URL(assets.skeleton, transport.url).href,
      );
      changed = Buffer.from(await original.body());
      // Minimal hostile 4.2 header layout follows the pinned official reader:
      // hash (8), version string, five floats, nonessential flag, string table.
      const version = Buffer.from("4.2.22");
      const floats = Buffer.alloc(20);
      floats.writeFloatBE(1, 8);
      floats.writeFloatBE(1, 12);
      floats.writeFloatBE(100, 16);
      const header = Buffer.concat([
        Buffer.alloc(8),
        Buffer.from([version.length + 1]),
        version,
        floats,
        Buffer.from([0]),
      ]);
      const excessive = Buffer.from([255, 255, 255, 255, 7]); // 2^31-1 varint
      switch (mutation) {
        case "truncated":
          changed = changed.subarray(0, 12);
          break;
        case "counts":
          changed = Buffer.concat([header, excessive]);
          break;
        case "strings":
          changed = Buffer.concat([header, Buffer.from([1]), excessive]);
          break;
        case "indices": {
          const transform = Buffer.alloc(32);
          transform.writeFloatBE(1, 12);
          transform.writeFloatBE(1, 16);
          changed = Buffer.concat([
            header,
            Buffer.from([0, 2, 5]),
            Buffer.from("root"),
            transform,
            Buffer.from([0, 0, 6]),
            Buffer.from("child"),
            excessive,
          ]);
          break;
        }
        case "geometry":
          changed.writeFloatBE(NaN, 8 + 1 + version.length);
          break;
        case "offsets":
          changed = header.subarray(0, header.length - 3);
          break;
      }
      assets.resourceHashes[assets.skeleton] = createHash("sha256")
        .update(changed)
        .digest("hex");
      await route.fulfill({ response, json: assets });
    });
    await page.route("**/asset/7/spineboy-pro.skel", (route) =>
      route.fulfill({ body: changed }),
    );
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.goto(`${transport.url}frame.html?index=7`);
      await expect
        .poll(() => page.evaluate(() => window.fnxViewer?.state))
        .toBe("FAILED");
      await expect(page.locator("#diagnostics")).toContainText(
        "UNTRUSTED_BINARY_DISABLED",
      );
      expect(
        await page.evaluate(() => window.fnxViewer.info().statistics),
      ).toBeNull();
      await page.evaluate(() => window.fnxViewer.dispose());
      expect(await control.evaluate(() => window.fnxViewer.state)).toBe(
        "PLAYING",
      );
    }
    await control.evaluate(() => window.fnxViewer.dispose());
    await control.close();
  });
