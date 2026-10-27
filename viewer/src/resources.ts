import { ViewerError, cancelled } from "./diagnostics";
const MAX = 128 * 1024 * 1024;
async function cancelDownload(
  owner: Pick<ReadableStreamDefaultReader<Uint8Array>, "cancel">,
): Promise<void> {
  try {
    await owner.cancel();
  } catch {
    // Cleanup must not replace the original transport, limit or cancellation error.
  }
}
export async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
}
export async function fetchBytes(
  url: string,
  signal: AbortSignal,
  expectedHash: string,
  maxBytes: number = MAX,
): Promise<Uint8Array<ArrayBuffer>> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0 || maxBytes > MAX)
    throw new ViewerError(
      "VIEWER_RESOURCE_LIMIT_EXCEEDED",
      "Invalid resource byte limit.",
    );
  const parsed = new URL(url, location.href);
  if (parsed.origin !== location.origin)
    throw new ViewerError(
      "ASSET_ORIGIN_REJECTED",
      "Only the selected local asset origin is admitted.",
      url,
    );
  cancelled(signal);
  let response: Response;
  try {
    response = await fetch(parsed, {
      signal,
      credentials: "omit",
      redirect: "error",
    });
  } catch (e) {
    cancelled(signal);
    throw new ViewerError("ASSET_TRANSPORT_FAILED", String(e), url);
  }
  if (!response.ok) {
    if (response.body) await cancelDownload(response.body);
    throw new ViewerError(
      "ASSET_TRANSPORT_FAILED",
      `HTTP ${response.status}`,
      url,
    );
  }
  if (Number(response.headers.get("content-length")) > maxBytes) {
    if (response.body) await cancelDownload(response.body);
    throw new ViewerError(
      "VIEWER_RESOURCE_LIMIT_EXCEEDED",
      "Resource exceeds byte limit.",
      url,
    );
  }
  const reader = response.body?.getReader();
  if (!reader)
    throw new ViewerError("ASSET_TRANSPORT_FAILED", "No response stream.", url);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const item = await reader.read();
      if (item.done) break;
      size += item.value.length;
      if (size > maxBytes)
        throw new ViewerError("VIEWER_RESOURCE_LIMIT_EXCEEDED");
      chunks.push(item.value);
    }
  } catch (e) {
    await cancelDownload(reader);
    cancelled(signal);
    if (e instanceof ViewerError) throw e;
    throw new ViewerError("ASSET_TRANSPORT_FAILED", String(e), url);
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  if ((await sha256(result)) !== expectedHash)
    throw new ViewerError(
      "ASSET_INTEGRITY_FAILED",
      "Resource hash differs from the inspected snapshot.",
      url,
    );
  cancelled(signal);
  return result;
}
export async function fetchText(
  url: string,
  signal: AbortSignal,
  hash: string,
): Promise<string> {
  return new TextDecoder("utf-8", { fatal: true }).decode(
    await fetchBytes(url, signal, hash),
  );
}
export async function loadImage(
  url: string,
  signal: AbortSignal,
  hash: string,
  premultiply: boolean,
): Promise<ImageBitmap> {
  const bytes = await fetchBytes(url, signal, hash);
  let image: ImageBitmap;
  try {
    image = await createImageBitmap(new Blob([bytes]), {
      premultiplyAlpha: premultiply ? "premultiply" : "none",
      colorSpaceConversion: "none",
    });
  } catch (e) {
    cancelled(signal);
    throw new ViewerError("TEXTURE_DECODE_FAILED", String(e), url);
  }
  if (signal.aborted) {
    image.close();
    cancelled(signal);
  }
  return image;
}
