import { test, expect } from "@playwright/test";
import { fetchBytes, sha256 } from "../src/resources";

const originalFetch = globalThis.fetch;
const originalLocation = Object.getOwnPropertyDescriptor(
  globalThis,
  "location",
);
test.beforeEach(() => {
  Object.defineProperty(globalThis, "location", {
    configurable: true,
    value: new URL("https://viewer.example/"),
  });
});
test.afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalLocation)
    Object.defineProperty(globalThis, "location", originalLocation);
  else Reflect.deleteProperty(globalThis, "location");
});
const signal = () => new AbortController().signal;

for (const status of [200, 503]) {
  test(`rejected response ${status} cancels its body without losing diagnostic`, async () => {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({
      cancel() {
        cancelled = true;
        throw Error("cleanup failure");
      },
    });
    globalThis.fetch = async () =>
      new Response(body, {
        status,
        headers: { "content-length": "100" },
      });
    await expect(fetchBytes("/asset", signal(), "", 10)).rejects.toMatchObject({
      code:
        status === 200
          ? "VIEWER_RESOURCE_LIMIT_EXCEEDED"
          : "ASSET_TRANSPORT_FAILED",
    });
    expect(cancelled).toBe(true);
    expect(body.locked).toBe(false);
  });
}

test("stream failure remains a typed transport failure and releases reader", async () => {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.error(Error("connection reset"));
    },
  });
  globalThis.fetch = async () => new Response(body);
  await expect(fetchBytes("/asset", signal(), "")).rejects.toMatchObject({
    code: "ASSET_TRANSPORT_FAILED",
  });
  expect(body.locked).toBe(false);
});

test("streamed overflow cancels and unlocks even when cancel rejects", async () => {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new Uint8Array(11));
    },
    cancel() {
      cancelled = true;
      throw Error("cancel rejected");
    },
  });
  globalThis.fetch = async () => new Response(body);
  await expect(fetchBytes("/asset", signal(), "", 10)).rejects.toMatchObject({
    code: "VIEWER_RESOURCE_LIMIT_EXCEEDED",
  });
  expect(cancelled).toBe(true);
  expect(body.locked).toBe(false);
});

test("bounded successful download retains integrity checking and unlocks", async () => {
  const bytes = new Uint8Array([1, 2, 3]);
  const response = new Response(bytes);
  globalThis.fetch = async () => response;
  expect(await fetchBytes("/asset", signal(), await sha256(bytes), 3)).toEqual(
    bytes,
  );
  expect(response.body?.locked).toBe(false);
});

test("invalid byte budgets fail before invoking fetch", async () => {
  let fetched = false;
  globalThis.fetch = async () => {
    fetched = true;
    return new Response();
  };
  for (const limit of [NaN, Infinity, -1, 0, 1.5, Number.MAX_SAFE_INTEGER])
    await expect(
      fetchBytes("/asset", signal(), "", limit),
    ).rejects.toMatchObject({
      code: "VIEWER_RESOURCE_LIMIT_EXCEEDED",
    });
  expect(fetched).toBe(false);
});
