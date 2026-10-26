import type { Assets, Diagnostic } from "./contracts";
export const diagnosticCodes = [
  "RUNTIME_NOT_INSTALLED",
  "RUNTIME_VERSION_MISMATCH",
  "UNSUPPORTED_SKELETON_FORMAT",
  "UNSUPPORTED_SKELETON_VERSION",
  "SOURCE_EXPORT_KNOWN_BUG",
  "SKELETON_PARSE_FAILED",
  "ATLAS_LOAD_FAILED",
  "TEXTURE_MISSING",
  "TEXTURE_DECODE_FAILED",
  "ATTACHMENT_RESOLUTION_FAILED",
  "ANIMATION_NOT_FOUND",
  "SKIN_NOT_FOUND",
  "RENDERER_INITIALIZATION_FAILED",
  "WEBGL_UNAVAILABLE",
  "WEBGL_CONTEXT_LOST",
  "UNSUPPORTED_RENDER_FEATURE",
  "NON_FINITE_POSE",
  "RUNTIME_UPDATE_FAILED",
  "FRAME_CAPTURE_FAILED",
  "VIEWER_SESSION_CANCELLED",
  "VIEWER_RESOURCE_LIMIT_EXCEEDED",
  "ASSET_TRANSPORT_FAILED",
  "ASSET_INTEGRITY_FAILED",
  "ASSET_ORIGIN_REJECTED",
  "INVALID_PROTOCOL_REQUEST",
  "INVALID_SESSION_STATE",
  "VISUAL_COMPARISON_UNAVAILABLE",
] as const;
export type DiagnosticCode = (typeof diagnosticCodes)[number];
export class ViewerError extends Error {
  constructor(
    readonly code: DiagnosticCode,
    message: string = code,
    readonly filename: string | null = null,
  ) {
    super(message);
    this.name = "ViewerError";
  }
}
export function diagnostic(
  error: unknown,
  assets: Assets,
  fallback: DiagnosticCode = "RUNTIME_UPDATE_FAILED",
): Diagnostic {
  const e = error instanceof Error ? error : new Error(String(error));
  return {
    code: e instanceof ViewerError ? e.code : fallback,
    severity: "error",
    family: assets.family,
    assetId: assets.assetId,
    filename: e instanceof ViewerError ? e.filename : null,
    context: e.stack ?? e.message,
    message: e.message,
    action:
      "Inspect the named asset and runtime details. Correct the input or explicitly retry the session.",
  };
}
export function cancelled(signal: AbortSignal): void {
  if (signal.aborted) throw new ViewerError("VIEWER_SESSION_CANCELLED");
}
