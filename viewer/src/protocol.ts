import { z } from "zod";
const number = z.number().finite();
export const cameraSchema = z
  .object({
    x: number.min(-1e9).max(1e9),
    y: number.min(-1e9).max(1e9),
    width: number.min(1e-9).max(1e9),
    height: number.min(1e-9).max(1e9),
    zoom: number.min(0.01).max(100),
  })
  .strict();
export const viewportSchema = z
  .object({
    width: number.int().min(1).max(4096),
    height: number.int().min(1).max(4096),
    pixelRatio: number.min(0.25).max(3),
  })
  .strict()
  .refine(
    (v) => v.width * v.height * v.pixelRatio * v.pixelRatio <= 16777216,
    "Viewport exceeds 16 million pixels",
  );
export const debugSchema = z
  .object({
    bones: z.boolean(),
    regions: z.boolean(),
    meshTriangles: z.boolean(),
    meshHull: z.boolean(),
    clipping: z.boolean(),
    boundingBoxes: z.boolean(),
    paths: z.boolean(),
    origin: z.boolean(),
    bounds: z.boolean(),
  })
  .strict();
export const backgroundSchema = z
  .object({
    rgba: z.tuple([
      number.min(0).max(1),
      number.min(0).max(1),
      number.min(0).max(1),
      number.min(0).max(1),
    ]),
  })
  .strict();
const empty = z.object({}).strict();
const variant = <T extends string, P extends z.ZodType>(
  command: T,
  payload: P,
) =>
  z
    .object({
      protocolVersion: z.literal(1),
      sessionId: z.string().min(1).max(128),
      requestId: z.string().min(1).max(128),
      command: z.literal(command),
      payload,
    })
    .strict();
export const requestSchema = z.discriminatedUnion("command", [
  variant("PLAY", empty),
  variant("PAUSE", empty),
  variant("RESUME", empty),
  variant("STOP", empty),
  variant("CAPTURE_POSE", empty),
  variant("CAPTURE_FRAME", empty),
  variant("DISPOSE", empty),
  variant("GET_RUNTIME_INFO", empty),
  variant("RESET_CAMERA", empty),
  variant("SEEK", z.object({ seconds: number.min(0).max(600) }).strict()),
  variant("STEP", z.object({ seconds: number.min(0).max(1) }).strict()),
  variant(
    "SET_ANIMATION",
    z
      .object({ name: z.string().min(1).max(1024), mix: number.min(0).max(10) })
      .strict(),
  ),
  variant(
    "SET_SKIN",
    z.object({ name: z.string().max(1024).nullable() }).strict(),
  ),
  variant("SET_SPEED", z.object({ scale: number.min(0).max(4) }).strict()),
  variant("SET_LOOP", z.object({ enabled: z.boolean() }).strict()),
  variant("SET_DEBUG", debugSchema),
  variant("SET_CAMERA", cameraSchema),
  variant("SET_VIEWPORT", viewportSchema.nullable()),
  variant("SET_BACKGROUND", backgroundSchema),
]);
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const assetsSchema = z
  .object({
    sessionId: z.string().min(1).max(128),
    assetId: z.string(),
    family: z.enum(["3.8", "4.0", "4.1", "4.2", "4.3"]),
    exportVersion: z.string(),
    runtimeRevision: z.string(),
    skeleton: z.string(),
    atlas: z.string(),
    pages: z.record(
      z.string(),
      z
        .object({
          url: z.string(),
          sha256: hash,
          width: number.int().positive().max(8192),
          height: number.int().positive().max(8192),
          pma: z.boolean(),
        })
        .strict(),
    ),
    binary: z.boolean(),
    sourceRisk: z.boolean(),
    checksums: z.record(z.string(), hash),
    resourceHashes: z.record(z.string(), hash),
    conversionQualification: z.literal("UNCHANGED_NOT_INFERRED_FROM_PLAYBACK"),
  })
  .strict();
