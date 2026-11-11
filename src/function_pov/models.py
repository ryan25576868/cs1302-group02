"""Data models shared by the analyzer, graph builder, and CLI."""

from dataclasses import asdict, dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ParameterInfo:
    name: str
    kind: str
    default: Optional[str] = None
    annotation: Optional[str] = None


@dataclass(frozen=True)
class FunctionInfo:
    id: str
    name: str
    module: str
    file: str
    line: int
    end_line: int
    source: str
    parameters: Tuple[ParameterInfo, ...]
    return_expressions: Tuple[str, ...]


@dataclass(frozen=True)
class CallEdge:
    caller: str
    callee: str
    line: int
    expression: str


@dataclass(frozen=True)
class Diagnostic:
    file: str
    message: str
    severity: str
    line: Optional[int] = None


@dataclass(frozen=True)
class AnalysisResult:
    root: str
    functions: Tuple[FunctionInfo, ...]
    calls: Tuple[CallEdge, ...]
    diagnostics: Tuple[Diagnostic, ...]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
