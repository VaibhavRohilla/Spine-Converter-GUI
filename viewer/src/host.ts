import { assetsSchema } from "./protocol";
import { ComparisonSession, drawDifference } from "./comparison";
import type { SpineViewer } from "./viewer";
const assets = assetsSchema
  .array()
  .parse(await (await fetch("sessions.json")).json());
const host = document.querySelector("#sessions");
const viewers: HTMLIFrameElement[] = [];
const selection = new URLSearchParams(location.search);
for (let i = 0; i < Math.min(2, assets.length); i++) {
  const frame = document.createElement("iframe");
  frame.src = `frame.html?index=${Number(selection.get(i === 0 ? "left" : "right") ?? i)}`;
  frame.title = `Independent runtime session ${i}`;
  host?.append(frame);
  viewers.push(frame);
}
const controls = document.createElement("section");
controls.id = "comparison";
const left = document.createElement("select"),
  right = document.createElement("select");
left.setAttribute("aria-label", "Original session");
right.setAttribute("aria-label", "Converted session");
assets.forEach((asset, i) => {
  for (const select of [left, right])
    select.add(
      new Option(`${i + 1}: ${asset.assetId} (${asset.family})`, String(i)),
    );
});
left.selectedIndex = Number(selection.get("left") ?? 0);
right.selectedIndex = Number(
  selection.get("right") ?? Math.min(1, assets.length - 1),
);
const animation = document.createElement("select");
animation.setAttribute("aria-label", "Shared animation");
const time = document.createElement("input");
time.type = "number";
time.min = "0";
time.max = "1";
time.step = ".1";
time.value = ".5";
time.setAttribute("aria-label", "Normalized comparison time");
const prepare = document.createElement("button");
prepare.textContent = "Find shared animations";
prepare.disabled = true;
const capture = document.createElement("button");
capture.textContent = "Capture pair and difference";
capture.disabled = true;
const output = document.createElement("pre");
output.setAttribute("role", "status");
const canvas = document.createElement("canvas");
canvas.id = "difference";
canvas.hidden = true;
controls.append(left, right, prepare, animation, time, capture, output, canvas);
document.querySelector("header")?.after(controls);
function port(index: number): SpineViewer {
  const v = viewers[index]?.contentWindow?.fnxViewer;
  if (!v) throw Error("Wait for both viewer sessions to load.");
  return v;
}
let comparison: ComparisonSession | null = null;
prepare.addEventListener("click", () => {
  void (async () => {
    try {
      comparison = new ComparisonSession(port(0), port(1));
      animation.replaceChildren();
      for (const name of await comparison.animations())
        animation.add(new Option(name, name));
      capture.disabled = animation.options.length === 0;
      output.textContent = capture.disabled
        ? "No matching animation names."
        : "Choose a normalized time. Duration differences are reported separately.";
    } catch (e) {
      capture.disabled = true;
      output.textContent = String(e);
    }
  })();
});
for (const [side, select] of [left, right].entries())
  select.addEventListener("change", () => {
    void comparison?.stop().catch(() => {});
    comparison = null;
    capture.disabled = true;
    prepare.disabled = true;
    const frame = viewers[side];
    if (frame) frame.src = `frame.html?index=${select.value}`;
  });
capture.addEventListener("click", () => {
  void (async () => {
    capture.disabled = true;
    try {
      if (!comparison) throw Error("Select a pair first.");
      await comparison.stop();
      const camera = port(0).info().camera;
      const pair = await comparison.capture(
        animation.value,
        Number(time.value),
        { width: 640, height: 640, pixelRatio: 1 },
        camera,
      );
      canvas.hidden = false;
      const metrics = await drawDifference(pair, canvas);
      output.textContent = JSON.stringify(
        {
          status: pair.status,
          leftDuration: pair.leftDuration,
          rightDuration: pair.rightDuration,
          durationDifference: pair.durationDifference,
          pose: pair.pose,
          metrics,
        },
        null,
        2,
      );
    } catch (e) {
      output.textContent = String(e);
    } finally {
      capture.disabled = false;
    }
  })();
});

function refreshPairAvailability() {
  prepare.disabled = !viewers.every((frame) => {
    const state = frame.contentWindow?.fnxViewer?.state;
    return state && ["READY", "PLAYING", "PAUSED", "STOPPED"].includes(state);
  });
}
for (const frame of viewers)
  frame.addEventListener("load", refreshPairAvailability);
refreshPairAvailability();

window.addEventListener("message", (event) => {
  if (
    event.origin !== location.origin ||
    !viewers.some((frame) => frame.contentWindow === event.source)
  )
    return;
  refreshPairAvailability();
});

const playPair = document.createElement("button");
playPair.textContent = "Play synchronized";
const pausePair = document.createElement("button");
pausePair.textContent = "Pause pair";
controls.insertBefore(playPair, output);
controls.insertBefore(pausePair, output);
playPair.addEventListener("click", () => {
  void (async () => {
    try {
      if (!comparison) throw Error("Find shared animations first.");
      await comparison.play(
        animation.value,
        { width: 640, height: 640, pixelRatio: 1 },
        port(0).info().camera,
      );
      output.textContent =
        "Synchronized normalized playback at sampled fixed-step poses; events suppressed. Durations remain independent.";
    } catch (e) {
      output.textContent = String(e);
    }
  })();
});
pausePair.addEventListener("click", () => {
  void comparison?.stop().catch((e) => {
    output.textContent = String(e);
  });
});
window.addEventListener(
  "pagehide",
  () => {
    void comparison?.stop().catch(() => {});
  },
  { once: true },
);
