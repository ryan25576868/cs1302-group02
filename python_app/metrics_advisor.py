"""Code complexity and beginner readability advisor for Prism."""

from __future__ import annotations

import json
from typing import Any


def evaluate_code_health(analysis: dict[str, Any], trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute cyclomatic complexity, readability grade, and beginner tips."""
    metrics = analysis.get("metrics") or {}
    loops = int(metrics.get("loops", 0))
    conditions = int(metrics.get("conditions", 0))
    functions = int(metrics.get("functions", 0))
    max_depth = int(metrics.get("maxDepth", 0))
    code_lines = int(metrics.get("codeLines", 0))

    # McCabe-style simplified cyclomatic complexity: 1 + decision/loop branches
    complexity = 1 + loops + conditions

    if complexity <= 3 and max_depth <= 3:
        grade = "A"
        label = "Clean & Flat"
        summary = "Low branching complexity. Easy for beginners to trace step by step."
    elif complexity <= 6 and max_depth <= 4:
        grade = "B"
        label = "Moderate"
        summary = "Moderate control flow. Consider splitting complex blocks into helper functions."
    else:
        grade = "C"
        label = "Deep / Complex"
        summary = "High branching or deep nesting. Refactoring into smaller functions is recommended."

    tips: list[str] = []
    if max_depth >= 4:
        tips.append(f"Nesting depth reaches {max_depth} levels; consider early returns to flatten logic.")
    if loops >= 2 and functions == 0 and code_lines >= 12:
        tips.append("Multiple loops appear at top level; wrapping reusable logic in a function improves clarity.")
    if conditions >= 3:
        tips.append("Several conditional branches detected; verify edge cases in Live Trace.")
    if trace and trace.get("warnings"):
        tips.append("Trace terminated early due to safe execution bounds; inspect structural views for full coverage.")
    if not tips:
        tips.append("Structure is concise and well-proportioned for step-by-step learning.")

    return {
        "cyclomaticComplexity": complexity,
        "maxNestingDepth": max_depth,
        "grade": grade,
        "label": label,
        "summary": summary,
        "tips": tips,
    }


def format_health_markdown(health: dict[str, Any]) -> str:
    """Render code health report as a Markdown section."""
    lines = [
        "## Code Health & Complexity",
        f"- **Rating**: Grade {health['grade']} ({health['label']})",
        f"- **Cyclomatic Complexity**: {health['cyclomaticComplexity']}",
        f"- **Max Nesting Depth**: {health['maxNestingDepth']}",
        f"- **Assessment**: {health['summary']}",
        "",
        "### Structural Tips",
    ]
    lines.extend(f"- {tip}" for tip in health.get("tips", []))
    return "\n".join(lines)


def export_health_json(analysis: dict[str, Any], trace: dict[str, Any] | None = None) -> str:
    """Serialize analysis metrics and health score into formatted JSON."""
    health = evaluate_code_health(analysis, trace)
    payload = {
        "language": analysis.get("languageId", "unknown"),
        "metrics": analysis.get("metrics", {}),
        "health": health,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
