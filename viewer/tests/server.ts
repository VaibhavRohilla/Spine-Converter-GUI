import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

const STARTUP_DEADLINE_MS = 30000;
const SHUTDOWN_GRACE_MS = 5000;
const OUTPUT_LIMIT = 65536;

export async function server(): Promise<{
  url: string;
  close: () => Promise<void>;
}> {
  const child: ChildProcessWithoutNullStreams = spawn(
    process.env.B4_VIEWER_PYTHON ?? ".venv/bin/python",
    ["-I", "-u", "viewer/scripts/test_server.py"],
  );
  // Register before startup: shutdown must also work after an early exit/spawn error.
  const closed = new Promise<void>((resolve) =>
    child.once("close", () => resolve()),
  );
  let closing: Promise<void> | undefined;
  function close(): Promise<void> {
    closing ??= (async () => {
      if (
        child.exitCode !== null ||
        child.signalCode !== null ||
        child.pid === undefined
      ) {
        await closed;
        return;
      }
      child.kill("SIGINT");
      const escalation = setTimeout(
        () => child.kill("SIGKILL"),
        SHUTDOWN_GRACE_MS,
      );
      try {
        await closed;
      } finally {
        clearTimeout(escalation);
      }
    })();
    return closing;
  }
  let error = "";
  child.stderr.on("data", (chunk: Buffer) => {
    error = (error + chunk.toString()).slice(-OUTPUT_LIMIT);
  });
  try {
    const url = await new Promise<string>((resolve, reject) => {
      let out = "";
      const timeout = setTimeout(() => {
        reject(Error(`Server timeout: ${error}`));
      }, STARTUP_DEADLINE_MS);
      function failed(reason: Error): void {
        clearTimeout(timeout);
        reject(reason);
      }
      child.once("error", failed);
      child.stdout.on("data", (chunk: Buffer) => {
        out += chunk.toString();
        if (out.length > OUTPUT_LIMIT) {
          failed(Error("Server startup output exceeded limit"));
          return;
        }
        if (out.includes("\n")) {
          clearTimeout(timeout);
          const line = out.split("\n")[0]?.trim();
          if (!line) failed(Error("Server did not return a URL"));
          else resolve(line);
        }
      });
      child.once("exit", (code, signal) =>
        failed(Error(`Server exit ${code}/${signal}: ${error}`)),
      );
    });
    return { url, close };
  } catch (error) {
    await close();
    throw error;
  }
}
