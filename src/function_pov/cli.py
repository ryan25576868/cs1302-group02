"""Command-line entry point for static function analysis."""

import argparse
import json
from typing import Optional, Sequence

from .analyzer import analyze_project
from .graph import build_function_graph


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="function-pov",
        description="Analyze Python functions and build call graph data without running the code.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a Python file or project")
    analyze_parser.add_argument("path", help="Python file or project directory")
    ui_parser = subparsers.add_parser("ui", help="Start the local interactive web interface")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: localhost)")
    ui_parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    arguments = parser.parse_args(argv)

    if arguments.command == "analyze":
        result = analyze_project(arguments.path)
        output = {
            "analysis": result.to_dict(),
            "graph": build_function_graph(result).to_dict(),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 1 if any(item.severity == "error" for item in result.diagnostics) else 0
    if arguments.command == "ui":
        from .server import serve

        serve(arguments.host, arguments.port)
        return 0
    return 0
