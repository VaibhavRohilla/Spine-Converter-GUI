import { createHostBridge, type HostBridge } from "./bridge";
import { SpineViewer, cleanDebug } from "./viewer";
import { assetsSchema } from "./protocol";
import type { Command, Request } from "./contracts";
const element = <T extends HTMLElement>(
  id: string,
  constructor: { new (): T },
): T => {
  const e = document.getElementById(id);
  if (!(e instanceof constructor)) throw Error(`Missing ${id}`);
  return e;
};
const canvas = element("canvas", HTMLCanvasElement);
const diagnostics = element("diagnostics", HTMLPreElement);
const status = element("status", HTMLPreElement);
const index = Number(new URLSearchParams(location.search).get("index") ?? 0);
const assets = assetsSchema.parse(
  await (await fetch(`launch/${index}.json`)).json(),
);
const viewer = new SpineViewer(canvas, assets, assets.sessionId);
// Stable B5 entry point. A host may call request and subscribe to the EventTarget.
declare global {
  interface Window {
    fnxViewer: SpineViewer;
    fnxBridge: HostBridge;
  }
}
window.fnxViewer = viewer;
window.fnxBridge = createHostBridge(viewer);
let lifecycle = Promise.resolve();
viewer.addEventListener("PLAYBACK_CHANGED", () => {
  const state = viewer.state;
  lifecycle = lifecycle
    .then(async () => {
      const response = await fetch(`state/${viewer.sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ protocolVersion: 1, state }),
        keepalive: true,
      });
      if (!response.ok)
        throw Error(
          `Lifecycle transport rejected ${state}: ${response.status}`,
        );
    })
    .catch((e) => {
      diagnostics.textContent += String(e) + "\n";
    });
});

for (const name of [
  "RUNTIME_ERROR",
  "RUNTIME_WARNING",
  "ANIMATION_EVENT",
  "ANIMATION_COMPLETE",
  "SESSION_DISPOSED",
])
  viewer.addEventListener(name, (e) => {
    const detail = (e as CustomEvent<object>).detail;
    diagnostics.textContent = (
      (diagnostics.textContent ?? "") + `${name}: ${JSON.stringify(detail)}\n`
    ).slice(-32000);
  });
const command = async (c: Command) => {
  const r: Request = {
    ...c,
    protocolVersion: 1,
    sessionId: viewer.sessionId,
    requestId: crypto.randomUUID(),
  };
  const reply = await viewer.request(r);
  if (!reply.success)
    diagnostics.textContent += JSON.stringify(reply.diagnostics) + "\n";
  status.textContent = JSON.stringify(viewer.info(), null, 2);
  return reply;
};
const click = (id: string, run: () => void | Promise<object | void>) =>
  element(id, HTMLButtonElement).addEventListener("click", () => {
    void run();
  });
const input = (id: string) => element(id, HTMLInputElement);
const animation = element("animation", HTMLSelectElement);
const skin = element("skin", HTMLSelectElement);
const updateControls = () => {
  if (window.parent !== window)
    window.parent.postMessage(
      {
        type: "FNX_VIEWER_STATE",
        sessionId: viewer.sessionId,
        state: viewer.state,
      },
      location.origin,
    );
  const active = ["READY", "PLAYING", "PAUSED", "STOPPED"].includes(
    viewer.state,
  );
  for (const control of document.querySelectorAll<
    HTMLButtonElement | HTMLInputElement | HTMLSelectElement
  >("#controls button,#controls input,#controls select"))
    control.disabled = !active && control.id !== "dispose";
  status.textContent = JSON.stringify(viewer.info(), null, 2);
};
viewer.addEventListener("PLAYBACK_CHANGED", updateControls);
viewer.addEventListener("VIEWER_UPDATED", () => {
  const info = viewer.info();
  if (info.animation) animation.value = info.animation;
  input("loop").checked = info.loop;
  input("speed").value = String(info.speed);
  if (document.activeElement !== input("time"))
    input("time").value = String(Number(info.animationTime.toFixed(4)));
  updateControls();
});
viewer.addEventListener("TIME_CHANGED", () => {
  status.textContent = JSON.stringify(viewer.info(), null, 2);
});
updateControls();
try {
  await viewer.load();
  element("identity", HTMLDivElement).textContent =
    `${assets.assetId} · export ${assets.exportVersion} · official ${assets.family}@${assets.runtimeRevision}`;
  for (const a of viewer.info().animations) {
    const option = new Option(`${a.name} (${a.duration.toFixed(3)}s)`, a.name);
    animation.add(option);
  }
  skin.add(new Option("Default skin", ""));
  for (const name of viewer.info().skins) skin.add(new Option(name, name));
  animation.value =
    viewer.info().animations.find((a) => a.duration > 0)?.name ??
    animation.value;
  if (animation.value)
    await command({
      command: "SET_ANIMATION",
      payload: { name: animation.value, mix: 0 },
    });
  status.textContent = JSON.stringify(viewer.info(), null, 2);
} catch (e) {
  diagnostics.textContent += String(e);
  status.textContent = viewer.state;
}
for (const [id, c] of [
  ["play", "PLAY"],
  ["pause", "PAUSE"],
  ["stop", "STOP"],
  ["fit", "RESET_CAMERA"],
  ["dispose", "DISPOSE"],
] as const)
  click(id, () => command({ command: c, payload: {} }));
click("restart", () =>
  command({
    command: "SET_ANIMATION",
    payload: { name: animation.value, mix: 0 },
  }),
);
click("step", () => command({ command: "STEP", payload: { seconds: 1 / 60 } }));
click("seek", () =>
  command({
    command: "SEEK",
    payload: { seconds: Number(input("time").value) },
  }),
);
animation.addEventListener(
  "change",
  () =>
    void command({
      command: "SET_ANIMATION",
      payload: { name: animation.value, mix: Number(input("mix").value) },
    }),
);
skin.addEventListener(
  "change",
  () =>
    void command({
      command: "SET_SKIN",
      payload: { name: skin.value || null },
    }),
);
input("loop").addEventListener(
  "change",
  () =>
    void command({
      command: "SET_LOOP",
      payload: { enabled: input("loop").checked },
    }),
);
input("debug").addEventListener(
  "change",
  () =>
    void command({
      command: "SET_DEBUG",
      payload: {
        ...cleanDebug(),
        bones: input("debug").checked,
        regions: input("debug").checked,
        meshTriangles: input("debug").checked,
        clipping: input("debug").checked,
      },
    }),
);
input("speed").addEventListener(
  "change",
  () =>
    void command({
      command: "SET_SPEED",
      payload: { scale: Number(input("speed").value) },
    }),
);
const download = (data: string, name: string) => {
  const a = document.createElement("a");
  a.href = data;
  a.download = name;
  a.click();
};
click("capture", async () => {
  try {
    const capture = await viewer.captureFrame();
    download(capture.png, `frame-${capture.sha256}.png`);
  } catch (e) {
    diagnostics.textContent += String(e);
  }
});
click("pose", () => {
  download(
    `data:application/json,${encodeURIComponent(JSON.stringify(viewer.capturePose(), null, 2))}`,
    "pose.json",
  );
});
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const camera = viewer.info().camera;
    camera.zoom = Math.min(
      100,
      Math.max(0.01, camera.zoom * Math.exp(e.deltaY * 0.001)),
    );
    void command({ command: "SET_CAMERA", payload: camera });
  },
  { passive: false },
);
let drag: { x: number; y: number } | null = null;
canvas.addEventListener("pointerdown", (e) => {
  drag = { x: e.clientX, y: e.clientY };
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointerup", () => {
  drag = null;
});
canvas.addEventListener("pointercancel", () => {
  drag = null;
});
canvas.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const camera = viewer.info().camera;
  camera.x -=
    ((e.clientX - drag.x) * camera.width * camera.zoom) / canvas.clientWidth;
  camera.y +=
    ((e.clientY - drag.y) * camera.height * camera.zoom) / canvas.clientHeight;
  drag = { x: e.clientX, y: e.clientY };
  void command({ command: "SET_CAMERA", payload: camera });
});
window.addEventListener("pagehide", () => viewer.dispose(), { once: true });

canvas.tabIndex = 0;
canvas.setAttribute(
  "aria-label",
  "Animation canvas. Arrow keys pan, plus and minus zoom, zero resets the camera.",
);
canvas.addEventListener("keydown", (e) => {
  const c = viewer.info().camera;
  const step = c.width * 0.05 * c.zoom;
  switch (e.key) {
    case "ArrowLeft":
      c.x -= step;
      break;
    case "ArrowRight":
      c.x += step;
      break;
    case "ArrowUp":
      c.y += step;
      break;
    case "ArrowDown":
      c.y -= step;
      break;
    case "+":
    case "=":
      c.zoom = Math.max(0.01, c.zoom / 1.1);
      break;
    case "-":
      c.zoom = Math.min(100, c.zoom * 1.1);
      break;
    case "0":
      void command({ command: "RESET_CAMERA", payload: {} });
      return;
    default:
      return;
  }
  e.preventDefault();
  void command({ command: "SET_CAMERA", payload: c });
});

const background = document.createElement("select");
background.setAttribute("aria-label", "Canvas background");
for (const [label, value] of [
  ["Transparent", "transparent"],
  ["Dark", "dark"],
  ["White", "white"],
] as const)
  background.add(new Option(label, value));
element("controls", HTMLDivElement).append(background);
background.addEventListener("change", () => {
  const value = background.value;
  void command({
    command: "SET_BACKGROUND",
    payload: {
      rgba:
        value === "white"
          ? [1, 1, 1, 1]
          : value === "dark"
            ? [0.08, 0.08, 0.08, 1]
            : [0, 0, 0, 0],
    },
  });
});
