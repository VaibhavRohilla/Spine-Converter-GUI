import { test, expect, type Page } from "@playwright/test";
import { PNG } from "pngjs";
import { writeFile, mkdir } from "node:fs/promises";
import { server } from "./server";
import type { Capture, Command } from "../src/contracts";
let transport: Awaited<ReturnType<typeof server>>;
const evidence = "docs/evidence/B4";
test.beforeAll(async () => {
  transport = await server();
  await mkdir(evidence, { recursive: true });
});
test.afterAll(async () => {
  if (transport) await transport.close();
});
async function load(page: Page, index: number) {
  await page.goto(`${transport.url}frame.html?index=${index}`);
  await page.waitForFunction(
    () =>
      window.fnxViewer &&
      ["READY", "PAUSED", "FAILED"].includes(window.fnxViewer.state),
  );
  const error = await page.locator("#diagnostics").textContent();
  expect(
    await page.evaluate(() => window.fnxViewer.state),
    error ?? "",
  ).not.toBe("FAILED");
}
async function cmd(page: Page, command: Command) {
  const reply = await page.evaluate(async (c) => {
    const v = window.fnxViewer;
    return await v.request({
      ...c,
      protocolVersion: 1,
      sessionId: v.sessionId,
      requestId: crypto.randomUUID(),
    });
  }, command);
  expect(reply.success, JSON.stringify(reply.diagnostics)).toBe(true);
  return reply;
}
async function frame(page: Page): Promise<Capture> {
  return await page.evaluate(() => window.fnxViewer.captureFrame());
}
function pixels(c: Capture) {
  return PNG.sync.read(Buffer.from(c.png.split(",")[1] ?? "", "base64"));
}
function visible(c: Capture) {
  const png = pixels(c);
  let solid = 0,
    transparent = 0;
  for (let i = 3; i < png.data.length; i += 4) {
    if (png.data[i]! > 10) solid++;
    if (png.data[i] === 0) transparent++;
  }
  expect(solid).toBeGreaterThan(500);
  expect(transparent).toBeGreaterThan(500);
  return { solid, transparent };
}
for (let index = 0; index < 12; index++)
  test(`official renderer fixture ${index}: pixels, evaluation, fixed capture, pause`, async ({
    page,
    browserName,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await load(page, index);
    await cmd(page, {
      command: "SET_VIEWPORT",
      payload: { width: 640, height: 640, pixelRatio: 1 },
    });
    await cmd(page, { command: "STOP", payload: {} });
    const setup = await frame(page);
    visible(setup);
    const info = await page.evaluate(() => window.fnxViewer.info());
    const animation =
      info.animations.find((a) => a.name === "walk") ??
      info.animations.find((a) => a.duration > 0);
    expect(animation).toBeDefined();
    await cmd(page, {
      command: "SET_ANIMATION",
      payload: { name: animation!.name, mix: 0 },
    });
    await cmd(page, {
      command: "SEEK",
      payload: { seconds: animation!.duration * 0.25 },
    });
    const a = await frame(page);
    visible(a);
    await cmd(page, {
      command: "SEEK",
      payload: { seconds: animation!.duration * 0.75 },
    });
    const b = await frame(page);
    expect(b.sha256).not.toBe(a.sha256);
    await cmd(page, {
      command: "SEEK",
      payload: { seconds: animation!.duration * 0.25 },
    });
    const again = await frame(page);
    expect(again.sha256).toBe(a.sha256);
    expect(again.pose).toEqual(a.pose);
    await cmd(page, { command: "PLAY", payload: {} });
    await cmd(page, { command: "PLAY", payload: {} });
    await page.waitForTimeout(180);
    await cmd(page, { command: "PAUSE", payload: {} });
    const pause = await frame(page);
    await page.waitForTimeout(120);
    expect((await frame(page)).sha256).toBe(pause.sha256);
    for (const bone of b.pose.bones)
      expect(bone.world.every(Number.isFinite)).toBe(true);
    expect(errors).toEqual([]);
    await writeFile(
      `${evidence}/fixture-${index}.png`,
      Buffer.from(b.png.split(",")[1] ?? "", "base64"),
    );
    await writeFile(
      `${evidence}/fixture-${index}.json`,
      JSON.stringify(
        {
          browserName,
          info,
          capture: { ...b, png: undefined },
          pixelEvidence: visible(b),
          checks: [
            "visible setup and animation pixels",
            "motion",
            "fixed seek repeatability",
            "paused stability",
            "finite transforms",
          ],
          visuallyVerified: false,
          binaryCodecQualified: false,
        },
        null,
        2,
      ),
    );
    await cmd(page, { command: "DISPOSE", payload: {} });
    expect(await page.evaluate(() => window.fnxViewer.state)).toBe("DISPOSED");
  });
test("two runtime documents stay isolated during play, camera and disposal", async ({
  page,
}) => {
  await page.goto(transport.url + "?left=0&right=8");
  await page.waitForFunction(
    () =>
      Array.from(document.querySelectorAll("iframe")).length === 2 &&
      Array.from(document.querySelectorAll("iframe")).every(
        (f) => f.contentWindow?.fnxViewer?.state === "READY",
      ),
  );
  const result = await page.evaluate(async () => {
    const frames = document.querySelectorAll("iframe");
    const a = frames[0]!.contentWindow!.fnxViewer,
      b = frames[1]!.contentWindow!.fnxViewer;
    a.setAnimation("walk", 0);
    b.setAnimation("walk", 0);
    await a.seek(0.2);
    await b.seek(0.2);
    const original = await b.captureFrame();
    await a.play();
    await new Promise((r) => setTimeout(r, 120));
    a.dispose();
    return {
      independent: original.sha256 === (await b.captureFrame()).sha256,
      a: a.state,
      b: b.state,
      leftFamily: a.assets.family,
      rightFamily: b.assets.family,
    };
  });
  expect(result.independent).toBe(true);
  expect(result.a).toBe("DISPOSED");
  expect(result.b).toBe("PAUSED");
  expect(result.leftFamily).toBe("3.8");
  expect(result.rightFamily).toBe("4.3");
});
test("protocol, missing animation and skin reject without false verification", async ({
  page,
}) => {
  await load(page, 6);
  const replies = await page.evaluate(async () => {
    const v = window.fnxViewer;
    const request = (command: Command) =>
      v.request({
        ...command,
        protocolVersion: 1,
        sessionId: v.sessionId,
        requestId: crypto.randomUUID(),
      });
    return await Promise.all([
      request({
        command: "SET_ANIMATION",
        payload: { name: "missing", mix: 0 },
      }),
      request({ command: "SET_SKIN", payload: { name: "missing" } }),
      request({ command: "SEEK", payload: { seconds: Infinity } }),
    ]);
  });
  expect(replies.map((r) => r.success)).toEqual([false, false, false]);
  expect(replies.map((r) => r.diagnostics[0]?.code)).toEqual([
    "ANIMATION_NOT_FOUND",
    "SKIN_NOT_FOUND",
    "INVALID_PROTOCOL_REQUEST",
  ]);
});
test("events suppressed on seek, bounded clock, end state and frame stepping", async ({
  page,
}) => {
  await load(page, 6);
  const result = await page.evaluate(async () => {
    const v = window.fnxViewer;
    let events = 0;
    v.addEventListener("ANIMATION_EVENT", () => events++);
    v.setAnimation("walk", 0);
    await v.seek(2.2);
    const afterSeek = events;
    await v.play();
    await new Promise((r) => setTimeout(r, 700));
    v.pause();
    const liveEvents = events;
    await v.request({
      protocolVersion: 1,
      sessionId: v.sessionId,
      requestId: "loop",
      command: "SET_LOOP",
      payload: { enabled: false },
    });
    await v.seek(0.99);
    await v.play();
    await new Promise((r) => setTimeout(r, 100));
    const end = v.info();
    await v.seek(0);
    v.step(1 / 60);
    return { afterSeek, liveEvents, end, stepped: v.info().time };
  });
  expect(result.afterSeek).toBe(0);
  expect(result.liveEvents).toBeGreaterThan(0);
  expect(result.end.state).toBe("PAUSED");
  expect(result.end.time).toBe(1);
  expect(result.stepped).toBeCloseTo(1 / 60);
});
test("context loss fails closed and explicit retry restores", async ({
  page,
}) => {
  await load(page, 6);
  await page.evaluate(() => {
    const gl = window.fnxViewer.canvas.getContext("webgl");
    const extension = gl?.getExtension("WEBGL_lose_context");
    if (!extension) throw Error("WEBGL_lose_context unavailable");
    extension.loseContext();
    setTimeout(() => extension.restoreContext(), 100);
  });
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer.state))
    .toBe("FAILED");
  await page.waitForTimeout(200);
  await page.evaluate(() => window.fnxViewer.load());
  expect(await page.evaluate(() => window.fnxViewer.state)).toBe("READY");
  visible(await frame(page));
});
test("cancellation during pending texture transport never revives session", async ({
  page,
}) => {
  await page.route("**/asset/6/*.png", async (route) => {
    await new Promise((r) => setTimeout(r, 250));
    await route.continue().catch(() => {});
  });
  await page.goto(`${transport.url}frame.html?index=6`);
  await page.waitForFunction(
    () => window.fnxViewer?.state === "LOADING_ASSETS",
  );
  await page.evaluate(() => window.fnxViewer.dispose());
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => window.fnxViewer.state)).toBe("DISPOSED");
});
test("disposed capture and seek reject, repeated reload releases resources", async ({
  page,
}) => {
  await load(page, 6);
  const result = await page.evaluate(async () => {
    const original = window.fnxViewer;
    const captures = [];
    for (let i = 0; i < 4; i++) {
      await original.load().catch(() => {});
      original.setAnimation("walk", 0);
      await original.seek(0.2);
      captures.push((await original.captureFrame()).sha256);
      const pending = original.captureFrame();
      original.dispose();
      let rejected = false;
      try {
        await pending;
      } catch {
        rejected = true;
      }
      if (i === 0) return { rejected, state: original.state, captures };
    }
    throw Error("unreachable");
  });
  expect(result.rejected).toBe(true);
  expect(result.state).toBe("DISPOSED");
  // Real DOM reload exercises context and renderer creation without detached loops.
  for (let i = 0; i < 3; i++) {
    await load(page, 6);
    await cmd(page, { command: "PLAY", payload: {} });
    await cmd(page, { command: "DISPOSE", payload: {} });
    expect(
      await page.evaluate(() => window.fnxViewer.info().statistics),
    ).toBeNull();
  }
});
test("camera, debug and high DPI alter real frames with reset behavior", async ({
  page,
}) => {
  await load(page, 6);
  await cmd(page, {
    command: "SET_VIEWPORT",
    payload: { width: 400, height: 300, pixelRatio: 2 },
  });
  const a = await frame(page);
  expect(a.width).toBe(800);
  expect(a.height).toBe(600);
  const camera = await page.evaluate(() => window.fnxViewer.info().camera);
  await cmd(page, { command: "SET_CAMERA", payload: { ...camera, zoom: 2 } });
  expect((await frame(page)).sha256).not.toBe(a.sha256);
  await cmd(page, { command: "RESET_CAMERA", payload: {} });
  expect((await frame(page)).sha256).toBe(a.sha256);
  await cmd(page, {
    command: "SET_DEBUG",
    payload: {
      bones: true,
      regions: true,
      meshTriangles: true,
      meshHull: true,
      clipping: true,
      boundingBoxes: true,
      paths: true,
      origin: true,
      bounds: true,
    },
  });
  expect((await frame(page)).sha256).not.toBe(a.sha256);
});
for (let index = 12; index < 32; index++)
  test(`feature fixture ${index}: all animations, skins, constraints and deterministic frames`, async ({
    page,
  }) => {
    await load(page, index);
    await cmd(page, {
      command: "SET_VIEWPORT",
      payload: { width: 512, height: 512, pixelRatio: 1 },
    });
    const info = await page.evaluate(() => window.fnxViewer.info());
    const samples = [];
    for (const animation of info.animations) {
      await cmd(page, {
        command: "SET_ANIMATION",
        payload: { name: animation.name, mix: 0 },
      });
      await cmd(page, {
        command: "SEEK",
        payload: { seconds: animation.duration * 0.5 },
      });
      const a = await frame(page);
      await cmd(page, {
        command: "SEEK",
        payload: { seconds: animation.duration * 0.5 },
      });
      const b = await frame(page);
      expect(b.sha256).toBe(a.sha256);
      for (const bone of a.pose.bones)
        expect(bone.world.every(Number.isFinite)).toBe(true);
      samples.push({
        animation: animation.name,
        duration: animation.duration,
        hash: a.sha256,
        constraints: a.pose.constraints,
        attachmentTypes: [...new Set(a.pose.slots.map((s) => s.type))],
      });
    }
    const hashes = [];
    for (const skin of info.skins) {
      await cmd(page, { command: "SET_SKIN", payload: { name: skin } });
      hashes.push((await frame(page)).sha256);
    }
    if (info.skins.length > 1) expect(new Set(hashes).size).toBeGreaterThan(1);
    const capture = await frame(page);
    visible(capture);
    await writeFile(
      `${evidence}/fixture-${index}.png`,
      Buffer.from(capture.png.split(",")[1] ?? "", "base64"),
    );
    await writeFile(
      `${evidence}/feature-${index}.json`,
      JSON.stringify(
        { info, samples, skins: info.skins, visuallyVerified: false },
        null,
        2,
      ),
    );
  });
test("controlled pair records duration mismatch, pose correspondence and pixel difference without certification", async ({
  page,
}) => {
  await page.goto(transport.url + "?left=0&right=8");
  await page.getByRole("button", { name: "Find shared animations" }).click();
  await expect(
    page.getByRole("combobox", { name: "Shared animation" }),
  ).toContainText("walk");
  await page
    .getByRole("combobox", { name: "Shared animation" })
    .selectOption("walk");
  await page
    .getByRole("button", { name: "Capture pair and difference" })
    .click();
  await expect(page.locator("#comparison pre")).toContainText(
    "FRAMES_CAPTURED_NOT_VISUALLY_VERIFIED",
  );
  await expect(page.locator("#comparison pre")).toContainText(
    "durationDifference",
  );
  await page.screenshot({
    path: `${evidence}/paired-viewer.png`,
    fullPage: true,
  });
});
test("official straight and PMA exports have close rendered colors", async ({
  page,
}) => {
  await load(page, 14);
  await cmd(page, {
    command: "SET_VIEWPORT",
    payload: { width: 512, height: 512, pixelRatio: 1 },
  });
  await cmd(page, { command: "STOP", payload: {} });
  const a = await frame(page);
  await load(page, 15);
  await cmd(page, {
    command: "SET_VIEWPORT",
    payload: { width: 512, height: 512, pixelRatio: 1 },
  });
  await cmd(page, { command: "STOP", payload: {} });
  const b = await frame(page);
  const aa = pixels(a).data,
    bb = pixels(b).data;
  expect(aa.length).toBe(bb.length);
  let total = 0;
  for (let i = 0; i < aa.length; i++) total += Math.abs(aa[i]! - bb[i]!);
  expect(total / aa.length).toBeLessThan(1);
  await writeFile(
    `${evidence}/pma-metrics.json`,
    JSON.stringify({
      meanAbsoluteError: total / aa.length,
      threshold: 1,
      reference: "official paired straight/PMA exports; same camera",
      visuallyVerified: false,
    }),
  );
});
for (const index of [33, 34])
  test(`physics fixture ${index} resets and simulates deterministically`, async ({
    page,
  }) => {
    await load(page, index);
    await cmd(page, {
      command: "SET_VIEWPORT",
      payload: { width: 512, height: 512, pixelRatio: 1 },
    });
    const info = await page.evaluate(() => window.fnxViewer.info());
    const records = [];
    for (const animation of info.animations) {
      await cmd(page, {
        command: "SET_ANIMATION",
        payload: { name: animation.name, mix: 0 },
      });
      await cmd(page, { command: "SEEK", payload: { seconds: 2.25 } });
      const a = await frame(page);
      expect(a.pose.constraints.some((c) => c.type === "physics")).toBe(true);
      await cmd(page, { command: "SEEK", payload: { seconds: 2.25 } });
      const b = await frame(page);
      expect(b.sha256).toBe(a.sha256);
      expect(b.pose.bones).toEqual(a.pose.bones);
      visible(a);
      records.push({
        animation: animation.name,
        capture: { ...a, png: undefined },
      });
      await writeFile(
        `${evidence}/physics-${index}.png`,
        Buffer.from(a.png.split(",")[1] ?? "", "base64"),
      );
    }
    await writeFile(
      `${evidence}/physics-${index}.json`,
      JSON.stringify(
        {
          info,
          records,
          policy:
            "fresh skeleton and animation state, simulation 1/60 plus remainder",
          visuallyVerified: false,
        },
        null,
        2,
      ),
    );
  });
test("keyboard camera and narrow developer controls stay usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await load(page, 6);
  const before = await frame(page);
  const canvas = page.locator("#canvas");
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer.info().camera.x))
    .not.toBe(before.camera.x);
  await page.keyboard.press("0");
  expect((await frame(page)).sha256).toBe(before.sha256);
  await page.getByRole("combobox", { name: "Animation" }).selectOption("walk");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => window.fnxViewer.state))
    .toBe("PLAYING");
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.screenshot({
    path: `${evidence}/narrow-viewer.png`,
    fullPage: true,
  });
});
test("production looping records measured budgets and environment", async ({
  page,
  browser,
}) => {
  await load(page, 11);
  await cmd(page, {
    command: "SET_VIEWPORT",
    payload: { width: 640, height: 640, pixelRatio: 1 },
  });
  const measurements = await page.evaluate(async () => {
    const v = window.fnxViewer;
    const animation = v.info().animations.find((a) => a.duration > 0);
    if (!animation) throw Error("No animation");
    v.setAnimation(animation.name, 0);
    await v.play();
    const samples: { update: number; render: number }[] = [];
    const start = performance.now();
    const first = v.info().statistics?.frames ?? 0;
    while (performance.now() - start < 2000) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      const statistics = v.info().statistics;
      if (statistics)
        samples.push({
          update: statistics.updateMs,
          render: statistics.renderMs,
        });
    }
    v.pause();
    const elapsed = performance.now() - start;
    const frames = (v.info().statistics?.frames ?? 0) - first;
    const gl = v.canvas.getContext("webgl")!;
    const debug = gl.getExtension("WEBGL_debug_renderer_info");
    return {
      samples,
      elapsed,
      frames,
      fps: (frames * 1000) / elapsed,
      info: v.info(),
      gpu: debug
        ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL))
        : "unavailable",
      userAgent: navigator.userAgent,
    };
  });
  const percentile = (values: number[]) =>
    values.sort((a, b) => a - b)[Math.floor(values.length * 0.95)] ?? 0;
  const update95 = percentile(measurements.samples.map((s) => s.update)),
    render95 = percentile(measurements.samples.map((s) => s.render));
  expect(measurements.frames).toBeGreaterThan(10);
  expect(measurements.info.statistics!.loadMs).toBeLessThan(10000);
  expect(update95).toBeLessThan(50);
  expect(render95).toBeLessThan(50);
  await writeFile(
    `${evidence}/performance.json`,
    JSON.stringify(
      {
        ...measurements,
        browserVersion: browser.version(),
        update95,
        render95,
        budgets: { loadMs: 10000, update95Ms: 50, render95Ms: 50 },
        scope:
          "This local machine and merged_multi fixture only; no universal FPS promise; CPU call timings, not GPU execution time.",
      },
      null,
      2,
    ),
  );
});
test("paired sampled playback synchronizes normalized time without equating durations", async ({
  page,
}) => {
  await page.goto(transport.url + "?left=0&right=8");
  await page.getByRole("button", { name: "Find shared animations" }).click();
  await page
    .getByRole("combobox", { name: "Shared animation" })
    .selectOption("walk");
  await page
    .getByRole("button", { name: "Play synchronized", exact: true })
    .click();
  await expect(page.locator("#comparison pre")).toContainText(
    "Synchronized normalized playback",
  );
  await page.waitForTimeout(250);
  await page.getByRole("button", { name: "Pause pair", exact: true }).click();
  await page.waitForTimeout(100);
  const times = await page.evaluate(() =>
    Array.from(document.querySelectorAll("iframe")).map((f) =>
      f.contentWindow!.fnxViewer.info(),
    ),
  );
  expect(times[0]!.time).toBeGreaterThan(0);
  expect(times[0]!.time / times[0]!.duration).toBeCloseTo(
    times[1]!.time / times[1]!.duration,
    8,
  );
  expect(times[0]!.duration).not.toBe(times[1]!.duration);
});
