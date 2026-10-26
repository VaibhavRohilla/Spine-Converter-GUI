import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { once } from "node:events";
export async function server(): Promise<{
  url: string;
  close: () => Promise<void>;
}> {
  const child: ChildProcessWithoutNullStreams = spawn(".venv/bin/python", [
    "-u",
    "viewer/scripts/test_server.py",
  ]);
  let error = "";
  child.stderr.on("data", (chunk: Buffer) => {
    error += chunk.toString();
  });
  const url = await new Promise<string>((resolve, reject) => {
    let out = "";
    const timeout = setTimeout(() => {
      child.kill("SIGTERM");
      reject(Error(`Server timeout: ${error}`));
    }, 30000);
    child.stdout.on("data", (chunk: Buffer) => {
      out += chunk.toString();
      if (out.includes("\n")) {
        clearTimeout(timeout);
        resolve(out.trim().split("\n")[0] ?? "");
      }
    });
    child.once("exit", (code) => {
      clearTimeout(timeout);
      reject(Error(`Server exit ${code}: ${error}`));
    });
  });
  return {
    url,
    close: async () => {
      child.kill("SIGINT");
      await once(child, "exit");
    },
  };
}
