"""Capability-URL local transport: immutable snapshots, no browser filesystem API."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from socket import socket
from threading import BoundedSemaphore, RLock, Thread
from urllib.parse import unquote, urlsplit

from ..json_types import JSONDocument, decode_json_object
from .service import ViewerAssetSet, ViewerService
from .session import ViewerSessionManager, ViewerState


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        self.capacity = BoundedSemaphore(16)
        super().__init__(address, handler)

    def process_request(
        self, request: socket | tuple[bytes, socket], client_address: tuple[str, int]
    ) -> None:
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            if not isinstance(request, socket):
                raise TypeError("Loopback transport requires TCP")
            request.settimeout(10)
            super().process_request(request, client_address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(
        self, request: socket | tuple[bytes, socket], client_address: tuple[str, int]
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()

    def server_bind(self) -> None:
        # HTTPServer's reverse DNS lookup can block offline macOS hosts.
        self.socket.bind(self.server_address)
        address: object = self.socket.getsockname()
        if not isinstance(address, tuple):
            raise RuntimeError("Unexpected loopback address")
        port: object = address[1]
        if not isinstance(port, int):
            raise RuntimeError("Unexpected loopback port")
        self.server_name = "127.0.0.1"
        self.server_port = port


class ViewerServer:
    def __init__(self, assets: tuple[ViewerAssetSet, ...], web_root: Path) -> None:
        self.manager = ViewerSessionManager()
        self.lock = RLock()
        self.token = token_urlsafe(32)
        self.assets = assets
        self.web_files = {
            p.relative_to(web_root).as_posix(): p.read_bytes()
            for p in web_root.rglob("*")
            if p.is_file()
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.headers.get("Host") != f"127.0.0.1:{owner.http.server_port}":
                    self.send_error(403)
                    return
                origin = self.headers.get("Origin")
                if origin and origin != owner.origin:
                    self.send_error(403)
                    return
                route = unquote(urlsplit(self.path).path)
                prefix = f"/{owner.token}/"
                if not route.startswith(prefix):
                    self.send_error(404)
                    return
                key = route[len(prefix) :]
                data: bytes | None = None
                content_type = "application/octet-stream"
                if key == "sessions.json":
                    descriptors: list[JSONDocument] = [
                        a.descriptor(f"/{owner.token}/asset/{i}/", f"session-{i}")
                        for i, a in enumerate(owner.assets)
                    ]
                    data = json.dumps(descriptors).encode()
                    content_type = "application/json"
                elif key.startswith("launch/") and key.endswith(".json"):
                    index_text = key[7:-5]
                    if index_text.isdigit() and int(index_text) < len(owner.assets):
                        index = int(index_text)
                        with owner.lock:
                            if len(owner.manager.sessions) >= 128:
                                self.send_error(429)
                                return
                            session = owner.manager.create()
                            session.transition(ViewerState.INSPECTING)
                        data = json.dumps(
                            owner.assets[index].descriptor(
                                f"/{owner.token}/asset/{index}/", session.session_id
                            )
                        ).encode()
                        content_type = "application/json"
                elif key.startswith("asset/"):
                    parts = key.split("/", 2)
                    if len(parts) == 3 and parts[1].isdigit():
                        index = int(parts[1])
                        if index < len(owner.assets):
                            data = owner.assets[index].files.get(parts[2])
                            content_type = mimetypes.guess_type(parts[2])[0] or content_type
                else:
                    name = key or "index.html"
                    data = owner.web_files.get(name)
                    content_type = mimetypes.guess_type(name)[0] or content_type
                if data is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; "
                    "script-src 'self'; style-src 'self'; img-src 'self' blob:; "
                    "connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; "
                    "base-uri 'none'; object-src 'none'; form-action 'none'",
                )
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self) -> None:
                if (
                    self.headers.get("Host") != f"127.0.0.1:{owner.http.server_port}"
                    or self.headers.get("Origin") != owner.origin
                    or self.headers.get("Content-Type") != "application/json"
                ):
                    self.send_error(403)
                    return
                prefix = f"/{owner.token}/state/"
                if not self.path.startswith(prefix):
                    self.send_error(404)
                    return
                session_id = self.path[len(prefix) :]
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 4096:
                        raise ValueError("Invalid lifecycle message size")
                    doc = decode_json_object(self.rfile.read(length).decode(), "Viewer lifecycle")
                    if (
                        set(doc) != {"protocolVersion", "state"}
                        or type(doc["protocolVersion"]) is not int
                        or doc["protocolVersion"] != 1
                    ):
                        raise ValueError("Invalid lifecycle message")
                    value = doc["state"]
                    if not isinstance(value, str):
                        raise ValueError("Invalid state")
                    state = ViewerState(value)
                    with owner.lock:
                        session = owner.manager.sessions[session_id]
                        # Retry re-enters inspection at the Python boundary.
                        if (
                            session.state == ViewerState.FAILED
                            and state == ViewerState.LOADING_RUNTIME
                        ):
                            session.transition(ViewerState.INSPECTING)
                        session.transition(state)
                        if state == ViewerState.DISPOSED:
                            del owner.manager.sessions[session_id]
                except (ValueError, KeyError, UnicodeError):
                    self.send_error(400)
                    return
                self.send_response(204)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.http = LoopbackServer(("127.0.0.1", 0), Handler)
        self.thread: Thread | None = None

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.http.server_port}"

    @property
    def url(self) -> str:
        return f"{self.origin}/{self.token}/"

    def start(self) -> str:
        self.thread = Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def close(self) -> None:
        if self.thread:
            self.http.shutdown()
            self.thread.join()
        self.http.server_close()
        self.manager.sessions.clear()
        self.assets = ()
        self.web_files.clear()


def main() -> None:
    parser = argparse.ArgumentParser(description="B4 local developer viewer")
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--bundle", action="append", required=True)
    parser.add_argument("--web-root", type=Path, default=Path("viewer/dist"))
    args = parser.parse_args()
    # argparse values are admitted individually rather than crossing typed service APIs.
    sources: list[str] = args.source
    bundles: list[str] = args.bundle
    root: Path = args.web_root
    if len(sources) != len(bundles):
        parser.error("each --source requires exactly one --bundle")
    assets = tuple(ViewerService().prepare(s, b) for s, b in zip(sources, bundles, strict=True))
    server = ViewerServer(assets, root)
    print(server.start(), flush=True)
    try:
        server.thread.join() if server.thread else None
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    main()
