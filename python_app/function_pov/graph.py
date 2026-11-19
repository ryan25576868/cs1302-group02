"""Function call graph data derived from static analysis results."""

from dataclasses import asdict, dataclass
from typing import Dict, Tuple

from .models import AnalysisResult


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    module: str
    file: str
    line: int


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    line: int


@dataclass(frozen=True)
class FunctionGraph:
    nodes: Tuple[GraphNode, ...]
    edges: Tuple[GraphEdge, ...]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def build_function_graph(analysis: AnalysisResult) -> FunctionGraph:
    """Build serializable graph nodes and edges from an analysis result."""
    nodes = tuple(
        GraphNode(
            id=function.id,
            label=function.name,
            module=function.module,
            file=function.file,
            line=function.line,
        )
        for function in analysis.functions
    )
    edges = tuple(
        GraphEdge(source=call.caller, target=call.callee, line=call.line)
        for call in analysis.calls
    )
    return FunctionGraph(nodes=nodes, edges=edges)
