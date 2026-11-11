"""Loopback web server for the interactive function graph."""

import json
import tempfile
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from .analyzer import analyze_project
from .graph import build_function_graph

MAX_FILES = 400
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 20 * 1024 * 1024
WEB_ROOT = Path(__file__).parent / "web"


class FunctionPovRequestHandler(BaseHTTPRequestHandler):
    """Serve the bundled UI and accept source text for static analysis."""

    server_version = "FunctionPOV/0.1"

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/static/styles.css": ("static/styles.css", "text/css; charset=utf-8"),
            "/static/app.js": ("static/app.js", "text/javascript; charset=utf-8"),
        }
        if route == "/api/health":
            self._send_json(200, {"status": "ok"})
            return
        if route not in assets:
            self._send_json(404, {"error": "Not found"})
            return

        relative_path, content_type = assets[route]
        try:
            content = (WEB_ROOT / relative_path).read_bytes()
        except OSError:
            self._send_json(500, {"error": "A bundled web asset is missing."})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/analyze":
            self._send_json(404, {"error": "Not found"})
            return

        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length) if content_length is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            self._send_json(400, {"error": "A valid Content-Length header is required."})
            return
        if length > MAX_REQUEST_BYTES:
            self._send_json(413, {"error": "The upload request is too large (20 MB maximum)."})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            files = _validate_files(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return

        try:
            result = _analyze_uploaded_files(files)
        except (OSError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return
        graph = build_function_graph(result)
        self._send_json(
            200,
            {
                "functions": [asdict(function) for function in result.functions],
                "calls": [asdict(call) for call in result.calls],
                "graph": graph.to_dict(),
                "diagnostics": [asdict(diagnostic) for diagnostic in result.diagnostics],
            },
        )

    def _send_json(self, status: int, payload: Dict[str, object]) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)


def _validate_files(payload: object) -> List[Tuple[str, str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError('Request body must contain a "files" list.')
    uploaded_files = payload["files"]
    if not uploaded_files:
        raise ValueError("Choose at least one Python file.")
    if len(uploaded_files) > MAX_FILES:
        raise ValueError("Choose no more than {} Python files.".format(MAX_FILES))

    validated: List[Tuple[str, str]] = []
    seen_paths = set()
    total_bytes = 0
    for uploaded in uploaded_files:
        if not isinstance(uploaded, dict):
            raise ValueError("Each uploaded file must include a path and source.")
        name = uploaded.get("path")
        source = uploaded.get("content")
        if not isinstance(name, str) or not isinstance(source, str):
            raise ValueError("Each uploaded file must include a path and source.")
        normalized = name.replace("\\", "/")
        relative = PurePosixPath(normalized)
        if (
            not normalized
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            raise ValueError("File paths must be relative and cannot contain '..'.")
        if relative.suffix.lower() != ".py":
            raise ValueError("Only Python (.py) files can be analyzed.")
        canonical = relative.as_posix()
        if canonical in seen_paths:
            raise ValueError("Duplicate uploaded file path: {}".format(canonical))
        seen_paths.add(canonical)
        source_bytes = len(source.encode("utf-8"))
        if source_bytes > MAX_FILE_BYTES:
            raise ValueError("{} exceeds the 2 MB per-file limit.".format(canonical))
        total_bytes += source_bytes
        validated.append((canonical, source))
    if total_bytes > MAX_TOTAL_SOURCE_BYTES:
        raise ValueError("The uploaded source exceeds the 8 MB total limit.")
    return validated


def _analyze_uploaded_files(files: List[Tuple[str, str]]):
    with tempfile.TemporaryDirectory(prefix="function-pov-") as directory:
        root = Path(directory).resolve()
        for relative_name, source in files:
            destination = (root / relative_name).resolve()
            if not destination.is_relative_to(root):
                raise ValueError("A file path is outside the temporary project directory.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source, encoding="utf-8")
        return analyze_project(str(root))


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the UI until interrupted."""
    server = ThreadingHTTPServer((host, port), FunctionPovRequestHandler)
    print("Function POV UI: http://{}:{}".format(host, server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Function POV UI.", flush=True)
    finally:
        server.server_close()


def create_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a server instance for tests or embedding."""
    return ThreadingHTTPServer((host, port), FunctionPovRequestHandler)
