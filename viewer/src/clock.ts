import { ViewerError } from "./diagnostics";
export const FIXED_STEP = 1 / 60;
export function simulationSteps(seconds: number): {
  whole: number;
  remainder: number;
} {
  if (!Number.isFinite(seconds) || seconds < 0 || seconds > 600)
    throw new ViewerError(
      "VIEWER_RESOURCE_LIMIT_EXCEEDED",
      "Simulation time must be between 0 and 600 seconds.",
    );
  const whole = Math.floor(seconds / FIXED_STEP);
  const remainder = seconds - whole * FIXED_STEP;
  return { whole, remainder: remainder > 1e-10 ? remainder : 0 };
}
export class RealtimeClock {
  private previous: number | null = null;
  reset() {
    this.previous = null;
  }
  delta(now: number): number {
    if (!Number.isFinite(now))
      throw new ViewerError("RUNTIME_UPDATE_FAILED", "Non-finite clock");
    const delta =
      this.previous === null
        ? 0
        : Math.min(Math.max((now - this.previous) / 1000, 0), 0.05);
    this.previous = now;
    return delta;
  }
}
