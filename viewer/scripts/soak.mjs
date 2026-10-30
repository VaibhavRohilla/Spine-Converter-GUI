// Real adapters, same document and canvas across cycles; no renderer replacement.
import { chromium } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
const out = process.env.B4_SOAK_OUTPUT ?? "docs/evidence/B4/soak";
const seconds = Number(process.env.B4_SOAK_SECONDS ?? 1800);
const cycles = Number(process.env.B4_SOAK_CYCLES ?? 200);
if (
  !Number.isFinite(seconds) ||
  seconds < 1 ||
  !Number.isInteger(cycles) ||
  cycles < 1
)
  throw Error("Invalid workload");
await mkdir(out); // Fresh evidence only; never overwrite a prior run.
const budgets = {
  cycles,
  seconds,
  maxLoadMs: 10000,
  maxHeapGrowthBytes: 64 * 1024 * 1024,
  maxRssGrowthKiB: 512 * 1024,
  maxLateHeapSlopeBytesPerCycle: 262144,
  maxLateRssSlopeKiBPerCycle: 2048,
  runtimeErrors: 0,
  liveGpuObjectsAfterDispose: 0,
};
await writeFile(`${out}/budgets.json`, JSON.stringify(budgets, null, 2));
const child = spawn(".venv/bin/python", [
  "-u",
  "viewer/scripts/test_server.py",
]);
const closed = new Promise((resolve) => child.once("close", resolve));
let browser;
const samples = [],
  errors = [], warnings = [];
const started = Date.now();
let result = {
  status: "FAILED",
  budgets,
  host: { platform: os.platform(), release: os.release(), arch: os.arch() },
  samples,
  errors,
  warnings,
};
function processTree() {
  const rows = execFileSync("ps", ["-axo", "pid=,ppid=,rss="], {
    encoding: "utf8",
  })
    .trim()
    .split("\n")
    .map((s) => s.trim().split(/\s+/).map(Number));
  const ids = new Set([process.pid]);
  let previous = 0;
  while (previous !== ids.size) {
    previous = ids.size;
    for (const [pid, ppid] of rows) if (ids.has(ppid)) ids.add(pid);
  }
  return rows.filter(([pid]) => ids.has(pid)).map(([pid, ppid, rssKiB]) => ({pid, ppid, rssKiB, role: pid === process.pid ? "node" : pid === child.pid ? "python" : "browser-descendant"}));
}
try {
  let stderr = "";
  child.stderr.on("data", (b) => (stderr = (stderr + b).slice(-65536)));
  const url = await new Promise((resolve, reject) => {
    let data = "";
    const timer = setTimeout(
      () => reject(Error(stderr || "server deadline")),
      30000,
    );
    child.stdout.on("data", (b) => {
      data += b;
      if (data.includes("\n")) {
        clearTimeout(timer);
        resolve(data.trim().split("\n")[0]);
      }
    });
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("exit", (c) => {
      clearTimeout(timer);
      reject(Error(`server ${c}: ${stderr}`));
    });
  });
  browser = await chromium.launch();
  result.browser = browser.version();
  const page = await browser.newPage({ viewport: { width: 640, height: 640 } });
  page.on("console", message => {
    if (message.type() === "warning") warnings.push(message.text());
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("crash", () => errors.push("page crash"));
  await page.goto(`${url}frame.html?index=0`);
  await page.waitForFunction(() => window.fnxViewer?.state === "READY");
  await page.evaluate(() => {
    window.fnxViewer.dispose();
  });
  await page.evaluate(async (url) => {
    const mod = await import(`${url}component.js`);
    window.soak = {
      mod,
      live: new Set(),
      gpuCounts: {},
      activeSessions: new Set(),
      runtimeWarnings: [],
      runtimeErrors: [],
      schedulers: new Set(),
      listeners: new Set(),
      canvases: [],
      viewers: [],
      lifecycle: Promise.resolve(),
    };
    const request = window.requestAnimationFrame.bind(window),
      cancel = window.cancelAnimationFrame.bind(window);
    window.requestAnimationFrame = (callback) => {
      const id = request((time) => {
        window.soak.schedulers.delete(id);
        callback(time);
      });
      window.soak.schedulers.add(id);
      return id;
    };
    window.cancelAnimationFrame = (id) => {
      window.soak.schedulers.delete(id);
      cancel(id);
    };
    const add = EventTarget.prototype.addEventListener,
      remove = EventTarget.prototype.removeEventListener;
    const tracked = new Set([
      "webglcontextlost",
      "webglcontextrestored",
      "visibilitychange",
    ]);
    EventTarget.prototype.addEventListener = function (
      type,
      callback,
      options,
    ) {
      if (tracked.has(type)) window.soak.listeners.add(callback);
      return add.call(this, type, callback, options);
    };
    EventTarget.prototype.removeEventListener = function (
      type,
      callback,
      options,
    ) {
      if (tracked.has(type)) window.soak.listeners.delete(callback);
      return remove.call(this, type, callback, options);
    };
    window.soak.create = (canvas, assets) => {
      const v = new mod.SpineViewer(canvas, assets, assets.sessionId);
      window.soak.activeSessions.add(v);
      v.subscribe(([name, detail]) => {
        if (name === "SESSION_DISPOSED") window.soak.activeSessions.delete(v);
        if (name === "RUNTIME_WARNING") window.soak.runtimeWarnings.push(detail);
        if (name === "RUNTIME_ERROR") window.soak.runtimeErrors.push(detail);
        if (name === "PLAYBACK_CHANGED") {
          window.soak.lifecycle = window.soak.lifecycle.then(async () => {
            const response = await fetch(`${url}state/${assets.sessionId}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ protocolVersion: 1, state: detail.state }),
            });
            if (!response.ok)
              throw Error(`lifecycle ${detail.state}: ${response.status}`);
          });
        }
      });
      return v;
    };
    const p = WebGLRenderingContext.prototype;
    for (const kind of ["Texture", "Buffer", "Program", "Framebuffer", "Renderbuffer", "Shader"]) {
      const counts = window.soak.gpuCounts[kind] = {allocated: 0, disposed: 0};
      const create = p[`create${kind}`],
        remove = p[`delete${kind}`];
      p[`create${kind}`] = function (...args) {
        const obj = create.apply(this, args);
        if (obj) { window.soak.live.add(obj); counts.allocated++; }
        return obj;
      };
      p[`delete${kind}`] = function (obj) {
        if (window.soak.live.delete(obj)) counts.disposed++;
        return remove.call(this, obj);
      };
    }
    for (let i = 0; i < 2; i++) {
      const c = document.createElement("canvas");
      c.width = c.height = 320;
      document.body.append(c);
      window.soak.canvases.push(c);
    }
  }, url);
  const cdp = await page.context().newCDPSession(page);
  const fixtures = [
    0, 2, 4, 6, 8, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 33, 34,
  ];
  for (let cycle = 0; cycle < cycles; cycle++) {
    const loadMs = await page.evaluate(
      async ({ url, index }) => {
        const { mod, canvases } = window.soak;
        const assets = mod.assetsSchema.parse(
          await (await fetch(`${url}launch/${index}.json`)).json(),
        );
        const v = window.soak.create(canvases[0], assets);
        await v.load();
        const info = v.info();
        const animation = info.animations.find((a) => a.duration > 0);
        if (animation) {
          v.setAnimation(animation.name, 0);
          await v.play();
          v.pause();
          await v.play();
          v.pause();
          await v.seek(0.17);
          v.step(0.016);
          if (info.skins.length)
            await v.setSkin(info.skins[info.skins.length - 1]);
          await v.seek(0.31);
          await v.captureFrame();
          v.capturePose();
          v.stop();
        }
        const load = info.statistics.loadMs;
        v.dispose();
        if (
          v.state !== "DISPOSED" ||
          v.info().statistics !== null ||
          window.soak.live.size !== 0 ||
          window.soak.schedulers.size !== 0 ||
          window.soak.listeners.size !== 0 ||
          v.eventListeners.size !== 0
        )
          throw Error("resource owner survives disposal");
        await window.soak.lifecycle;
        return load;
      },
      { url, index: fixtures[cycle % fixtures.length] },
    );
    if (loadMs > budgets.maxLoadMs) throw Error(`load budget: ${loadMs}`);
    if (cycle % 10 === 0 || cycle === cycles - 1) {
      await cdp.send("HeapProfiler.collectGarbage");
      const heap = await cdp.send("Runtime.getHeapUsage");
      const tree = processTree();
      const resources = await page.evaluate(() => ({activeSessions: window.soak.activeSessions.size, gpuCounts: window.soak.gpuCounts, liveGpuObjects: window.soak.live.size, listeners: window.soak.listeners.size, schedulers: window.soak.schedulers.size, subscribers: [...window.soak.activeSessions].reduce((n,v) => n + v.eventListeners.size, 0)}));
      samples.push({
        phase: "cycles",
        processTree: tree,
        resources,
        cycle,
        elapsedMs: Date.now() - started,
        heap: heap.usedSize,
        rssKiB: tree.reduce((n, row) => n + row.rssKiB, 0),
        loadMs,
      });
      await writeFile(`${out}/progress.json`, JSON.stringify(samples, null, 2));
    }
  }
  await page.evaluate(async (url) => {
    const { mod, canvases, viewers } = window.soak;
    for (const [i, index] of [0, 34].entries()) {
      const assets = mod.assetsSchema.parse(
        await (await fetch(`${url}launch/${index}.json`)).json(),
      );
      const v = window.soak.create(canvases[i], assets);
      viewers.push(v);
      await v.load();
      await v.play();
    }
  }, url);
  const playbackStart = Date.now();
  while (Date.now() - playbackStart < seconds * 1000) {
    await page.waitForTimeout(Math.min(10000, seconds * 1000));
    const stats = await page.evaluate(async () => {
      const values = [];
      for (const v of window.soak.viewers) {
        if (v.state !== "PLAYING") throw Error(`playback ${v.state}`);
        await v.captureFrame();
        v.capturePose();
        values.push(v.info().statistics);
        await v.play();
      }
      return values;
    });
    await cdp.send("HeapProfiler.collectGarbage");
    const heap = await cdp.send("Runtime.getHeapUsage");
    const tree = processTree();
    const resources = await page.evaluate(() => ({activeSessions: window.soak.activeSessions.size, gpuCounts: window.soak.gpuCounts, liveGpuObjects: window.soak.live.size, listeners: window.soak.listeners.size, schedulers: window.soak.schedulers.size, subscribers: [...window.soak.activeSessions].reduce((n,v) => n + v.eventListeners.size, 0)}));
    samples.push({
      phase: "playback",
      processTree: tree,
      resources,
      elapsedMs: Date.now() - playbackStart,
      heap: heap.usedSize,
      rssKiB: tree.reduce((n, row) => n + row.rssKiB, 0),
      stats,
    });
    await writeFile(`${out}/progress.json`, JSON.stringify(samples, null, 2));
  }
  result.graphics = await page.evaluate(() => {
    const gl = window.soak.canvases[0].getContext("webgl");
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return {
      vendor: ext
        ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL)
        : gl.getParameter(gl.VENDOR),
      renderer: ext
        ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER),
      version: gl.getParameter(gl.VERSION),
    };
  });
  result.disposal = await page.evaluate(async () => {
    for (const v of window.soak.viewers) v.dispose();
    await window.soak.lifecycle;
    return {
      activeSessions: window.soak.activeSessions.size,
      gpuCounts: window.soak.gpuCounts,
      runtimeWarnings: window.soak.runtimeWarnings,
      runtimeErrors: window.soak.runtimeErrors,
      states: window.soak.viewers.map((v) => v.state),
      liveGpuObjects: window.soak.live.size,
      liveSchedulers: window.soak.schedulers.size,
      liveListeners: window.soak.listeners.size,
      subscribers: window.soak.viewers.reduce(
        (n, v) => n + v.eventListeners.size,
        0,
      ),
    };
  });
  errors.push(...result.disposal.runtimeErrors.map(e => JSON.stringify(e)));
  warnings.push(...result.disposal.runtimeWarnings.map(e => JSON.stringify(e)));
  const late = samples.filter(
    (s) => s.phase === "cycles" && s.cycle >= Math.floor(cycles / 4),
  );
  function slope(key) {
    const mx = late.reduce((s, v) => s + v.cycle, 0) / late.length,
      my = late.reduce((s, v) => s + v[key], 0) / late.length;
    return (
      late.reduce((s, v) => s + (v.cycle - mx) * (v[key] - my), 0) /
      late.reduce((s, v) => s + (v.cycle - mx) ** 2, 0)
    );
  }
  const playback = samples.filter((s) => s.phase === "playback");
  if (late.length < 2 || playback.length < 2)
    throw Error("Insufficient samples to evaluate stability trends");
  result.playbackGrowth = {
    heap: playback.at(-1).heap - playback[0].heap,
    rssKiB: playback.at(-1).rssKiB - playback[0].rssKiB,
  };
  result.growth = {
    heap: late.at(-1).heap - late[0].heap,
    rssKiB: late.at(-1).rssKiB - late[0].rssKiB,
    heapSlope: slope("heap"),
    rssSlope: slope("rssKiB"),
  };
  const observations = [
    ["runtimeErrors", errors.length, budgets.runtimeErrors],
    [
      "playbackHeapGrowth",
      result.playbackGrowth.heap,
      budgets.maxHeapGrowthBytes,
    ],
    [
      "playbackRssGrowthKiB",
      result.playbackGrowth.rssKiB,
      budgets.maxRssGrowthKiB,
    ],
    [
      "liveGpuObjects",
      result.disposal.liveGpuObjects,
      budgets.liveGpuObjectsAfterDispose,
    ],
    ["activeSessions", result.disposal.activeSessions, 0],
    ["liveSchedulers", result.disposal.liveSchedulers, 0],
    ["liveListeners", result.disposal.liveListeners, 0],
    ["subscribers", result.disposal.subscribers, 0],
    ["cycleHeapGrowth", result.growth.heap, budgets.maxHeapGrowthBytes],
    ["cycleRssGrowthKiB", result.growth.rssKiB, budgets.maxRssGrowthKiB],
    [
      "cycleHeapSlope",
      result.growth.heapSlope,
      budgets.maxLateHeapSlopeBytesPerCycle,
    ],
    [
      "cycleRssSlopeKiB",
      result.growth.rssSlope,
      budgets.maxLateRssSlopeKiBPerCycle,
    ],
  ];
  result.budgetFailures = observations
    .filter(
      ([, measured, maximum]) =>
        !Number.isFinite(measured) || measured > maximum,
    )
    .map(([metric, measured, maximum]) => ({ metric, measured, maximum }));
  if (result.budgetFailures.length) throw Error("stability budget failed");
  // Short diagnostics must never be mistaken for the extended release gate.
  result.status =
    cycles >= 200 && seconds >= 1800 ? "PASSED" : "DIAGNOSTIC_PASSED";
} catch (e) {
  errors.push(String(e));
  process.exitCode = 1;
} finally {
  result.durationMs = Date.now() - started;
  try {
    await browser?.close();
  } catch (error) {
    errors.push(`Browser cleanup: ${String(error)}`);
    result.status = "FAILED";
    process.exitCode = 1;
  } finally {
    child.kill("SIGINT");
    const escalation = setTimeout(() => child.kill("SIGKILL"), 5000);
    try {
      await closed;
    } finally {
      clearTimeout(escalation);
    }
  }
  result.serverExit = child.exitCode;
  result.serverSignal = child.signalCode;
  if (child.exitCode !== 0) {
    errors.push(`Server shutdown: ${child.exitCode}/${child.signalCode}`);
    result.status = "FAILED";
    process.exitCode = 1;
  }
  await writeFile(`${out}/result.json`, JSON.stringify(result, null, 2));
  console.log(
    JSON.stringify({
      status: result.status,
      durationMs: result.durationMs,
      errors,
    }),
  );
}
