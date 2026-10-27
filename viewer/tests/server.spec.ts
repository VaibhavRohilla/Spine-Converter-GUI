import { test, expect } from "@playwright/test";
import { server } from "./server";

test("server spawn failure rejects promptly without unhandled error", async () => {
  const previous = process.env.B4_VIEWER_PYTHON;
  process.env.B4_VIEWER_PYTHON = "/nonexistent/fnx-viewer-python";
  try {
    await expect(server()).rejects.toThrow("ENOENT");
  } finally {
    if (previous === undefined) delete process.env.B4_VIEWER_PYTHON;
    else process.env.B4_VIEWER_PYTHON = previous;
  }
});

test("real server shutdown is safe concurrently and after completion", async () => {
  const transport = await server();
  expect((await fetch(`${transport.url}sessions.json`)).ok).toBe(true);
  await Promise.all([transport.close(), transport.close()]);
  await transport.close();
  await expect(fetch(`${transport.url}sessions.json`)).rejects.toThrow();
});

for (const behavior of ["exit", "ignore-interrupt"] as const) {
  test(`server shutdown handles child behavior: ${behavior}`, async ({}, testInfo) => {
    const { writeFile, chmod, mkdir } = await import("node:fs/promises");
    const { resolve, dirname } = await import("node:path");
    const script = testInfo.outputPath("server-process.py");
    await mkdir(dirname(script), { recursive: true });
    await writeFile(
      script,
      [
        `#!${resolve(".venv/bin/python")}`,
        "import signal",
        ...(behavior === "ignore-interrupt"
          ? ["signal.signal(signal.SIGINT, signal.SIG_IGN)"]
          : []),
        'print("http://127.0.0.1:12345/test/", flush=True)',
        ...(behavior === "ignore-interrupt"
          ? ["while True: signal.pause()"]
          : []),
        "",
      ].join("\n"),
    );
    await chmod(script, 0o700);
    const previous = process.env.B4_VIEWER_PYTHON;
    process.env.B4_VIEWER_PYTHON = script;
    try {
      const transport = await server();
      // Ensure the short-lived child can exit before close registers any new work.
      await new Promise<void>((resolve) => setTimeout(resolve, 100));
      await transport.close();
      await transport.close();
    } finally {
      if (previous === undefined) delete process.env.B4_VIEWER_PYTHON;
      else process.env.B4_VIEWER_PYTHON = previous;
    }
  });
}
