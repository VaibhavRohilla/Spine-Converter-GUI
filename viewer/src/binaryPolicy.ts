import type { Assets } from "./contracts";
import { trustedBinaries } from "./generated/binaryPolicy";
import { ViewerError } from "./diagnostics";
import { sha256 } from "./resources";

export async function admitBinary(
  bytes: Uint8Array<ArrayBuffer>,
  assets: Assets,
): Promise<void> {
  if (bytes.byteLength > 32 * 1024 * 1024)
    throw new ViewerError("VIEWER_RESOURCE_LIMIT_EXCEEDED");
  // Hash the actual bytes independently of attacker-supplied transport metadata.
  const digest = await sha256(bytes);
  const record = trustedBinaries.find((item) => item.sha256 === digest);
  if (!record || record.bytes !== bytes.byteLength)
    throw new ViewerError(
      "UNTRUSTED_BINARY_DISABLED",
      "No qualified process isolation; only approved fixture bytes may reach the official binary parser.",
    );
  if (record.version !== assets.exportVersion)
    throw new ViewerError("RUNTIME_VERSION_MISMATCH");
}
