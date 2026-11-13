"""Loopback web server for the interactive function graph."""

import json
import tempfile
import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from .analyzer import analyze_project, analyze_source
from .graph import build_function_graph
from .models import AnalysisResult
from .pov.engine import (
    PovSimulation,
    SimulationError,
    build_simulation,
    build_simulation_from_source,
)

MAX_FILES = 400
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 20 * 1024 * 1024
WEB_ROOT = Path(__file__).parent / "web"
POV_SESSIONS: "OrderedDict[str, PovSimulation]" = OrderedDict()
POV_SESSIONS_LOCK = threading.Lock()
MAX_POV_SESSIONS = 64
INVALID_JSON_BODY = object()


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
        route = urlsplit(self.path).path
        allowed_routes = {
            "/api/analyze",
            "/api/analyze-source",
            "/api/pov/start",
            "/api/pov/start-source",
            "/api/pov/check",
            "/api/pov/hint",
            "/api/pov/answer",
        }
        if route not in allowed_routes:
            self._send_json(404, {"error": "Not found"})
            return

        if route == "/api/pov/check":
            self._handle_pov_action("check")
            return
        if route == "/api/pov/hint":
            self._handle_pov_action("hint")
            return
        if route == "/api/pov/answer":
            self._handle_pov_action("answer")
            return

        payload = self._read_json_body()
        if payload is INVALID_JSON_BODY:
            return
        if route == "/api/analyze-source":
            try:
                source = _validate_source(payload)
                result = analyze_source(source)
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            syntax_errors = [item for item in result.diagnostics if item.severity == "error"]
            if syntax_errors:
                diagnostic = syntax_errors[0]
                location = " on line {}".format(diagnostic.line) if diagnostic.line else ""
                self._send_json(
                    400,
                    {
                        "error": "Python syntax error{}: {}. Check indentation, brackets, "
                        "and colons, then try again.".format(location, diagnostic.message)
                    },
                )
                return
            self._send_json(200, _analysis_payload(result))
            return
        if route == "/api/pov/start-source":
            try:
                source = _validate_source(payload)
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            function_id = payload.get("function_id") if isinstance(payload, dict) else None
            arguments = payload.get("arguments", {}) if isinstance(payload, dict) else {}
            if not isinstance(function_id, str) or not isinstance(arguments, dict):
                self._send_json(
                    400,
                    {"error": 'POV start requires a "function_id" and an "arguments" object.'},
                )
                return
            try:
                simulation = build_simulation_from_source(source, function_id, arguments)
            except (OSError, ValueError, SimulationError) as error:
                self._send_json(400, {"error": str(error)})
                return
            session_id = str(uuid.uuid4())
            with POV_SESSIONS_LOCK:
                POV_SESSIONS[session_id] = simulation
                while len(POV_SESSIONS) > MAX_POV_SESSIONS:
                    POV_SESSIONS.popitem(last=False)
            response = simulation.public_dict()
            response["session_id"] = session_id
            self._send_json(200, response)
            return
        try:
            files = _validate_files(payload)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return

        if route == "/api/pov/start":
            function_id = payload.get("function_id") if isinstance(payload, dict) else None
            arguments = payload.get("arguments", {}) if isinstance(payload, dict) else {}
            if not isinstance(function_id, str) or not isinstance(arguments, dict):
                self._send_json(
                    400,
                    {"error": 'POV start requires a "function_id" and an "arguments" object.'},
                )
                return
            try:
                simulation = _build_uploaded_simulation(files, function_id, arguments)
            except (OSError, ValueError, SimulationError) as error:
                self._send_json(400, {"error": str(error)})
                return
            session_id = str(uuid.uuid4())
            with POV_SESSIONS_LOCK:
                POV_SESSIONS[session_id] = simulation
                while len(POV_SESSIONS) > MAX_POV_SESSIONS:
                    POV_SESSIONS.popitem(last=False)
            response = simulation.public_dict()
            response["session_id"] = session_id
            self._send_json(200, response)
            return

        try:
            result = _analyze_uploaded_files(files)
        except (OSError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, _analysis_payload(result))

    def _read_json_body(self) -> object:
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length) if content_length is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            self._send_json(400, {"error": "A valid Content-Length header is required."})
            return INVALID_JSON_BODY
        if length > MAX_REQUEST_BYTES:
            self._send_json(413, {"error": "The upload request is too large (20 MB maximum)."})
            return INVALID_JSON_BODY
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Request body must be valid UTF-8 JSON."})
            return None

    def _handle_pov_action(self, action: str) -> None:
        payload = self._read_json_body()
        if payload is INVALID_JSON_BODY:
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "Request body must be a JSON object."})
            return
        session_id = payload.get("session_id")
        index = payload.get("step")
        if (
            not isinstance(session_id, str)
            or not isinstance(index, int)
            or isinstance(index, bool)
        ):
            self._send_json(400, {"error": "A POV session and step number are required."})
            return
        with POV_SESSIONS_LOCK:
            simulation = POV_SESSIONS.get(session_id)
        if simulation is None:
            self._send_json(404, {"error": "This POV session has expired. Enter POV again."})
            return
        try:
            if action == "check":
                result = simulation.check(index, payload.get("answer"))
            elif action == "hint":
                result = {"hint": simulation.hint(index)}
            else:
                result = {
                    "answer": simulation.answer(index),
                    "feedback": "Here is the answer. You can continue learning.",
                }
        except SimulationError as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, result)

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


def _validate_source(payload: object) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("source"), str):
        raise ValueError('Request body must contain a "source" string.')
    source = payload["source"]
    if len(source.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Pasted code exceeds the 2 MB source limit.")
    return source


def _analysis_payload(result: AnalysisResult) -> Dict[str, object]:
    graph = build_function_graph(result)
    return {
        "functions": [asdict(function) for function in result.functions],
        "calls": [asdict(call) for call in result.calls],
        "graph": graph.to_dict(),
        "diagnostics": [asdict(diagnostic) for diagnostic in result.diagnostics],
    }


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


def _build_uploaded_simulation(
    files: List[Tuple[str, str]],
    function_id: str,
    arguments: Dict[str, object],
) -> PovSimulation:
    with tempfile.TemporaryDirectory(prefix="function-pov-") as directory:
        root = Path(directory).resolve()
        for relative_name, source in files:
            destination = (root / relative_name).resolve()
            if not destination.is_relative_to(root):
                raise ValueError("A file path is outside the temporary project directory.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source, encoding="utf-8")
        return build_simulation(str(root), function_id, arguments)


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
