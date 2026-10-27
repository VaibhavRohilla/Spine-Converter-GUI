import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { server } from "./server";
import { assetsSchema } from "../src/protocol";
import { runtimeCapabilities } from "../src/component";

let transport: Awaited<ReturnType<typeof server>>;
test.beforeAll(async () => { transport = await server(); });
test.afterAll(async () => { if (transport) await transport.close(); });

test("B5 can query the approved-binary-only capability without loading", () => {
  for (const family of ["3.8", "4.0", "4.1", "4.2", "4.3"] as const)
    expect(runtimeCapabilities[family]).toContain("APPROVED_BINARY_ONLY");
});

for (const binary of [true, false])
  test(`renamed binary and forged metadata cannot bypass admission: binary=${binary}`, async ({ page }) => {
    const bytes = Buffer.from([0, 255, 255, 255, 255]);
    await page.route("**/launch/7.json", async route => {
      const response = await route.fetch();
      const assets = assetsSchema.parse(await response.json());
      assets.skeleton = "/renamed.json";
      assets.binary = binary;
      assets.resourceHashes[assets.skeleton] = createHash("sha256").update(bytes).digest("hex");
      await route.fulfill({ response, json: assets });
    });
    await page.route("**/renamed.json", route => route.fulfill({body: bytes}));
    await page.goto(`${transport.url}frame.html?index=7`);
    await expect.poll(() => page.evaluate(() => window.fnxViewer?.state)).toBe("FAILED");
    await expect(page.locator("#diagnostics")).toContainText(binary ? "UNTRUSTED_BINARY_DISABLED" : "SKELETON_PARSE_FAILED");
    await page.evaluate(() => window.fnxViewer.dispose());
  });
