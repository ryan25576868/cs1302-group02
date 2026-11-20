"""Structural comparison engine: Prism analysis trees -> structscope diff.

Kept free of Qt imports so it can be tested, scripted and reused. The heavy
lifting (symbol matching, status classification, two-column layout) is done by
the separate ``structscope`` package; this module only adapts the trees Prism
already builds into the symbol model structscope expects.

Requires ``structscope`` on the path: ``pip install structscope``.
"""

from __future__ import annotations

import difflib
import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from structscope.diff import DiffResult
    from structscope.matcher import match as match_symbols
    from structscope.model import FileModel, Symbol

    ENGINE_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on the environment
    DiffResult = None  # type: ignore[assignment]
    match_symbols = None  # type: ignore[assignment]
    FileModel = None  # type: ignore[assignment]
    Symbol = None  # type: ignore[assignment]
    ENGINE_ERROR = f"{type(exc).__name__}: {exc}"

LANGUAGE_LABELS = [
    ("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"),
    ("java", "Java"), ("cpp", "C++"), ("c", "C"),
]
FILE_EXTENSIONS = {
    "python": ["py"], "javascript": ["js", "jsx", "mjs"], "typescript": ["ts", "tsx"],
    "java": ["java"], "cpp": ["cpp", "cc", "cxx", "hpp", "h"], "c": ["c", "h"],
}

STATUS_COLORS = {
    "added": "#57c98a",
    "removed": "#ff6b6b",
    "modified": "#f2b544",
    "moved": "#6aa8ff",
    "unchanged": "#59606b",
}
STATUS_FILL = {
    "added": "#1e2f26",
    "removed": "#33211f",
    "modified": "#322a1b",
    "moved": "#1d2733",
    "unchanged": "#22252a",
}

_CONTAINERS = {"class", "function"}
_DECISIONS = {
    "if", "elif", "else", "for", "foreach", "while", "case", "catch", "when",
    "switch", "match", "try", "ternary", "do",
}


def analyze_source(language: str, source: str) -> Dict[str, Any]:
    """Run the analyzer that belongs to ``language``.

    The analyzers are imported on demand: the compiled-language one needs
    tree-sitter, and a missing optional dependency should not stop Prism from
    comparing Python files.
    """
    if language == "python":
        try:
            from python_app.analysis import analyze_python
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from python_app.analysis import analyze_python
        return analyze_python(source)
    if language in ("javascript", "typescript"):
        try:
            from python_app.js_analysis import analyze_javascript
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from python_app.js_analysis import analyze_javascript
        return analyze_javascript(source, language)
    try:
        from python_app.compiled_analysis import analyze_compiled
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from python_app.compiled_analysis import analyze_compiled
    return analyze_compiled(source, language)


def _children(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    body = node.get("body")
    if isinstance(body, dict):
        return list(body.get("children") or [])
    if isinstance(body, list):
        return list(body)
    return []


def _flat_text(node: Dict[str, Any]) -> str:
    return " ".join(str(node.get("header") or node.get("text") or "").split())


def _signature(node: Dict[str, Any], drop_name: str = "") -> str:
    """Structural signature of a subtree: node types plus their source text.

    Node ids are skipped on purpose: they change on every parse and would make
    every symbol look modified. The symbol's own name can be dropped so that a
    rename shows up as "moved" instead of "modified + added + removed".
    """
    parts: List[str] = []
    stack: List[Tuple[Dict[str, Any], bool]] = [(node, True)]
    while stack:
        current, is_root = stack.pop()
        text = _flat_text(current)
        if is_root and drop_name and drop_name in text:
            text = text.replace(drop_name, "\x00", 1)
        parts.append(f"{current.get('type')}:{text}")
        for child in reversed(_children(current)):
            stack.append((child, False))
    return "\n".join(parts)


def _body_hash(node: Dict[str, Any], name: str) -> str:
    return hashlib.sha1(_signature(node, name).encode("utf-8")).hexdigest()


def _subtree_complexity(node: Dict[str, Any]) -> int:
    total = 1
    stack = [node]
    while stack:
        current = stack.pop()
        for child in _children(current):
            if child.get("type") in _DECISIONS:
                total += 1
            stack.append(child)
    return total


def _has_doc_above(lines: List[str], start_line: int) -> bool:
    index = start_line - 2
    checked = 0
    while index >= 0 and checked < 6:
        stripped = lines[index].strip()
        checked += 1
        index -= 1
        if not stripped or stripped.startswith("@"):
            continue
        return (
            stripped.startswith("#")
            or stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.startswith('"""')
            or stripped.startswith("'''")
        )
    return False


def model_from_analysis(analysis: Dict[str, Any], label: str) -> Any:
    """Build a structscope ``FileModel`` out of one Prism analysis result."""
    raw_lines = analysis.get("lines") or []
    lines = [
        item.get("text", "") if isinstance(item, dict) else str(item)
        for item in raw_lines
    ]
    source = "\n".join(lines)

    def walk(nodes: List[Dict[str, Any]], prefix: str, depth: int, parent_kind: str) -> List[Any]:
        found = []
        for node in nodes:
            kind_raw = node.get("type")
            if kind_raw not in _CONTAINERS:
                continue
            name = str(node.get("name") or "anonymous")
            if kind_raw == "class":
                kind = "class"
            elif parent_kind == "class":
                kind = "method"
            elif depth == 0:
                kind = "function"
            else:
                kind = "nested"
            qualname = f"{prefix}{name}"
            start = int(node.get("startLine") or 1)
            end = int(node.get("endLine") or start)
            symbol = Symbol(
                kind=kind,
                name=name,
                qualname=qualname,
                lineno=start,
                end_lineno=end,
                depth=depth,
                loc=sum(1 for line in lines[start - 1:end] if line.strip()),
                complexity=_subtree_complexity(node),
                params=len(node.get("params") or []),
                has_doc=_has_doc_above(lines, start),
                body_hash=_body_hash(node, name),
            )
            symbol.children = walk(_children(node), f"{qualname}.", depth + 1, kind)
            found.append(symbol)
        return found

    root = analysis.get("root") or {}
    symbols = walk(_children(root), "", 0, "")
    return FileModel(
        path=label,
        label=label,
        source=source,
        lines=lines,
        symbols=symbols,
        loc=sum(1 for line in lines if line.strip()),
    )


def compare_sources(
    language: str,
    old_source: str,
    new_source: str,
    old_label: str = "before",
    new_label: str = "after",
) -> Any:
    """Diff two source strings with Prism's parsers and structscope's matcher."""
    if ENGINE_ERROR:
        raise RuntimeError(
            "structscope is not available; install it with: pip install structscope"
        )
    old_analysis = analyze_source(language, old_source)["analysis"]
    new_analysis = analyze_source(language, new_source)["analysis"]
    old = model_from_analysis(old_analysis, old_label)
    new = model_from_analysis(new_analysis, new_label)
    pairs = match_symbols(old.symbols, new.symbols)
    class PrismDiffResult(DiffResult):
        def summary(self):
            return {**super().summary(), "language": language}

    result = PrismDiffResult(old=old, new=new, pairs=pairs)
    return result


def aligned_rows(
    old_lines: List[str], new_lines: List[str], old_start: int, new_start: int
) -> List[Tuple[str, int, str, int, str]]:
    """Line pairs for the detail table: (tag, old_no, old_text, new_no, new_text)."""
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    rows: List[Tuple[str, int, str, int, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                rows.append((
                    "eq",
                    old_start + i1 + offset,
                    old_lines[i1 + offset],
                    new_start + j1 + offset,
                    new_lines[j1 + offset],
                ))
            continue
        old_count = i2 - i1
        new_count = j2 - j1
        for offset in range(max(old_count, new_count)):
            has_old = offset < old_count
            has_new = offset < new_count
            rows.append((
                "rep" if has_old and has_new else ("del" if has_old else "ins"),
                old_start + i1 + offset if has_old else 0,
                old_lines[i1 + offset] if has_old else "",
                new_start + j1 + offset if has_new else 0,
                new_lines[j1 + offset] if has_new else "",
            ))
    return rows


def describe(summary: Dict[str, Any]) -> str:
    """One-line stats string shared by the CLI-style output and the UI."""
    return (
        f"{summary['added']} added · {summary['removed']} removed · "
        f"{summary['modified']} modified · {summary['moved']} moved · "
        f"{summary['unchanged']} unchanged   |   "
        f"LOC {summary['old_loc']} \u2192 {summary['new_loc']} "
        f"({summary['loc_delta']:+d})   |   "
        f"complexity {summary['old_complexity']} \u2192 {summary['new_complexity']} "
        f"({summary['complexity_delta']:+d})"
    )
