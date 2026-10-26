import type {
  Camera,
  Capture,
  Command,
  Info,
  Pose,
  Reply,
  Request,
  Viewport,
} from "./contracts";
import { ViewerError } from "./diagnostics";
export interface ViewerPort {
  sessionId: string;
  request(request: Request): Promise<Reply>;
}
export interface PoseDifference {
  matchedBones: number;
  missingLeft: string[];
  missingRight: string[];
  incompatibleParents: string[];
  maximumWorldError: number | null;
  slotAttachmentDifferences: string[];
  drawOrderMatches: boolean;
}
export interface PairedCapture {
  status: "FRAMES_CAPTURED_NOT_VISUALLY_VERIFIED";
  left: Capture;
  right: Capture;
  animation: string;
  normalizedTime: number;
  leftDuration: number;
  rightDuration: number;
  durationDifference: number;
  pose: PoseDifference;
}
async function command(port: ViewerPort, request: Command): Promise<Reply> {
  const reply = await port.request({
    ...request,
    protocolVersion: 1,
    sessionId: port.sessionId,
    requestId: crypto.randomUUID(),
  });
  if (!reply.success)
    throw new ViewerError(
      "VISUAL_COMPARISON_UNAVAILABLE",
      reply.diagnostics.map((d) => d.message).join("; "),
    );
  return reply;
}
async function info(port: ViewerPort): Promise<Info> {
  const r = await command(port, { command: "GET_RUNTIME_INFO", payload: {} });
  if (!r.success || !r.result || !("animations" in r.result))
    throw new ViewerError("INVALID_PROTOCOL_REQUEST");
  return r.result;
}
async function capture(port: ViewerPort): Promise<Capture> {
  const r = await command(port, { command: "CAPTURE_FRAME", payload: {} });
  if (!r.success || !r.result || !("png" in r.result))
    throw new ViewerError("FRAME_CAPTURE_FAILED");
  return r.result;
}
export function comparePoses(a: Pose, b: Pose): PoseDifference {
  const left = new Map(a.bones.map((bone) => [bone.name, bone])),
    right = new Map(b.bones.map((bone) => [bone.name, bone]));
  const missingLeft = [...right.keys()].filter((n) => !left.has(n)),
    missingRight = [...left.keys()].filter((n) => !right.has(n));
  const incompatibleParents: string[] = [];
  let matchedBones = 0;
  let maximumWorldError: number | null = null;
  for (const [name, bone] of left) {
    const other = right.get(name);
    if (!other) continue;
    if (bone.parent !== other.parent) {
      incompatibleParents.push(name);
      continue;
    }
    matchedBones++;
    for (let i = 0; i < bone.world.length; i++) {
      const value = other.world[i];
      if (value === undefined || !Number.isFinite(value))
        throw new ViewerError("NON_FINITE_POSE");
      maximumWorldError = Math.max(
        maximumWorldError ?? 0,
        Math.abs((bone.world[i] ?? 0) - value),
      );
    }
  }
  const rightSlots = new Map(b.slots.map((s) => [s.name, s]));
  const slotAttachmentDifferences = a.slots
    .filter((s) => {
      const other = rightSlots.get(s.name);
      return (
        !other || s.attachment !== other.attachment || s.type !== other.type
      );
    })
    .map((s) => s.name);
  for (const slot of b.slots)
    if (!a.slots.some((s) => s.name === slot.name))
      slotAttachmentDifferences.push(slot.name);
  return {
    matchedBones,
    missingLeft,
    missingRight,
    incompatibleParents,
    maximumWorldError,
    slotAttachmentDifferences,
    drawOrderMatches:
      JSON.stringify(a.drawOrder) === JSON.stringify(b.drawOrder),
  };
}
export class ComparisonSession {
  private playback: Promise<void> | null = null;
  private playing = false;
  async stop(): Promise<void> {
    this.playing = false;
    await this.playback;
    this.playback = null;
  }
  async play(
    animation: string,
    viewport: Viewport,
    camera: Camera,
  ): Promise<void> {
    await this.stop();
    const initial = await this.capture(animation, 0, viewport, camera);
    if (initial.leftDuration <= 0 || initial.rightDuration <= 0)
      throw new ViewerError(
        "VISUAL_COMPARISON_UNAVAILABLE",
        "Both animations need nonzero durations for synchronized playback.",
      );
    this.playing = true;
    this.playback = (async () => {
      let normalized = 0;
      let previous = performance.now();
      try {
        while (this.playing) {
          await new Promise<void>((resolve) => setTimeout(resolve, 1000 / 30));
          if (!this.playing) break;
          const now = performance.now();
          normalized =
            (normalized +
              Math.min(0.05, (now - previous) / 1000) / initial.leftDuration) %
            1;
          previous = now;
          await Promise.all([
            command(this.left, {
              command: "SEEK",
              payload: { seconds: normalized * initial.leftDuration },
            }),
            command(this.right, {
              command: "SEEK",
              payload: { seconds: normalized * initial.rightDuration },
            }),
          ]);
        }
      } finally {
        this.playing = false;
      }
    })();
    // The promise remains observable by stop(); prevent an unhandled rejection when
    // a host closes one side before calling stop.
    void this.playback.catch(() => {});
  }
  constructor(
    readonly left: ViewerPort,
    readonly right: ViewerPort,
  ) {
    if (left === right || left.sessionId === right.sessionId)
      throw new ViewerError(
        "VISUAL_COMPARISON_UNAVAILABLE",
        "Select two independent sessions.",
      );
  }
  async animations(): Promise<string[]> {
    const [a, b] = await Promise.all([info(this.left), info(this.right)]);
    return a.animations
      .filter((x) => b.animations.some((y) => x.name === y.name))
      .map((x) => x.name);
  }
  async capture(
    animation: string,
    normalizedTime: number,
    viewport: Viewport,
    camera: Camera,
  ): Promise<PairedCapture> {
    if (
      !Number.isFinite(normalizedTime) ||
      normalizedTime < 0 ||
      normalizedTime > 1
    )
      throw new ViewerError("INVALID_PROTOCOL_REQUEST");
    const [a, b] = await Promise.all([info(this.left), info(this.right)]);
    const aa = a.animations.find((x) => x.name === animation),
      bb = b.animations.find((x) => x.name === animation);
    if (!aa || !bb)
      throw new ViewerError(
        "VISUAL_COMPARISON_UNAVAILABLE",
        "Animation must exist on both sides.",
      );
    for (const port of [this.left, this.right]) {
      await command(port, { command: "PAUSE", payload: {} });
      await command(port, { command: "SET_VIEWPORT", payload: viewport });
      await command(port, { command: "SET_CAMERA", payload: camera });
      await command(port, { command: "SET_LOOP", payload: { enabled: false } });
      await command(port, {
        command: "SET_DEBUG",
        payload: {
          bones: false,
          regions: false,
          meshTriangles: false,
          meshHull: false,
          clipping: false,
          boundingBoxes: false,
          paths: false,
          origin: false,
          bounds: false,
        },
      });
      await command(port, {
        command: "SET_BACKGROUND",
        payload: { rgba: [0, 0, 0, 0] },
      });
      await command(port, {
        command: "SET_ANIMATION",
        payload: { name: animation, mix: 0 },
      });
    }
    await Promise.all([
      command(this.left, {
        command: "SEEK",
        payload: { seconds: aa.duration * normalizedTime },
      }),
      command(this.right, {
        command: "SEEK",
        payload: { seconds: bb.duration * normalizedTime },
      }),
    ]);
    const [left, right] = await Promise.all([
      capture(this.left),
      capture(this.right),
    ]);
    return {
      status: "FRAMES_CAPTURED_NOT_VISUALLY_VERIFIED",
      left,
      right,
      animation,
      normalizedTime,
      leftDuration: aa.duration,
      rightDuration: bb.duration,
      durationDifference: bb.duration - aa.duration,
      pose: comparePoses(left.pose, right.pose),
    };
  }
}
export interface PixelMetrics {
  changedPixels: number;
  changedFraction: number;
  meanAbsoluteError: number;
  maximumChannelError: number;
  alphaChangedPixels: number;
  alphaMeanError: number;
}
export function pixelMetrics(
  a: Uint8ClampedArray,
  b: Uint8ClampedArray,
  tolerance = 8,
): PixelMetrics {
  if (a.length !== b.length || a.length === 0 || a.length % 4 !== 0)
    throw new ViewerError(
      "VISUAL_COMPARISON_UNAVAILABLE",
      "Incompatible pixel buffers.",
    );
  let changedPixels = 0,
    total = 0,
    maximumChannelError = 0,
    alphaChangedPixels = 0,
    alphaTotal = 0;
  for (let i = 0; i < a.length; i += 4) {
    let changed = false;
    for (let c = 0; c < 4; c++) {
      const error = Math.abs((a[i + c] ?? 0) - (b[i + c] ?? 0));
      total += error;
      maximumChannelError = Math.max(maximumChannelError, error);
      if (error > tolerance) changed = true;
      if (c === 3) {
        alphaTotal += error;
        if (error > tolerance) alphaChangedPixels++;
      }
    }
    if (changed) changedPixels++;
  }
  return {
    changedPixels,
    changedFraction: changedPixels / (a.length / 4),
    meanAbsoluteError: total / a.length,
    maximumChannelError,
    alphaChangedPixels,
    alphaMeanError: alphaTotal / (a.length / 4),
  };
}
export async function drawDifference(
  pair: PairedCapture,
  canvas: HTMLCanvasElement,
  overlay = false,
): Promise<PixelMetrics> {
  const { left, right } = pair;
  if (
    left.width !== right.width ||
    left.height !== right.height ||
    JSON.stringify(left.camera) !== JSON.stringify(right.camera) ||
    JSON.stringify(left.background) !== JSON.stringify(right.background)
  )
    throw new ViewerError(
      "VISUAL_COMPARISON_UNAVAILABLE",
      "Capture normalization differs.",
    );
  const decode = async (c: Capture) => {
    const bytes = Uint8Array.from(atob(c.png.split(",")[1] ?? ""), (v) =>
      v.charCodeAt(0),
    );
    return await createImageBitmap(new Blob([bytes]));
  };
  const a = await decode(left),
    b = await decode(right);
  try {
    canvas.width = left.width;
    canvas.height = left.height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new ViewerError("FRAME_CAPTURE_FAILED");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(a, 0, 0);
    const aa = ctx.getImageData(0, 0, canvas.width, canvas.height);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(b, 0, 0);
    const bb = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const metrics = pixelMetrics(aa.data, bb.data);
    const out = ctx.createImageData(canvas.width, canvas.height);
    for (let i = 0; i < out.data.length; i += 4) {
      const alphaError = Math.abs(
        (aa.data[i + 3] ?? 0) - (bb.data[i + 3] ?? 0),
      );
      for (let c = 0; c < 3; c++)
        out.data[i + c] = overlay
          ? Math.round(((aa.data[i + c] ?? 0) + (bb.data[i + c] ?? 0)) / 2)
          : Math.max(
              alphaError,
              Math.abs((aa.data[i + c] ?? 0) - (bb.data[i + c] ?? 0)),
            );
      out.data[i + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    return metrics;
  } finally {
    a.close();
    b.close();
  }
}
