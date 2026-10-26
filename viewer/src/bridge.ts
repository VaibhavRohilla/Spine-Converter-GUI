import { requestSchema } from "./protocol";
import type { Reply } from "./contracts";
import type { SpineViewer } from "./viewer";
export interface HostBridge {
  submit(serialized: string): boolean;
  takeReplies(): string;
  takeEvents(): string;
}
export function createHostBridge(viewer: SpineViewer): HostBridge {
  const replies: Reply[] = [];
  const events: { event: string; detail: object }[] = [];
  const requests = new Set<string>();
  for (const event of [
    "LOAD_STARTED",
    "RUNTIME_READY",
    "ASSETS_LOADED",
    "VIEWER_READY",
    "PLAYBACK_CHANGED",
    "ANIMATION_COMPLETE",
    "ANIMATION_EVENT",
    "RUNTIME_WARNING",
    "RUNTIME_ERROR",
    "SESSION_DISPOSED",
  ])
    viewer.addEventListener(event, (e) => {
      events.push({ event, detail: (e as CustomEvent<object>).detail });
      if (events.length > 256) events.shift();
    });
  return {
    submit(serialized) {
      if (
        serialized.length > 16384 ||
        replies.length >= 16 ||
        requests.size >= 16
      )
        return false;
      let parsed: ReturnType<typeof requestSchema.safeParse>;
      try {
        parsed = requestSchema.safeParse(JSON.parse(serialized));
      } catch {
        return false;
      }
      if (
        !parsed.success ||
        parsed.data.sessionId !== viewer.sessionId ||
        requests.has(parsed.data.requestId)
      )
        return false;
      requests.add(parsed.data.requestId);
      void viewer.request(parsed.data).then((reply) => {
        replies.push(reply);
      });
      return true;
    },
    takeReplies() {
      const result = JSON.stringify(replies);
      for (const reply of replies) requests.delete(reply.requestId);
      replies.length = 0;
      return result;
    },
    takeEvents() {
      const result = JSON.stringify(events);
      events.length = 0;
      return result;
    },
  };
}
