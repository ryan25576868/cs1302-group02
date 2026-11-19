"""Static Python source analysis based on the standard-library AST module."""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .models import (
    AnalysisResult,
    CallEdge,
    Diagnostic,
    FunctionInfo,
    ParameterInfo,
)

DEFAULT_EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "venv", "env", "__pycache__", "build", "dist"}
)


@dataclass
class _ParsedFile:
    path: Path
    module: str
    is_package_init: bool
    tree: ast.Module
    source: str


def analyze_project(
    path: str,
    exclude_dirs: Optional[Iterable[str]] = None,
) -> AnalysisResult:
    """Analyze Python functions and their statically resolvable local calls.

    Only source parsing is performed. No project module is imported or executed.
    """
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError("Project path does not exist: {}".format(target))
    if target.is_file() and target.suffix != ".py":
        raise ValueError("Expected a Python file or a project directory: {}".format(target))
    if not target.is_file() and not target.is_dir():
        raise ValueError("Expected a Python file or a project directory: {}".format(target))

    excluded = set(DEFAULT_EXCLUDED_DIRS)
    if exclude_dirs is not None:
        excluded.update(exclude_dirs)

    root = target.parent if target.is_file() else target
    files = [target] if target.is_file() else _find_python_files(target, excluded)
    diagnostics: List[Diagnostic] = []
    parsed_files: List[_ParsedFile] = []

    for file_path in files:
        relative = file_path.relative_to(root)
        module, is_package_init = _module_name(relative, root)
        try:
            source = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            diagnostics.append(
                Diagnostic(
                    file=relative.as_posix(),
                    message="Source is not valid UTF-8: {}".format(error),
                    severity="error",
                )
            )
            continue

        try:
            tree = ast.parse(source, filename=relative.as_posix())
        except SyntaxError as error:
            diagnostics.append(
                Diagnostic(
                    file=relative.as_posix(),
                    message=error.msg,
                    severity="error",
                    line=error.lineno,
                )
            )
            continue

        parsed_files.append(
            _ParsedFile(
                path=relative,
                module=module,
                is_package_init=is_package_init,
                tree=tree,
                source=source,
            )
        )

    if not files:
        diagnostics.append(
            Diagnostic(
                file=".",
                message="No Python source files were found.",
                severity="warning",
            )
        )

    return _analyze_parsed_files(str(root), parsed_files, diagnostics)


def analyze_source(source: str, filename: str = "pasted.py") -> AnalysisResult:
    """Analyze a virtual Python file without writing it to disk."""
    if not isinstance(source, str):
        raise TypeError("Python source must be text.")
    normalized_filename = filename.replace("\\", "/")
    relative = Path(normalized_filename)
    if (
        not filename
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in normalized_filename.split("/"))
        or relative.suffix.lower() != ".py"
    ):
        raise ValueError("The virtual filename must be a relative Python file path.")

    diagnostics: List[Diagnostic] = []
    try:
        tree = ast.parse(source, filename=relative.as_posix())
    except SyntaxError as error:
        diagnostics.append(
            Diagnostic(
                file=relative.as_posix(),
                message=error.msg,
                severity="error",
                line=error.lineno,
            )
        )
        return _analyze_parsed_files("<memory>", [], diagnostics)

    module = ".".join(relative.with_suffix("").parts)
    is_package_init = relative.name == "__init__.py"
    parsed = _ParsedFile(
        path=relative,
        module=module,
        is_package_init=is_package_init,
        tree=tree,
        source=source,
    )
    return _analyze_parsed_files("<memory>", [parsed], diagnostics)


def _analyze_parsed_files(
    root: str,
    parsed_files: List[_ParsedFile],
    diagnostics: List[Diagnostic],
) -> AnalysisResult:
    functions: List[FunctionInfo] = []
    function_ids: Set[str] = set()
    for parsed in parsed_files:
        for node in parsed.tree.body:
            if isinstance(node, ast.FunctionDef):
                function = _function_info(parsed, node)
                functions.append(function)
                function_ids.add(function.id)
                diagnostics.extend(_nested_definition_diagnostics(parsed.path, node))
            elif isinstance(node, ast.AsyncFunctionDef):
                diagnostics.append(
                    Diagnostic(
                        file=parsed.path.as_posix(),
                        message="Async functions are not analyzed yet.",
                        severity="warning",
                        line=node.lineno,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                diagnostics.append(
                    Diagnostic(
                        file=parsed.path.as_posix(),
                        message="Class definitions and methods are not analyzed yet.",
                        severity="warning",
                        line=node.lineno,
                    )
                )

    functions.sort(key=lambda item: (item.module, item.line, item.name))
    calls = _collect_calls(parsed_files, function_ids)
    return AnalysisResult(
        root=root,
        functions=tuple(functions),
        calls=tuple(calls),
        diagnostics=tuple(diagnostics),
    )


def _find_python_files(root: Path, excluded_dirs: Set[str]) -> List[Path]:
    return sorted(
        (
            candidate
            for candidate in root.rglob("*.py")
            if not any(part in excluded_dirs for part in candidate.relative_to(root).parts)
        ),
        key=lambda candidate: candidate.relative_to(root).as_posix(),
    )


def _module_name(relative: Path, root: Path) -> Tuple[str, bool]:
    is_package_init = relative.name == "__init__.py"
    parts = list(relative.parent.parts if is_package_init else relative.with_suffix("").parts)
    if (root / "__init__.py").is_file():
        parts.insert(0, root.name)
    if not parts:
        parts.append(root.name)
    return ".".join(parts), is_package_init


def _function_info(parsed: _ParsedFile, node: ast.FunctionDef) -> FunctionInfo:
    parameters = _parameters(node.args)
    returns = tuple(
        ast.unparse(return_node.value) if return_node.value is not None else "None"
        for return_node in _return_nodes(node)
    )
    lines = parsed.source.splitlines()
    first_line = min(
        (decorator.lineno for decorator in node.decorator_list),
        default=node.lineno,
    )
    source = "\n".join(lines[first_line - 1 : node.end_lineno])
    return FunctionInfo(
        id="{}.{}".format(parsed.module, node.name),
        name=node.name,
        module=parsed.module,
        file=parsed.path.as_posix(),
        line=first_line,
        end_line=node.end_lineno,
        source=source,
        docstring=ast.get_docstring(node, clean=False),
        parameters=parameters,
        return_expressions=returns,
    )


def _parameters(arguments: ast.arguments) -> Tuple[ParameterInfo, ...]:
    result: List[ParameterInfo] = []
    positional = list(arguments.posonlyargs) + list(arguments.args)
    positional_defaults: List[Optional[ast.expr]] = (
        [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
    )
    positional_kinds = ["positional_only"] * len(arguments.posonlyargs)
    positional_kinds.extend(["positional_or_keyword"] * len(arguments.args))

    for argument, default, kind in zip(positional, positional_defaults, positional_kinds):
        result.append(_parameter(argument, kind, default))
    if arguments.vararg is not None:
        result.append(_parameter(arguments.vararg, "var_positional", None))
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
        result.append(_parameter(argument, "keyword_only", default))
    if arguments.kwarg is not None:
        result.append(_parameter(arguments.kwarg, "var_keyword", None))
    return tuple(result)


def _parameter(
    argument: ast.arg,
    kind: str,
    default: Optional[ast.expr],
) -> ParameterInfo:
    return ParameterInfo(
        name=argument.arg,
        kind=kind,
        default=ast.unparse(default) if default is not None else None,
        annotation=ast.unparse(argument.annotation) if argument.annotation else None,
    )


def _return_nodes(function: ast.FunctionDef) -> List[ast.Return]:
    class ReturnFinder(ast.NodeVisitor):
        def __init__(self) -> None:
            self.nodes: List[ast.Return] = []

        def visit_Return(self, node: ast.Return) -> None:
            self.nodes.append(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is function:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

    finder = ReturnFinder()
    finder.visit(function)
    return finder.nodes


def _nested_definition_diagnostics(
    path: Path,
    function: ast.FunctionDef,
) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []

    class DefinitionFinder(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is not function:
                diagnostics.append(
                    Diagnostic(
                        file=path.as_posix(),
                        message="Nested functions are not analyzed yet.",
                        severity="warning",
                        line=node.lineno,
                    )
                )
                return
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            diagnostics.append(
                Diagnostic(
                    file=path.as_posix(),
                    message="Nested async functions are not analyzed yet.",
                    severity="warning",
                    line=node.lineno,
                )
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            diagnostics.append(
                Diagnostic(
                    file=path.as_posix(),
                    message="Nested classes are not analyzed yet.",
                    severity="warning",
                    line=node.lineno,
                )
            )

    DefinitionFinder().visit(function)
    return diagnostics


def _collect_calls(
    parsed_files: Sequence[_ParsedFile],
    function_ids: Set[str],
) -> List[CallEdge]:
    calls: List[CallEdge] = []
    for parsed in parsed_files:
        for node in parsed.tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            caller = "{}.{}".format(parsed.module, node.name)
            imported_functions, imported_modules = _import_bindings(parsed)
            finder = _CallFinder(
                caller=caller,
                module=parsed.module,
                function_ids=function_ids,
                imported_functions=imported_functions,
                imported_modules=imported_modules,
            )
            for statement in node.body:
                finder.visit(statement)
            calls.extend(finder.calls)
    calls.sort(key=lambda item: (item.caller, item.line, item.callee))
    return calls


def _import_bindings(parsed: _ParsedFile) -> Tuple[Dict[str, str], Dict[str, str]]:
    imported_functions: Dict[str, str] = {}
    imported_modules: Dict[str, str] = {}
    for node in parsed.tree.body:
        if isinstance(node, ast.ImportFrom):
            module = _resolve_from_module(parsed, node)
            for alias in node.names:
                local_name = alias.asname or alias.name
                imported_modules[local_name] = ".".join(
                    part for part in (module, alias.name) if part
                )
                imported_functions[local_name] = ".".join(
                    part for part in (module, alias.name) if part
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                imported_modules[local_name] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
    return imported_functions, imported_modules


def _resolve_from_module(parsed: _ParsedFile, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package_parts = parsed.module.split(".")
    if not parsed.is_package_init and package_parts:
        package_parts.pop()
    remove_count = node.level - 1
    if remove_count > len(package_parts):
        return node.module or ""
    base = package_parts[: len(package_parts) - remove_count]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


class _CallFinder(ast.NodeVisitor):
    def __init__(
        self,
        caller: str,
        module: str,
        function_ids: Set[str],
        imported_functions: Dict[str, str],
        imported_modules: Dict[str, str],
    ) -> None:
        self.caller = caller
        self.module = module
        self.function_ids = function_ids
        self.imported_functions = imported_functions
        self.imported_modules = imported_modules
        self.calls: List[CallEdge] = []

    def visit_Call(self, node: ast.Call) -> None:
        callee = self._resolve_callee(node.func)
        if callee is not None:
            self.calls.append(
                CallEdge(
                    caller=self.caller,
                    callee=callee,
                    line=node.lineno,
                    expression=ast.unparse(node.func),
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def _resolve_callee(self, expression: ast.expr) -> Optional[str]:
        if isinstance(expression, ast.Name):
            imported = self.imported_functions.get(expression.id)
            if imported in self.function_ids:
                return imported
            local = "{}.{}".format(self.module, expression.id)
            return local if local in self.function_ids else None

        if isinstance(expression, ast.Attribute):
            parts: List[str] = []
            current: ast.expr = expression
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                parts.reverse()
                module = self.imported_modules.get(parts[0])
                if module:
                    target = ".".join([module] + parts[1:])
                    if target in self.function_ids:
                        return target
        return None
