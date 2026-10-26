import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 90000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: fileURLToPath(
          new URL("../docs/evidence/B4/browser-results.json", import.meta.url),
        ),
      },
    ],
  ],
  use: {
    browserName: "chromium",
    viewport: { width: 900, height: 900 },
    deviceScaleFactor: 1,
  },
  outputDir: "test-results",
});
