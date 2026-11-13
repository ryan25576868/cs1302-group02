"""A small AST interpreter that produces interactive function challenges."""

import ast
import json
import math
import operator
from string import Formatter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..analyzer import analyze_project, analyze_source
from ..models import AnalysisResult, FunctionInfo

MAX_CALL_DEPTH = 8
MAX_STEPS = 120
MAX_AST_NODES = 800
MAX_INTEGER_BITS = 256
MAX_COLLECTION_ITEMS = 100


class SimulationError(ValueError):
    """Raised when source or values are outside the supported safe subset."""


@dataclass
class _Function:
    info: FunctionInfo
    node: ast.FunctionDef


@dataclass
class _Frame:
    function: _Function
    variables: Dict[str, Any]
    caller: Optional[str]


@dataclass(frozen=True)
class _ReturnFlow:
    value: Any


def _function_body(function: _Function) -> Sequence[ast.stmt]:
    body = function.node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


@dataclass
class _Step:
    kind: str
    function_id: str
    function_name: str
    file: str
    line: int
    expression: str
    prompt: str
    variables: Dict[str, Any]
    stack: List[Dict[str, Any]]
    expected: Any = None
    challenge: bool = False
    hint: str = ""
    choices: List[str] = field(default_factory=list)
    target: Optional[str] = None

    def public_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "function_id": self.function_id,
            "function_name": self.function_name,
            "file": self.file,
            "line": self.line,
            "expression": self.expression,
            "prompt": self.prompt,
            "variables": _json_safe(self.variables),
            "stack": _json_safe(self.stack),
            "challenge": self.challenge,
            "hint": self.hint,
            "choices": list(self.choices),
            "target": self.target,
        }


@dataclass
class PovSimulation:
    """An immutable challenge sequence with private expected answers."""

    function_id: str
    steps: Tuple[_Step, ...]
    sources: Dict[str, Dict[str, Any]]

    def public_dict(self) -> Dict[str, Any]:
        return {
            "function_id": self.function_id,
            "steps": [step.public_dict() for step in self.steps],
            "sources": self.sources,
        }

    def check(self, index: int, answer: Any) -> Dict[str, Any]:
        step = self._step(index)
        if not step.challenge:
            return {"correct": True, "feedback": "This step has no answer to check."}
        if _answers_equal(answer, step.expected):
            return {
                "correct": True,
                "feedback": "That's right! Your function can continue.",
                "answer": _json_safe(step.expected),
            }
        return {
            "correct": False,
            "feedback": "Not quite. Check the current values and try again.",
        }

    def hint(self, index: int) -> str:
        return self._step(index).hint

    def answer(self, index: int) -> Any:
        step = self._step(index)
        return _json_safe(step.expected)

    def _step(self, index: int) -> _Step:
        if index < 0 or index >= len(self.steps):
            raise SimulationError("The requested POV step does not exist.")
        return self.steps[index]


def build_simulation(
    project_root: str,
    function_id: str,
    arguments: Optional[Dict[str, Any]] = None,
) -> PovSimulation:
    """Create an interactive trace without importing or executing project code."""
    root = Path(project_root).resolve()
    analysis = analyze_project(str(root))
    infos = {function.id: function for function in analysis.functions}
    if function_id not in infos:
        raise SimulationError("That function was not found in the analyzed project.")
    return _build_simulation(
        analysis,
        _load_functions(root, infos),
        function_id,
        arguments,
    )


def build_simulation_from_source(
    source: str,
    function_id: str,
    arguments: Optional[Dict[str, Any]] = None,
    filename: str = "pasted.py",
) -> PovSimulation:
    """Create a POV trace from virtual source without writing it to disk."""
    analysis = analyze_source(source, filename)
    syntax_errors = [item for item in analysis.diagnostics if item.severity == "error"]
    if syntax_errors:
        diagnostic = syntax_errors[0]
        location = " on line {}".format(diagnostic.line) if diagnostic.line else ""
        raise SimulationError(
            "Cannot simulate pasted Python{}: {}".format(location, diagnostic.message)
        )
    infos = {function.id: function for function in analysis.functions}
    functions = _load_functions_from_sources({filename: source}, infos)
    return _build_simulation(analysis, functions, function_id, arguments)


def _build_simulation(
    analysis: AnalysisResult,
    functions: Dict[str, _Function],
    function_id: str,
    arguments: Optional[Dict[str, Any]],
) -> PovSimulation:
    infos = {function.id: function for function in analysis.functions}
    selected = infos.get(function_id)
    if selected is None:
        raise SimulationError("That function was not found in the analyzed project.")

    calls = {
        (call.caller, call.line, call.expression): call.callee
        for call in analysis.calls
    }
    builder = _SimulationBuilder(functions, calls)
    input_arguments = _validate_arguments(arguments or {})
    return builder.build(functions[function_id], input_arguments)


def _load_functions(root: Path, infos: Dict[str, FunctionInfo]) -> Dict[str, _Function]:
    by_file: Dict[str, List[FunctionInfo]] = {}
    for info in infos.values():
        by_file.setdefault(info.file, []).append(info)

    functions: Dict[str, _Function] = {}
    for relative, file_infos in by_file.items():
        source = (root / relative).read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as error:
            raise SimulationError(
                "Cannot simulate {}: {}".format(relative, error.msg)
            ) from error
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                function_id = "{}.{}".format(file_infos[0].module, node.name)
                info = next((item for item in file_infos if item.id == function_id), None)
                if info is not None:
                    functions[function_id] = _Function(info, node)
    return functions


def _load_functions_from_sources(
    sources: Dict[str, str],
    infos: Dict[str, FunctionInfo],
) -> Dict[str, _Function]:
    by_file: Dict[str, List[FunctionInfo]] = {}
    for info in infos.values():
        by_file.setdefault(info.file, []).append(info)

    functions: Dict[str, _Function] = {}
    for relative, file_infos in by_file.items():
        try:
            tree = ast.parse(sources[relative], filename=relative)
        except SyntaxError as error:
            raise SimulationError(
                "Cannot simulate {}: {}".format(relative, error.msg)
            ) from error
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                function_id = "{}.{}".format(file_infos[0].module, node.name)
                info = next((item for item in file_infos if item.id == function_id), None)
                if info is not None:
                    functions[function_id] = _Function(info, node)
    return functions


def _validate_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(arguments, dict):
        raise SimulationError("Arguments must be an object with parameter names and values.")
    if len(arguments) > 40:
        raise SimulationError("Too many function arguments.")
    validated: Dict[str, Any] = {}
    for name, value in arguments.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise SimulationError("Argument names must be valid parameter names.")
        validated[name] = _validate_json_value(value, name)
    return validated


def _validate_json_value(value: Any, label: str, depth: int = 0) -> Any:
    if depth > 8:
        raise SimulationError("{} is nested too deeply.".format(label))
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > 10000:
            raise SimulationError("{} is too long.".format(label))
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value.bit_length() > MAX_INTEGER_BITS:
            raise SimulationError("{} is too large.".format(label))
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SimulationError("{} must be a finite number.".format(label))
        return value
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise SimulationError("{} has too many items.".format(label))
        return [
            _validate_json_value(item, label, depth + 1)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS or not all(
            isinstance(key, str) for key in value
        ):
            raise SimulationError("{} must be a small object with string keys.".format(label))
        return {
            key: _validate_json_value(item, label, depth + 1)
            for key, item in value.items()
        }
    raise SimulationError("{} must be a JSON value.".format(label))


class _SimulationBuilder:
    def __init__(
        self,
        functions: Dict[str, _Function],
        call_targets: Dict[Tuple[str, int, str], str],
    ) -> None:
        self.functions = functions
        self.call_targets = call_targets
        self.steps: List[_Step] = []
        self.frames: List[_Frame] = []
        self.node_count = sum(
            1 for function in functions.values() for _ in ast.walk(function.node)
        )
        if self.node_count > MAX_AST_NODES:
            raise SimulationError("This project is too large for the POV simulator.")

    def build(self, function: _Function, arguments: Dict[str, Any]) -> PovSimulation:
        self._validate_function(function, set())
        self._invoke(function, arguments, None)
        if not self.steps:
            raise SimulationError("This function has no supported steps to simulate.")
        sources = {
            function_id: {
                "file": item.info.file,
                "line": min(
                    (decorator.lineno for decorator in item.node.decorator_list),
                    default=item.node.lineno,
                ),
                "source": item.info.source,
            }
            for function_id, item in self.functions.items()
        }
        return PovSimulation(function.info.id, tuple(self.steps), sources)

    def _validate_function(self, function: _Function, seen: set) -> None:
        if function.info.id in seen:
            return
        seen.add(function.info.id)
        node = function.node
        arguments = node.args
        if arguments.vararg or arguments.kwarg or arguments.kwonlyargs or arguments.posonlyargs:
            raise SimulationError(
                "{} uses advanced parameter syntax. The simulator supports simple positional parameters.".format(
                    function.info.name
                )
            )
        for default in arguments.defaults:
            self._validate_default(default, function)
            self._validate_expr(default, function)
        self._validate_statements(_function_body(function), function, seen)

    def _validate_statements(
        self,
        statements: Sequence[ast.stmt],
        function: _Function,
        seen: set,
    ) -> None:
        for statement in statements:
            if isinstance(statement, ast.Return):
                if statement.value is not None:
                    self._validate_expr(statement.value, function, seen)
            elif isinstance(statement, ast.Assign):
                if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                    self._unsupported(statement, "Only assignments to one local variable are supported.")
                self._validate_expr(statement.value, function, seen)
            elif isinstance(statement, ast.AnnAssign):
                if not isinstance(statement.target, ast.Name):
                    self._unsupported(statement, "Only local variable annotations are supported.")
                self._validate_expr(statement.annotation, function, seen)
                if statement.value is not None:
                    self._validate_expr(statement.value, function, seen)
            elif isinstance(statement, ast.If):
                self._validate_expr(statement.test, function, seen)
                self._validate_statements(statement.body, function, seen)
                self._validate_statements(statement.orelse, function, seen)
            elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                self._validate_expr(statement.value, function, seen)
            elif isinstance(statement, ast.Pass):
                continue
            else:
                self._unsupported(
                    statement,
                    "Supported statements are local assignments, if/else, direct function calls, and return.",
                )

    def _validate_expr(
        self,
        expression: ast.expr,
        function: _Function,
        seen: Optional[set] = None,
    ) -> None:
        if isinstance(expression, (ast.Constant, ast.Name)):
            return
        if isinstance(expression, ast.BinOp) and type(expression.op) in _BINARY_OPERATORS:
            self._validate_expr(expression.left, function, seen)
            self._validate_expr(expression.right, function, seen)
            return
        if isinstance(expression, ast.UnaryOp) and type(expression.op) in _UNARY_OPERATORS:
            self._validate_expr(expression.operand, function, seen)
            return
        if isinstance(expression, ast.BoolOp) and isinstance(expression.op, (ast.And, ast.Or)):
            for value in expression.values:
                self._validate_expr(value, function, seen)
            return
        if isinstance(expression, ast.Compare):
            if not all(type(operator_node) in _COMPARISON_OPERATORS for operator_node in expression.ops):
                self._unsupported(expression, "This comparison operator is not supported.")
            self._validate_expr(expression.left, function, seen)
            for comparator in expression.comparators:
                self._validate_expr(comparator, function, seen)
            return
        if isinstance(expression, (ast.List, ast.Tuple)):
            if len(expression.elts) > MAX_COLLECTION_ITEMS:
                self._unsupported(expression, "This collection has too many items.")
            for item in expression.elts:
                self._validate_expr(item, function, seen)
            return
        if isinstance(expression, ast.Dict):
            if len(expression.keys) > MAX_COLLECTION_ITEMS:
                self._unsupported(expression, "This object has too many items.")
            for key, value in zip(expression.keys, expression.values):
                if key is None:
                    self._unsupported(expression, "Dictionary unpacking is not supported.")
                self._validate_expr(key, function, seen)
                self._validate_expr(value, function, seen)
            return
        if isinstance(expression, ast.Call):
            if _is_string_format_call(expression):
                self._validate_string_format(expression, function, seen)
                return
            if not isinstance(expression.func, (ast.Name, ast.Attribute)):
                self._unsupported(expression, "Only direct calls to project functions are supported.")
            if any(keyword.arg is None for keyword in expression.keywords):
                self._unsupported(expression, "Keyword unpacking is not supported.")
            for argument in expression.args:
                if isinstance(argument, ast.Starred):
                    self._unsupported(expression, "Starred call arguments are not supported.")
                self._validate_expr(argument, function, seen)
            for keyword in expression.keywords:
                self._validate_expr(keyword.value, function, seen)
            target = self._resolve_call(expression, function)
            if target not in self.functions:
                self._unsupported(
                    expression,
                    "Call {!r} cannot be resolved to a project function.".format(
                        ast.unparse(expression.func)
                    ),
                )
            if seen is not None:
                self._validate_function(self.functions[target], seen)
            return
        self._unsupported(
            expression,
            "This expression is outside the safe POV subset: {}.".format(
                type(expression).__name__
            ),
        )

    def _validate_string_format(
        self,
        call: ast.Call,
        function: _Function,
        seen: Optional[set],
    ) -> None:
        if any(keyword.arg is None for keyword in call.keywords):
            self._unsupported(call, "String formatting does not support keyword unpacking.")
        if any(isinstance(argument, ast.Starred) for argument in call.args):
            self._unsupported(call, "String formatting does not support unpacked arguments.")
        for argument in call.args:
            self._validate_expr(argument, function, seen)
        for keyword in call.keywords:
            self._validate_expr(keyword.value, function, seen)

        template = call.func.value.value
        if len(template) > 10000:
            self._unsupported(call, "String format templates are limited to 10,000 characters.")
        positional_count = len(call.args)
        keyword_names = {keyword.arg for keyword in call.keywords}
        automatic_index = 0
        try:
            fields = list(Formatter().parse(template))
        except ValueError as error:
            raise SimulationError(
                "This string format template is invalid at line {}.".format(call.lineno)
            ) from error
        for _, field_name, format_spec, conversion in fields:
            if field_name is None:
                continue
            if format_spec or conversion is not None:
                self._unsupported(
                    call,
                    "String formatting supports simple replacement fields only.",
                )
            if field_name == "":
                field_index = automatic_index
                automatic_index += 1
                if field_index >= positional_count:
                    self._unsupported(call, "A string format field has no matching argument.")
            elif field_name.isdecimal():
                if len(field_name) > len(str(positional_count)) or int(field_name) >= positional_count:
                    self._unsupported(call, "A string format field has no matching argument.")
            elif field_name.isidentifier():
                if field_name not in keyword_names:
                    self._unsupported(call, "A string format field has no matching argument.")
            else:
                self._unsupported(
                    call,
                    "String formatting does not support attribute or index access.",
                )

    def _validate_default(self, expression: ast.expr, function: _Function) -> None:
        allowed = (ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.UnaryOp, ast.BinOp)
        if not isinstance(expression, allowed):
            self._unsupported(
                expression,
                "Default values must be safe literals or literal arithmetic.",
            )
        if isinstance(expression, ast.List):
            children = expression.elts
        elif isinstance(expression, ast.Tuple):
            children = expression.elts
        elif isinstance(expression, ast.Dict):
            if any(key is None for key in expression.keys):
                self._unsupported(expression, "Dictionary unpacking is not supported.")
            children = [
                node
                for pair in zip(expression.keys, expression.values)
                for node in pair
            ]
        elif isinstance(expression, ast.UnaryOp):
            children = [expression.operand]
        elif isinstance(expression, ast.BinOp):
            if type(expression.op) not in _BINARY_OPERATORS:
                self._unsupported(expression, "This default operator is not supported.")
            children = [expression.left, expression.right]
        else:
            children = []
        for child in children:
            self._validate_default(child, function)

    def _unsupported(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", None)
        detail = " at line {}".format(line) if line is not None else ""
        raise SimulationError(message + detail)

    def _resolve_call(self, call: ast.Call, function: _Function) -> Optional[str]:
        expression = ast.unparse(call.func)
        return self.call_targets.get(
            (function.info.id, call.lineno, expression)
        )

    def _invoke(
        self,
        function: _Function,
        provided: Dict[str, Any],
        caller: Optional[str],
    ) -> Any:
        if len(self.frames) >= MAX_CALL_DEPTH:
            raise SimulationError(
                "Call depth exceeded the safe limit of {}.".format(MAX_CALL_DEPTH)
            )
        frame = _Frame(function, self._bind(function, provided), caller)
        self.frames.append(frame)
        self._append_step(
            _Step(
                kind="enter",
                function_id=function.info.id,
                function_name=function.info.name,
                file=function.info.file,
                line=function.node.lineno,
                expression=function.info.name + "(" + _format_mapping(frame.variables) + ")",
                prompt="You are now {}. The caller handed you these arguments.".format(
                    function.info.name
                ),
                variables=dict(frame.variables),
                stack=self._stack(),
            )
        )
        try:
            flow = self._execute_statements(_function_body(function), frame)
        finally:
            self.frames.pop()
        return flow.value if flow is not None else None

    def _bind(self, function: _Function, provided: Dict[str, Any]) -> Dict[str, Any]:
        node = function.node
        names = [argument.arg for argument in node.args.args]
        unknown = set(provided) - set(names)
        if unknown:
            raise SimulationError(
                "Unknown parameter(s) for {}: {}.".format(
                    function.info.name, ", ".join(sorted(unknown))
                )
            )

        defaults: Dict[str, Any] = {}
        positional_defaults = node.args.defaults
        if positional_defaults:
            default_names = names[-len(positional_defaults):]
            for name, default in zip(default_names, positional_defaults):
                defaults[name] = self._eval(default, {}, function)

        variables: Dict[str, Any] = {}
        for name in names:
            if name in provided:
                variables[name] = provided[name]
            elif name in defaults:
                variables[name] = defaults[name]
            else:
                raise SimulationError(
                    "Enter a value for the required parameter {!r}.".format(name)
                )
        return variables

    def _execute_statements(
        self,
        statements: Sequence[ast.stmt],
        frame: _Frame,
    ) -> Optional[_ReturnFlow]:
        for statement in statements:
            if isinstance(statement, ast.Pass):
                continue
            if isinstance(statement, ast.Return):
                value = self._eval(statement.value, frame.variables, frame.function) if statement.value else None
                expression = ast.unparse(statement.value) if statement.value else "None"
                self._append_step(
                    _Step(
                        kind="return",
                        function_id=frame.function.info.id,
                        function_name=frame.function.info.name,
                        file=frame.function.info.file,
                        line=statement.lineno,
                        expression=expression,
                        prompt="What value does {} return to its caller?".format(
                            frame.function.info.name
                        ),
                        variables=dict(frame.variables),
                        stack=self._stack(),
                        expected=value,
                        challenge=True,
                        hint="Evaluate the return expression using the local variables shown, then submit that value.",
                    )
                )
                return _ReturnFlow(value)
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                expression = statement.value
                if expression is None:
                    continue
                name = statement.targets[0].id if isinstance(statement, ast.Assign) else statement.target.id
                result = self._eval(expression, frame.variables, frame.function)
                expects_answer = _contains_arithmetic(expression)
                if expects_answer:
                    self._append_step(
                        _Step(
                            kind="arithmetic",
                            function_id=frame.function.info.id,
                            function_name=frame.function.info.name,
                            file=frame.function.info.file,
                            line=statement.lineno,
                            expression=ast.unparse(expression),
                            prompt="Work out the value assigned to {}.".format(name),
                            variables=dict(frame.variables),
                            stack=self._stack(),
                            expected=result,
                            challenge=True,
                            hint="Substitute the local values into the expression, then follow the operator order.",
                            target=name,
                        )
                    )
                else:
                    self._append_step(
                        _Step(
                            kind="assignment",
                            function_id=frame.function.info.id,
                            function_name=frame.function.info.name,
                            file=frame.function.info.file,
                            line=statement.lineno,
                            expression=ast.unparse(expression),
                            prompt="Bind the expression result to {}.".format(name),
                            variables=dict(frame.variables),
                            stack=self._stack(),
                            expected=result,
                            target=name,
                        )
                    )
                frame.variables[name] = result
                continue
            if isinstance(statement, ast.If):
                condition = self._eval(statement.test, frame.variables, frame.function)
                result = bool(condition)
                self._append_step(
                    _Step(
                        kind="condition",
                        function_id=frame.function.info.id,
                        function_name=frame.function.info.name,
                        file=frame.function.info.file,
                        line=statement.test.lineno,
                        expression=ast.unparse(statement.test),
                        prompt="Does this condition evaluate to True or False?",
                        variables=dict(frame.variables),
                        stack=self._stack(),
                        expected=result,
                        challenge=True,
                        hint="Substitute the local values and compare them. Then choose the branch that matches.",
                        choices=["True", "False"],
                    )
                )
                branch = statement.body if result else statement.orelse
                flow = self._execute_statements(branch, frame)
                if flow is not None:
                    return flow
                continue
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                self._eval(statement.value, frame.variables, frame.function)
                continue
            self._unsupported(statement, "Unsupported statement.")
        return None

    def _eval(self, expression: Optional[ast.expr], variables: Dict[str, Any], function: _Function) -> Any:
        if expression is None:
            return None
        if isinstance(expression, ast.Constant):
            return _validate_json_value(expression.value, "literal")
        if isinstance(expression, ast.Name):
            if expression.id not in variables:
                raise SimulationError(
                    "Name {!r} is not available in {}.".format(
                        expression.id, function.info.name
                    )
                )
            return variables[expression.id]
        if isinstance(expression, ast.List):
            return [self._eval(item, variables, function) for item in expression.elts]
        if isinstance(expression, ast.Tuple):
            return tuple(self._eval(item, variables, function) for item in expression.elts)
        if isinstance(expression, ast.Dict):
            try:
                return {
                    self._eval(key, variables, function): self._eval(value, variables, function)
                    for key, value in zip(expression.keys, expression.values)
                }
            except TypeError as error:
                raise SimulationError("Dictionary keys must be simple immutable values.") from error
        if isinstance(expression, ast.BinOp):
            left = self._eval(expression.left, variables, function)
            right = self._eval(expression.right, variables, function)
            if isinstance(expression.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 10:
                raise SimulationError("Exponents must be between -10 and 10 in the POV simulator.")
            if isinstance(expression.op, ast.Mult) and (
                isinstance(left, (str, list, tuple)) or isinstance(right, (str, list, tuple))
            ):
                sequence = left if isinstance(left, (str, list, tuple)) else right
                count = right if sequence is left else left
                if not isinstance(count, int) or count < 0 or count > MAX_COLLECTION_ITEMS:
                    raise SimulationError("Repeated values are limited to 100 items.")
            try:
                result = _BINARY_OPERATORS[type(expression.op)](left, right)
            except (ArithmeticError, TypeError, ValueError, OverflowError) as error:
                raise SimulationError("Cannot safely calculate this expression: {}.".format(error)) from error
            return _validate_runtime_result(result)
        if isinstance(expression, ast.UnaryOp):
            value = self._eval(expression.operand, variables, function)
            try:
                result = _UNARY_OPERATORS[type(expression.op)](value)
            except (ArithmeticError, TypeError, ValueError) as error:
                raise SimulationError("Cannot safely calculate this expression: {}.".format(error)) from error
            return _validate_runtime_result(result)
        if isinstance(expression, ast.BoolOp):
            result = self._eval(expression.values[0], variables, function)
            for item in expression.values[1:]:
                if isinstance(expression.op, ast.And):
                    if not result:
                        break
                    result = self._eval(item, variables, function)
                else:
                    if result:
                        break
                    result = self._eval(item, variables, function)
            return _validate_runtime_result(result)
        if isinstance(expression, ast.Compare):
            left = self._eval(expression.left, variables, function)
            for operation, comparator in zip(expression.ops, expression.comparators):
                right = self._eval(comparator, variables, function)
                try:
                    comparison = _COMPARISON_OPERATORS[type(operation)](left, right)
                except (TypeError, ValueError) as error:
                    raise SimulationError("Cannot safely compare these values.") from error
                if not comparison:
                    return False
                left = right
            return True
        if isinstance(expression, ast.Call):
            return self._eval_call(expression, variables, function)
        raise SimulationError(
            "This expression is outside the safe POV subset: {}.".format(
                type(expression).__name__
            )
        )

    def _eval_call(self, call: ast.Call, variables: Dict[str, Any], caller: _Function) -> Any:
        if _is_string_format_call(call):
            return self._eval_string_format(call, variables, caller)
        target_id = self._resolve_call(call, caller)
        if target_id is None or target_id not in self.functions:
            self._unsupported(call, "This call does not resolve to a project function.")
        target = self.functions[target_id]
        arguments: Dict[str, Any] = {}
        positional_values = [self._eval(argument, variables, caller) for argument in call.args]
        keyword_values = {
            keyword.arg: self._eval(keyword.value, variables, caller)
            for keyword in call.keywords
        }
        parameter_names = [argument.arg for argument in target.node.args.args]
        if len(positional_values) > len(parameter_names):
            raise SimulationError("Too many arguments in call to {}.".format(target.info.name))
        for name, value in zip(parameter_names, positional_values):
            arguments[name] = value
        for name, value in keyword_values.items():
            if name in arguments:
                raise SimulationError("Argument {!r} was provided twice.".format(name))
            arguments[name] = value

        self._append_step(
            _Step(
                kind="function_call",
                function_id=caller.info.id,
                function_name=caller.info.name,
                file=caller.info.file,
                line=call.lineno,
                expression=ast.unparse(call.func),
                prompt="Which project function is being called here?",
                variables=dict(variables),
                stack=self._stack(),
                expected=target.info.name,
                challenge=True,
                hint="Look at the function name immediately before the parentheses.",
                choices=sorted({item.info.name for item in self.functions.values()}),
                target=target_id,
            )
        )
        result = self._invoke(target, arguments, caller.info.id)
        self._append_step(
            _Step(
                kind="call_return",
                function_id=caller.info.id,
                function_name=caller.info.name,
                file=caller.info.file,
                line=call.lineno,
                expression=ast.unparse(call) + " → " + _format_value(result),
                prompt="The called function returned. Its value is back with you.",
                variables=dict(variables),
                stack=self._stack(),
                expected=result,
            )
        )
        return result

    def _eval_string_format(
        self,
        call: ast.Call,
        variables: Dict[str, Any],
        function: _Function,
    ) -> str:
        template = call.func.value.value
        positional = [self._eval(argument, variables, function) for argument in call.args]
        named = {
            keyword.arg: self._eval(keyword.value, variables, function)
            for keyword in call.keywords
        }
        automatic_index = 0
        result = []
        total_length = 0
        for literal, field_name, _, _ in Formatter().parse(template):
            result.append(literal)
            total_length += len(literal)
            if field_name is None:
                continue
            if field_name == "":
                value = positional[automatic_index]
                automatic_index += 1
            elif field_name.isdecimal():
                value = positional[int(field_name)]
            else:
                value = named[field_name]
            rendered = str(value)
            total_length += len(rendered)
            if total_length > 10000:
                raise SimulationError("Formatted strings are limited to 10,000 characters.")
            result.append(rendered)
        return _validate_runtime_result("".join(result))

    def _append_step(self, step: _Step) -> None:
        if len(self.steps) >= MAX_STEPS:
            raise SimulationError(
                "The simulation reached its safe limit of {} steps.".format(MAX_STEPS)
            )
        self.steps.append(step)

    def _stack(self) -> List[Dict[str, Any]]:
        return [
            {
                "function_id": frame.function.info.id,
                "function_name": frame.function.info.name,
                "variables": dict(frame.variables),
            }
            for frame in self.frames
        ]


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _is_string_format_call(expression: ast.Call) -> bool:
    return (
        isinstance(expression.func, ast.Attribute)
        and expression.func.attr == "format"
        and isinstance(expression.func.value, ast.Constant)
        and isinstance(expression.func.value.value, str)
    )


_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}
_COMPARISON_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}
_BINARY_OPERATORS = {key: value for key, value in _BINARY_OPERATORS.items()}


def _validate_runtime_result(value: Any) -> Any:
    safe = _validate_json_value(
        list(value) if isinstance(value, tuple) else value,
        "result",
    )
    return safe


def _json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _answers_equal(answer: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(answer, bool) and answer is expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(answer, (int, float)) and not isinstance(answer, bool) and answer == expected
    return answer == _json_safe(expected)


def _format_mapping(values: Dict[str, Any]) -> str:
    return ", ".join(
        "{}={}".format(name, _format_value(value))
        for name, value in values.items()
    )


def _format_value(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)


def _contains_arithmetic(expression: ast.AST) -> bool:
    return any(isinstance(node, ast.BinOp) for node in ast.walk(expression))
