import type { DiagnosticCode } from "./diagnostics";
export type Family = keyof typeof import("./generated/revisions").revisions;
export interface TextureResource {
  url: string;
  sha256: string;
  width: number;
  height: number;
  pma: boolean;
}
export interface Assets {
  assetId: string;
  sessionId: string;
  family: Family;
  exportVersion: string;
  runtimeRevision: string;
  skeleton: string;
  atlas: string;
  pages: Record<string, TextureResource>;
  binary: boolean;
  sourceRisk: boolean;
  checksums: Record<string, string>;
  resourceHashes: Record<string, string>;
  conversionQualification: "UNCHANGED_NOT_INFERRED_FROM_PLAYBACK";
}
export type RGBA = [red: number, green: number, blue: number, alpha: number];
export type LocalTransform = [
  x: number,
  y: number,
  rotation: number,
  scaleX: number,
  scaleY: number,
  shearX: number,
  shearY: number,
];
export type WorldTransform = [
  x: number,
  y: number,
  a: number,
  b: number,
  c: number,
  d: number,
];
export interface BonePose {
  name: string;
  parent: string | null;
  local: LocalTransform;
  world: WorldTransform;
}
export type AttachmentType =
  | "region"
  | "mesh"
  | "clipping"
  | "boundingbox"
  | "path"
  | "point"
  | "unsupported";
export interface SlotPose {
  name: string;
  bone: string;
  attachment: string | null;
  type: AttachmentType | null;
  color: RGBA;
  darkColor: RGBA | null;
  worldVertices: number[];
  triangles: number[];
  influenceBones: number[] | null;
  influenceVertices: number[] | null;
}
export interface TrackPose {
  trackIndex: number;
  animation: string | null;
  trackTime: number;
  animationTime: number;
  loop: boolean;
  mixTime: number;
  mixDuration: number;
}
export interface ConstraintPose {
  name: string;
  type: "ik" | "transform" | "path" | "physics";
  values: Record<string, number | boolean>;
}
export interface KernelPose {
  bones: BonePose[];
  slots: SlotPose[];
  drawOrder: string[];
  skin: string | null;
  tracks: TrackPose[];
  constraints: ConstraintPose[];
  unsupportedInspection: string[];
}
export interface Pose extends KernelPose {
  runtime: string;
  exportVersion: string;
  animation: string | null;
  time: number;
  clock: "setup" | "realtime" | "fixed-1/60";
  eventsDuringSeek: "suppressed";
}
export interface AnimationInfo {
  name: string;
  duration: number;
}
export interface AnimationEvent {
  name: string;
  time: number;
  trackTime: number;
  int: number;
  float: number;
  string: string | null;
  audioPath: string | null;
  volume: number;
  balance: number;
}
export interface Camera {
  x: number;
  y: number;
  width: number;
  height: number;
  zoom: number;
}
export interface Viewport {
  width: number;
  height: number;
  pixelRatio: number;
}
export interface DebugOptions {
  bones: boolean;
  regions: boolean;
  meshTriangles: boolean;
  meshHull: boolean;
  clipping: boolean;
  boundingBoxes: boolean;
  paths: boolean;
  origin: boolean;
  bounds: boolean;
}
export interface RuntimeStatistics {
  loadMs: number;
  textureUploadMs: number;
  textureCount: number;
  texturePixels: number;
  frames: number;
  updateMs: number;
  renderMs: number;
}
export interface Kernel {
  animations: AnimationInfo[];
  skins: string[];
  pma: boolean;
  statistics: RuntimeStatistics;
  reset(skin: string | null): void;
  animate(name: string, loop: boolean, mix: number): void;
  advance(delta: number, events: boolean): AnimationEvent[];
  pose(): KernelPose;
  bounds(): { x: number; y: number; width: number; height: number };
  render(
    camera: Camera,
    background: [number, number, number, number],
    debug: DebugOptions,
  ): void;
  dispose(): void;
}
export type KernelFactory = (
  canvas: HTMLCanvasElement,
  assets: Assets,
  signal: AbortSignal,
) => Promise<Kernel>;
export interface Capture {
  png: string;
  sha256: string;
  width: number;
  height: number;
  dpr: number;
  camera: Camera;
  background: RGBA;
  pma: boolean;
  debug: DebugOptions;
  pose: Pose;
  colorSpace: "srgb";
  antialias: false;
}
export type Command =
  | {
      command:
        | "PLAY"
        | "PAUSE"
        | "RESUME"
        | "STOP"
        | "CAPTURE_POSE"
        | "CAPTURE_FRAME"
        | "DISPOSE"
        | "GET_RUNTIME_INFO"
        | "RESET_CAMERA";
      payload: Record<string, never>;
    }
  | { command: "SEEK" | "STEP"; payload: { seconds: number } }
  | { command: "SET_ANIMATION"; payload: { name: string; mix: number } }
  | { command: "SET_SKIN"; payload: { name: string | null } }
  | { command: "SET_SPEED"; payload: { scale: number } }
  | { command: "SET_LOOP"; payload: { enabled: boolean } }
  | { command: "SET_DEBUG"; payload: DebugOptions }
  | { command: "SET_CAMERA"; payload: Camera }
  | { command: "SET_VIEWPORT"; payload: Viewport | null }
  | {
      command: "SET_BACKGROUND";
      payload: { rgba: [number, number, number, number] };
    };
export type Request = Command & {
  protocolVersion: 1;
  sessionId: string;
  requestId: string;
};
export interface Diagnostic {
  code: DiagnosticCode;
  severity: "error" | "warning";
  family: Family;
  assetId: string;
  filename: string | null;
  context: string;
  message: string;
  action: string;
}
export type Reply =
  | {
      protocolVersion: 1;
      sessionId: string;
      requestId: string;
      success: true;
      result: Pose | Capture | Info | null;
      diagnostics: Diagnostic[];
    }
  | {
      protocolVersion: 1;
      sessionId: string;
      requestId: string;
      success: false;
      result: null;
      diagnostics: Diagnostic[];
    };
export interface Info {
  state: ViewerState;
  family: Family;
  revision: string;
  exportVersion: string;
  animations: AnimationInfo[];
  skins: string[];
  animation: string | null;
  time: number;
  animationTime: number;
  duration: number;
  progress: number;
  loop: boolean;
  speed: number;
  camera: Camera;
  statistics: RuntimeStatistics | null;
  limitations: readonly string[];
}

export type ViewerState =
  | "CREATED"
  | "LOADING_RUNTIME"
  | "LOADING_ASSETS"
  | "INITIALIZING"
  | "READY"
  | "PLAYING"
  | "PAUSED"
  | "STOPPED"
  | "SEEKING"
  | "FAILED"
  | "DISPOSING"
  | "DISPOSED";
export interface ViewerEventMap {
  LOAD_STARTED: { sessionId: string };
  RUNTIME_READY: { family: Family; revision: string };
  ASSETS_LOADED: { pages: string[] };
  VIEWER_READY: Info;
  VIEWER_UPDATED: Info;
  PLAYBACK_CHANGED: { state: ViewerState; sessionId: string };
  ANIMATION_EVENT: AnimationEvent;
  ANIMATION_COMPLETE: { animation: string | null; time: number };
  TIME_CHANGED: { time: number; animationTime: number };
  FRAME_CAPTURED: Omit<Capture, "png">;
  RUNTIME_WARNING: Diagnostic;
  RUNTIME_ERROR: Diagnostic;
  SESSION_DISPOSED: { sessionId: string };
}
export type ViewerEvent = {
  [Name in keyof ViewerEventMap]: [event: Name, detail: ViewerEventMap[Name]];
}[keyof ViewerEventMap];
export type ViewerEventListener = (event: ViewerEvent) => void;
