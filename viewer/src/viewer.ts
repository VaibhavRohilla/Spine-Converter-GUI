import { revisions } from "./generated/revisions";
import type {
  Assets,
  Kernel,
  KernelFactory,
  Camera,
  Pose,
  Capture,
  Info,
  Request,
  Reply,
  Diagnostic,
  DebugOptions,
  Viewport,
  Command,
} from "./contracts";
import {
  requestSchema,
  assetsSchema,
  cameraSchema,
  viewportSchema,
  backgroundSchema,
  debugSchema,
} from "./protocol";
import { ViewerError, diagnostic, cancelled } from "./diagnostics";
import { sha256 } from "./resources";
import { RealtimeClock, FIXED_STEP, simulationSteps } from "./clock";
export type State =
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
const flow: Record<State, readonly State[]> = {
  CREATED: ["LOADING_RUNTIME"],
  LOADING_RUNTIME: ["LOADING_ASSETS"],
  LOADING_ASSETS: ["INITIALIZING"],
  INITIALIZING: ["READY"],
  READY: ["PLAYING", "PAUSED", "STOPPED", "SEEKING"],
  PLAYING: ["PAUSED", "STOPPED", "SEEKING"],
  PAUSED: ["PLAYING", "STOPPED", "SEEKING"],
  STOPPED: ["PLAYING", "PAUSED", "SEEKING"],
  SEEKING: ["PAUSED"],
  FAILED: ["LOADING_RUNTIME"],
  DISPOSING: ["DISPOSED"],
  DISPOSED: [],
};
const factories: Record<
  Assets["family"],
  () => Promise<{ createKernel: KernelFactory }>
> = {
  "3.8": () => import("./generated/kernel38"),
  "4.0": () => import("./generated/kernel40"),
  "4.1": () => import("./generated/kernel41"),
  "4.2": () => import("./generated/kernel42"),
  "4.3": () => import("./generated/kernel43"),
};
export const cleanDebug = (): DebugOptions => ({
  bones: false,
  regions: false,
  meshTriangles: false,
  meshHull: false,
  clipping: false,
  boundingBoxes: false,
  paths: false,
  origin: false,
  bounds: false,
});
export class SpineViewer extends EventTarget {
  private currentState: State = "CREATED";
  private kernel: Kernel | null = null;
  private abort = new AbortController();
  private frame = 0;
  private clock = new RealtimeClock();
  private epoch = 0;
  private animation: string | null = null;
  private skin: string | null = null;
  private time = 0;
  private loop = true;
  private speed = 1;
  private debug = cleanDebug();
  private camera: Camera = { x: 0, y: 0, width: 100, height: 100, zoom: 1 };
  private effectiveCamera = { ...this.camera };
  private baseBounds = { x: 0, y: 0, width: 100, height: 100 };
  private background: [number, number, number, number] = [0, 0, 0, 0];
  private viewport: Viewport | null = null;
  private resize: ResizeObserver;
  private clockPolicy: Pose["clock"] = "setup";
  private capturing = false;
  private lastTimeEvent = 0;
  readonly assets: Assets;
  get state(): State {
    return this.currentState;
  }
  private lost = (e: Event) => {
    e.preventDefault();
    this.fail(
      new ViewerError(
        "WEBGL_CONTEXT_LOST",
        "Graphics context lost. Resources were disposed. Retry after restoration or create a new view.",
      ),
    );
  };
  private restored = () =>
    this.notify("RUNTIME_WARNING", {
      code: "WEBGL_CONTEXT_LOST",
      message:
        "Context restored. Explicit load() retry is required; no stale playback is resumed.",
    });
  private visibility = () => this.clock.reset();
  constructor(
    readonly canvas: HTMLCanvasElement,
    assets: Assets,
    readonly sessionId: string,
  ) {
    super();
    this.assets = assetsSchema.parse(assets);
    if (sessionId !== this.assets.sessionId)
      throw new ViewerError("INVALID_PROTOCOL_REQUEST");
    this.resize = new ResizeObserver(() => {
      if (this.kernel && this.isUsable()) {
        try {
          this.render();
        } catch (e) {
          this.fail(e);
        }
      }
    });
    this.resize.observe(canvas);
    canvas.addEventListener("webglcontextlost", this.lost);
    canvas.addEventListener("webglcontextrestored", this.restored);
    document.addEventListener("visibilitychange", this.visibility);
  }
  private notify(type: string, detail: object) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }
  private transition(state: State) {
    if (state === this.currentState) return;
    const terminal = this.state === "DISPOSED" || this.state === "DISPOSING";
    if (
      !flow[this.state].includes(state) &&
      !(state === "DISPOSING" && !terminal) &&
      !(state === "FAILED" && !terminal)
    )
      throw new ViewerError(
        "INVALID_SESSION_STATE",
        `Illegal transition ${this.state} -> ${state}`,
      );
    this.currentState = state;
    this.notify("PLAYBACK_CHANGED", { state, sessionId: this.sessionId });
  }
  private fail(error: unknown) {
    if (this.state === "DISPOSED" || this.state === "DISPOSING") return;
    this.abort.abort();
    this.epoch++;
    cancelAnimationFrame(this.frame);
    this.clock.reset();
    this.kernel?.dispose();
    this.kernel = null;
    this.transition("FAILED");
    this.notify("RUNTIME_ERROR", diagnostic(error, this.assets));
  }
  async load(): Promise<void> {
    if (this.state !== "CREATED" && this.state !== "FAILED")
      throw new ViewerError("INVALID_SESSION_STATE");
    this.abort = new AbortController();
    const epoch = ++this.epoch;
    this.time = 0;
    this.animation = null;
    this.skin = null;
    this.clockPolicy = "setup";
    try {
      if (
        this.assets.exportVersion.split(".").slice(0, 2).join(".") !==
          this.assets.family ||
        this.assets.runtimeRevision !== revisions[this.assets.family]
      )
        throw new ViewerError("RUNTIME_VERSION_MISMATCH");
      if (this.assets.sourceRisk)
        this.notify("RUNTIME_WARNING", {
          ...diagnostic(
            new ViewerError(
              "SOURCE_EXPORT_KNOWN_BUG",
              "Original 3.8.75 playback is not established. Source metadata is preserved.",
            ),
            this.assets,
          ),
          severity: "warning",
        });
      this.transition("LOADING_RUNTIME");
      this.notify("LOAD_STARTED", { sessionId: this.sessionId });
      const module = await factories[this.assets.family]();
      cancelled(this.abort.signal);
      this.notify("RUNTIME_READY", {
        family: this.assets.family,
        revision: this.assets.runtimeRevision,
      });
      this.transition("LOADING_ASSETS");
      const kernel = await module.createKernel(
        this.canvas,
        this.assets,
        this.abort.signal,
      );
      if (this.abort.signal.aborted || epoch !== this.epoch) {
        kernel.dispose();
        throw new ViewerError("VIEWER_SESSION_CANCELLED");
      }
      this.kernel = kernel;
      this.notify("ASSETS_LOADED", { pages: Object.keys(this.assets.pages) });
      this.transition("INITIALIZING");
      this.baseBounds = kernel.bounds();
      this.fit();
      this.render();
      this.transition("READY");
      this.notify("VIEWER_READY", this.info());
    } catch (e) {
      if (epoch === this.epoch) this.fail(e);
      throw e;
    }
  }
  private isUsable() {
    return ["READY", "PLAYING", "PAUSED", "STOPPED"].includes(this.state);
  }
  private ready(): Kernel {
    if (!this.kernel || !this.isUsable())
      throw new ViewerError(
        "INVALID_SESSION_STATE",
        `Viewer is ${this.state}.`,
      );
    return this.kernel;
  }
  private duration() {
    return (
      this.kernel?.animations.find((a) => a.name === this.animation)
        ?.duration ?? 0
    );
  }
  info(): Info {
    return {
      state: this.state,
      family: this.assets.family,
      revision: this.assets.runtimeRevision,
      exportVersion: this.assets.exportVersion,
      animations: this.kernel?.animations ?? [],
      skins: this.kernel?.skins ?? [],
      animation: this.animation,
      time: this.time,
      animationTime: this.displayTime(),
      duration: this.duration(),
      progress: this.duration() ? this.displayTime() / this.duration() : 0,
      loop: this.loop,
      speed: this.speed,
      camera: { ...this.camera },
      statistics: this.kernel ? { ...this.kernel.statistics } : null,
      limitations: [
        "single animation track control",
        "seek discards mixing history",
        "deterministic results scoped to runtime, fixture and fixed-step policy",
        "GPU timing and heap ownership not inferred from frame timing",
      ],
    };
  }
  private displayTime() {
    const d = this.duration();
    return d ? (this.loop ? this.time % d : Math.min(d, this.time)) : 0;
  }
  private advance(delta: number, events: boolean) {
    const k = this.ready();
    if (!this.animation) throw new ViewerError("ANIMATION_NOT_FOUND");
    const bounded = this.loop
      ? delta
      : Math.max(0, Math.min(delta, this.duration() - this.time));
    for (const event of k.advance(bounded, events))
      this.notify("ANIMATION_EVENT", event);
    this.time += bounded;
    if (
      !this.loop &&
      this.time >= this.duration() &&
      this.state === "PLAYING"
    ) {
      this.pause();
      this.notify("ANIMATION_COMPLETE", {
        animation: this.animation,
        time: this.time,
      });
    }
  }
  private tick = (now: number) => {
    if (this.state !== "PLAYING") return;
    try {
      const delta = this.clock.delta(now);
      this.advance(delta * this.speed, true);
      this.clockPolicy = "realtime";
      this.render();
      if (now - this.lastTimeEvent > 100) {
        this.lastTimeEvent = now;
        this.notify("TIME_CHANGED", {
          time: this.time,
          animationTime: this.displayTime(),
        });
      }
      if (this.state === "PLAYING")
        this.frame = requestAnimationFrame(this.tick);
    } catch (e) {
      this.fail(e);
    }
  };
  async play() {
    const k = this.ready();
    if (this.state === "PLAYING") return;
    if (!this.animation) {
      const first = k.animations.find((a) => a.duration > 0) ?? k.animations[0];
      if (!first) throw new ViewerError("ANIMATION_NOT_FOUND");
      this.setAnimation(first.name, 0);
    }
    if (!this.loop && this.time >= this.duration()) await this.seek(0);
    this.ready();
    this.transition("PLAYING");
    this.clock.reset();
    this.frame = requestAnimationFrame(this.tick);
  }
  pause() {
    this.ready();
    cancelAnimationFrame(this.frame);
    this.clock.reset();
    if (this.state === "PLAYING") this.transition("PAUSED");
  }
  stop() {
    const k = this.ready();
    cancelAnimationFrame(this.frame);
    this.clock.reset();
    k.reset(this.skin);
    this.time = 0;
    this.animation = null;
    this.clockPolicy = "setup";
    this.transition("STOPPED");
    this.render();
  }
  setAnimation(name: string, mix: number) {
    const k = this.ready();
    if (!Number.isFinite(mix) || mix < 0 || mix > 10)
      throw new ViewerError("INVALID_PROTOCOL_REQUEST");
    if (!k.animations.some((a) => a.name === name))
      throw new ViewerError(
        "ANIMATION_NOT_FOUND",
        `No animation named ${name}.`,
      );
    if (mix === 0) k.reset(this.skin);
    k.animate(name, this.loop, mix);
    this.animation = name;
    this.time = 0;
    this.clock.reset();
    this.clockPolicy = "fixed-1/60";
    k.advance(0, false);
    this.render();
  }
  async seek(seconds: number) {
    const k = this.ready();
    if (!this.animation) throw new ViewerError("ANIMATION_NOT_FOUND");
    simulationSteps(seconds);
    const target = this.loop ? seconds : Math.min(seconds, this.duration());
    const steps = simulationSteps(target);
    this.pause();
    this.transition("SEEKING");
    const epoch = this.epoch;
    try {
      k.reset(this.skin);
      k.animate(this.animation, this.loop, 0);
      k.advance(0, false);
      for (let i = 0; i < steps.whole; i++) {
        k.advance(FIXED_STEP, false);
        if (i % 120 === 119) {
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
          cancelled(this.abort.signal);
          if (epoch !== this.epoch)
            throw new ViewerError("VIEWER_SESSION_CANCELLED");
        }
      }
      if (steps.remainder) k.advance(steps.remainder, false);
      cancelled(this.abort.signal);
      this.time = target;
      this.clock.reset();
      this.clockPolicy = "fixed-1/60";
      this.transition("PAUSED");
      this.render();
    } catch (e) {
      if (epoch === this.epoch) this.fail(e);
      throw e;
    }
  }
  step(seconds: number) {
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > 1)
      throw new ViewerError("INVALID_PROTOCOL_REQUEST");
    this.pause();
    const steps = simulationSteps(seconds);
    for (let i = 0; i < steps.whole; i++) this.advance(FIXED_STEP, false);
    if (steps.remainder) this.advance(steps.remainder, false);
    this.clockPolicy = "fixed-1/60";
    this.render();
  }
  async setSkin(name: string | null) {
    const k = this.ready();
    if (name !== null && !k.skins.includes(name))
      throw new ViewerError("SKIN_NOT_FOUND", `No skin named ${name}.`);
    this.pause();
    this.skin = name;
    k.reset(name);
    if (this.animation) await this.seek(this.time);
    else this.render();
  }
  private fit() {
    const b = this.baseBounds;
    this.camera = {
      x: b.x + b.width / 2,
      y: b.y + b.height / 2,
      width: Math.max(1, b.width) * 1.15,
      height: Math.max(1, b.height) * 1.15,
      zoom: 1,
    };
  }
  resetCamera() {
    this.ready();
    this.fit();
    this.render();
  }
  setCamera(camera: Camera) {
    this.ready();
    this.camera = cameraSchema.parse(camera);
    this.render();
  }
  setViewport(viewport: Viewport | null) {
    this.ready();
    this.viewport = viewport === null ? null : viewportSchema.parse(viewport);
    this.render();
  }
  setDebug(debug: DebugOptions) {
    this.ready();
    this.debug = debugSchema.parse(debug);
    this.render();
  }
  setBackground(rgba: [number, number, number, number]) {
    this.ready();
    this.background = backgroundSchema.parse({ rgba }).rgba;
    this.render();
  }
  render() {
    const k = this.kernel;
    if (!k) return;
    const dpr = this.viewport?.pixelRatio ?? Math.min(devicePixelRatio, 3);
    const w = Math.max(
      1,
      Math.round((this.viewport?.width ?? this.canvas.clientWidth) * dpr),
    );
    const h = Math.max(
      1,
      Math.round((this.viewport?.height ?? this.canvas.clientHeight) * dpr),
    );
    if (w * h > 16777216 || w > 8192 || h > 8192)
      throw new ViewerError(
        "VIEWER_RESOURCE_LIMIT_EXCEEDED",
        "Canvas exceeds capture limits.",
      );
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    const c = { ...this.camera };
    const aspect = w / h;
    if (c.width / c.height < aspect) c.width = c.height * aspect;
    else c.height = c.width / aspect;
    this.effectiveCamera = c;
    k.render(c, this.background, this.debug);
  }
  capturePose(): Pose {
    return {
      ...this.ready().pose(),
      runtime: `${this.assets.family}@${this.assets.runtimeRevision}`,
      exportVersion: this.assets.exportVersion,
      animation: this.animation,
      time: this.time,
      clock: this.clockPolicy,
      eventsDuringSeek: "suppressed",
    };
  }
  async captureFrame(): Promise<Capture> {
    this.ready();
    if (this.capturing)
      throw new ViewerError(
        "INVALID_SESSION_STATE",
        "A capture is already pending.",
      );
    this.capturing = true;
    const epoch = this.epoch;
    try {
      this.pause();
      this.render();
      const pose = this.capturePose();
      const png = this.canvas.toDataURL("image/png");
      if (!png.startsWith("data:image/png;base64,"))
        throw new ViewerError("FRAME_CAPTURE_FAILED");
      const metadata = {
        width: this.canvas.width,
        height: this.canvas.height,
        dpr: this.viewport?.pixelRatio ?? Math.min(devicePixelRatio, 3),
        camera: { ...this.effectiveCamera },
        background: [...this.background],
        pma: this.kernel?.pma ?? false,
        debug: { ...this.debug },
        pose,
        colorSpace: "srgb" as const,
        antialias: false as const,
      };
      const bytes = Uint8Array.from(atob(png.split(",")[1] ?? ""), (c) =>
        c.charCodeAt(0),
      );
      const digest = await sha256(bytes);
      cancelled(this.abort.signal);
      if (epoch !== this.epoch)
        throw new ViewerError("VIEWER_SESSION_CANCELLED");
      const result = { png, sha256: digest, ...metadata };
      this.notify("FRAME_CAPTURED", { ...metadata, sha256: digest });
      return result;
    } catch (e) {
      if (e instanceof ViewerError) throw e;
      throw new ViewerError("FRAME_CAPTURE_FAILED", String(e));
    } finally {
      this.capturing = false;
    }
  }
  dispose() {
    if (this.state === "DISPOSED") return;
    this.transition("DISPOSING");
    this.epoch++;
    this.abort.abort();
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.canvas.removeEventListener("webglcontextlost", this.lost);
    this.canvas.removeEventListener("webglcontextrestored", this.restored);
    document.removeEventListener("visibilitychange", this.visibility);
    this.kernel?.dispose();
    this.kernel = null;
    this.transition("DISPOSED");
    this.notify("SESSION_DISPOSED", { sessionId: this.sessionId });
  }
  async request(input: Request): Promise<Reply> {
    const parsed = requestSchema.safeParse(input);
    const base = {
      protocolVersion: 1 as const,
      sessionId: this.sessionId,
      requestId: input?.requestId ?? "invalid",
    };
    try {
      if (!parsed.success || parsed.data.sessionId !== this.sessionId)
        throw new ViewerError(
          "INVALID_PROTOCOL_REQUEST",
          parsed.success ? "Session ID differs." : parsed.error.message,
        );
      if (
        this.capturing &&
        !["DISPOSE", "GET_RUNTIME_INFO"].includes(parsed.data.command)
      )
        throw new ViewerError("INVALID_SESSION_STATE", "Capture is pending.");
      const result = await this.execute(parsed.data);
      this.notify("VIEWER_UPDATED", this.info());
      return { ...base, success: true, result, diagnostics: [] };
    } catch (e) {
      const d: Diagnostic = diagnostic(e, this.assets);
      return { ...base, success: false, result: null, diagnostics: [d] };
    }
  }
  private async execute(r: Command): Promise<Pose | Capture | Info | null> {
    switch (r.command) {
      case "PLAY":
      case "RESUME":
        await this.play();
        break;
      case "PAUSE":
        this.pause();
        break;
      case "STOP":
        this.stop();
        break;
      case "SEEK":
        await this.seek(r.payload.seconds);
        break;
      case "STEP":
        this.step(r.payload.seconds);
        break;
      case "SET_ANIMATION":
        this.setAnimation(r.payload.name, r.payload.mix);
        break;
      case "SET_SKIN":
        await this.setSkin(r.payload.name);
        break;
      case "SET_SPEED":
        this.ready();
        this.speed = r.payload.scale;
        break;
      case "SET_LOOP":
        this.ready();
        this.loop = r.payload.enabled;
        if (this.animation) await this.seek(this.time);
        break;
      case "SET_DEBUG":
        this.setDebug(r.payload);
        break;
      case "SET_CAMERA":
        this.setCamera(r.payload);
        break;
      case "RESET_CAMERA":
        this.resetCamera();
        break;
      case "SET_VIEWPORT":
        this.setViewport(r.payload);
        break;
      case "SET_BACKGROUND":
        this.setBackground(r.payload.rgba);
        break;
      case "CAPTURE_POSE":
        return this.capturePose();
      case "CAPTURE_FRAME":
        return await this.captureFrame();
      case "GET_RUNTIME_INFO":
        return this.info();
      case "DISPOSE":
        this.dispose();
        break;
    }
    return null;
  }
}
