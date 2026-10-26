import { test, expect } from "@playwright/test";
import { RealtimeClock, simulationSteps } from "../src/clock";
import { requestSchema } from "../src/protocol";
import { pixelMetrics, comparePoses } from "../src/comparison";
import {
  AnimationState,
  AnimationStateData,
  SkeletonJson,
  Skeleton,
  Physics,
  AtlasAttachmentLoader,
  TextureAtlas,
} from "spine42";
import type { Pose } from "../src/contracts";
test("clock bounds suspension and resets without a jump", () => {
  const c = new RealtimeClock();
  expect(c.delta(100)).toBe(0);
  expect(c.delta(100100)).toBe(0.05);
  c.reset();
  expect(c.delta(500000)).toBe(0);
  expect(c.delta(499999)).toBe(0);
});
test("fixed clock retains fractional remainder and rejects excessive work", () => {
  expect(simulationSteps(1).whole).toBe(60);
  expect(simulationSteps(0.025).remainder).toBeCloseTo(0.025 - 1 / 60);
  for (const n of [-1, Infinity, NaN, 601])
    expect(() => simulationSteps(n)).toThrow();
});
test("protocol rejects arbitrary commands, surplus keys and non-finite data", () => {
  const base = { protocolVersion: 1, sessionId: "s", requestId: "r" };
  expect(
    requestSchema.safeParse({ ...base, command: "PLAY", payload: {} }).success,
  ).toBe(true);
  for (const bad of [
    { command: "eval", payload: {} },
    { command: "PLAY", payload: { code: "x" } },
    { command: "SEEK", payload: { seconds: NaN } },
    { command: "SET_LOOP", payload: { enabled: 1 } },
    { command: "SET_ANIMATION", payload: { name: "x", mix: -1 } },
  ])
    expect(requestSchema.safeParse({ ...base, ...bad }).success).toBe(false);
});
test("image metrics retain alpha differences and configurable tolerance", () => {
  const a = new Uint8ClampedArray([20, 30, 40, 255, 0, 0, 0, 0]),
    b = new Uint8ClampedArray([25, 30, 40, 255, 0, 0, 0, 30]);
  const m = pixelMetrics(a, b, 8);
  expect(m.changedPixels).toBe(1);
  expect(m.alphaChangedPixels).toBe(1);
  expect(m.maximumChannelError).toBe(30);
  expect(m.meanAbsoluteError).toBe(35 / 8);
  expect(() => pixelMetrics(a, new Uint8ClampedArray(4))).toThrow();
});
test("pose comparison does not compare bones with different parents", () => {
  const base: Pose = {
    runtime: "x",
    exportVersion: "4.2.43",
    bones: [{ name: "b", parent: null, local: [], world: [1, 2, 1, 0, 0, 1] }],
    slots: [],
    drawOrder: [],
    skin: null,
    tracks: [],
    constraints: [],
    unsupportedInspection: [],
    animation: null,
    time: 0,
    clock: "setup",
    eventsDuringSeek: "suppressed",
  };
  const other = {
    ...base,
    bones: [{ ...base.bones[0]!, parent: "different" }],
  };
  expect(comparePoses(base, other).matchedBones).toBe(0);
  expect(comparePoses(base, other).maximumWorldError).toBeNull();
});
test("real official runtime updates a synthetic no-attachment animation", () => {
  const loader = new AtlasAttachmentLoader(new TextureAtlas(""));
  const data = new SkeletonJson(loader).readSkeletonData({
    skeleton: { spine: "4.2.43" },
    bones: [{ name: "root" }],
    slots: [],
    animations: {
      move: { bones: { root: { translate: [{ x: 0 }, { time: 1, x: 100 }] } } },
    },
  });
  const skeleton = new Skeleton(data),
    state = new AnimationState(new AnimationStateData(data));
  state.setAnimation(0, "move", false);
  state.update(0.5);
  state.apply(skeleton);
  skeleton.updateWorldTransform(Physics.update);
  expect(skeleton.bones[0]?.worldX).toBeCloseTo(50);
});
