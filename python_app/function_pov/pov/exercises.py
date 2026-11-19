"""Deterministic, safe exercise variants for Function POV."""

from __future__ import annotations

import ast
import copy
import json
import math
from dataclasses import dataclass
from typing import Any, Iterator

from ..analyzer import analyze_source
from .engine import (
    PovSimulation,
    SimulationError,
    build_program_simulation_from_source,
    build_simulation_from_source,
)

MAX_GENERATION_ATTEMPTS = 64


class ExerciseGenerationError(ValueError):
    """Raised when no supported, unused exercise can be generated."""


@dataclass(frozen=True)
class GeneratedExercise:
    level: str
    mode: str
    source: str
    filename: str
    function_id: str | None
    arguments: dict[str, Any]
    concepts: tuple[str, ...]
    simulation: PovSimulation
    logic_change: str | None = None


class PracticeExerciseGenerator:
    """Generate bounded variants without executing generated or user code."""

    def __init__(self) -> None:
        self._considered: set[str] = set()

    def similar_logic_availability(
        self,
        mode: str,
        source: str,
        filename: str,
        function_id: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> str | None:
        candidates = self._similar_logic_candidates(
            mode, source, filename, function_id, arguments or {}
        )
        found_pattern = False
        for candidate_source, candidate_function, candidate_arguments, _ in candidates:
            if _logic_change_explanation(
                source,
                candidate_source,
                mode,
                function_id,
                filename,
            ) is None:
                continue
            found_pattern = True
            key = self._variant_key(
                mode, candidate_source, candidate_function, candidate_arguments
            )
            if key in self._considered:
                continue
            try:
                simulation = self._build_simulation(
                    mode,
                    candidate_source,
                    filename,
                    candidate_function,
                    candidate_arguments,
                )
            except SimulationError:
                continue
            if any(step.challenge for step in simulation.steps):
                return None
        if not found_pattern:
            return "This code does not match a supported Similar Logic pattern."
        return "No unused Similar Logic exercise passed safe simulation."

    def generate(
        self,
        level: str,
        mode: str,
        source: str,
        filename: str,
        function_id: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> GeneratedExercise:
        if mode not in {"code", "function"}:
            raise ExerciseGenerationError("This practice mode is not supported.")
        if level == "new_values":
            candidates = self._new_value_candidates(
                mode, source, filename, function_id, arguments or {}
            )
        elif level == "similar_logic":
            candidates = self._similar_logic_candidates(
                mode, source, filename, function_id, arguments or {}
            )
        else:
            raise ExerciseGenerationError("This exercise level is not supported.")

        supported_pattern = False
        generation_attempts = 0
        attempt_limit_reached = False
        for candidate_source, candidate_function, candidate_arguments, concepts in candidates:
            logic_change = None
            if level == "similar_logic":
                logic_change = _logic_change_explanation(
                    source,
                    candidate_source,
                    mode,
                    function_id,
                    filename,
                )
                if logic_change is None:
                    continue
            supported_pattern = True
            key = self._variant_key(
                mode, candidate_source, candidate_function, candidate_arguments
            )
            if key in self._considered:
                continue
            generation_attempts += 1
            if generation_attempts > MAX_GENERATION_ATTEMPTS:
                attempt_limit_reached = True
                break
            self._considered.add(key)
            try:
                simulation = self._build_simulation(
                    mode,
                    candidate_source,
                    filename,
                    candidate_function,
                    candidate_arguments,
                )
            except SimulationError:
                continue
            if not any(step.challenge for step in simulation.steps):
                continue
            return GeneratedExercise(
                level=level,
                mode=mode,
                source=candidate_source,
                filename=filename,
                function_id=candidate_function,
                arguments=dict(candidate_arguments),
                concepts=concepts,
                simulation=simulation,
                logic_change=logic_change,
            )

        if level == "similar_logic" and not supported_pattern:
            raise ExerciseGenerationError(
                "This code does not match a supported Similar Logic pattern."
            )
        if attempt_limit_reached:
            raise ExerciseGenerationError(
                "Exercise search reached its safe candidate limit without finding a new variant."
            )
        if level == "new_values":
            raise ExerciseGenerationError(
                "No safe, unused New Values exercise is available for this code."
            )
        raise ExerciseGenerationError(
            "No unused Similar Logic exercise passed safe simulation."
        )

    @staticmethod
    def _variant_key(
        mode: str,
        source: str,
        function_id: str | None,
        arguments: dict[str, Any],
    ) -> str:
        return json.dumps(
            [mode, source, function_id, arguments],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _build_simulation(
        mode: str,
        source: str,
        filename: str,
        function_id: str | None,
        arguments: dict[str, Any],
    ) -> PovSimulation:
        if mode == "code":
            return build_program_simulation_from_source(source, filename)
        if function_id is None:
            raise SimulationError("A function must be selected for this exercise.")
        analysis = analyze_source(source, filename)
        selected = next(
            (function for function in analysis.functions if function.id == function_id),
            None,
        )
        if selected is None:
            selected = next(
                (
                    function for function in analysis.functions
                    if function.name == function_id
                ),
                None,
            )
        if selected is None:
            raise SimulationError("The generated function could not be resolved.")
        return build_simulation_from_source(
            source, selected.id, arguments, filename
        )

    def _new_value_candidates(
        self,
        mode: str,
        source: str,
        filename: str,
        function_id: str | None,
        arguments: dict[str, Any],
    ) -> Iterator[tuple[str, str | None, dict[str, Any], tuple[str, ...]]]:
        if mode == "code":
            yield from self._program_value_candidates(source)
            return
        if function_id is None:
            return
        effective = self._effective_function_arguments(
            source, filename, function_id, arguments
        )
        concepts = _selected_function_concepts(source, filename, function_id)
        function = _selected_function_node(source, filename, function_id)
        if function is not None:
            for name, variant in _branch_boundary_candidates(function, effective):
                updated = dict(effective)
                updated[name] = variant
                yield source, function_id, updated, concepts
        for name, value in effective.items():
            for variant in _value_variants(value):
                updated = dict(effective)
                updated[name] = variant
                yield source, function_id, updated, concepts

    @staticmethod
    def _program_value_candidates(
        source: str,
    ) -> Iterator[tuple[str, str | None, dict[str, Any], tuple[str, ...]]]:
        try:
            module = ast.parse(source)
        except SyntaxError:
            return
        updated_names = {
            node.target.id
            for node in ast.walk(module)
            if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)
        }
        concepts = _concepts(module)
        input_nodes: dict[str, ast.AST] = {}
        input_values: dict[str, Any] = {}
        for statement in module.body:
            if isinstance(statement, ast.Assign):
                if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                    continue
                name = statement.targets[0].id
                value_node = statement.value
            elif isinstance(statement, ast.AnnAssign):
                if not isinstance(statement.target, ast.Name) or statement.value is None:
                    continue
                name = statement.target.id
                value_node = statement.value
            else:
                continue
            if name in updated_names:
                continue
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                continue
            input_nodes[name] = value_node
            input_values[name] = value
        for name, variant in _branch_boundary_candidates(module, input_values):
            candidate = _replace_source_segment(
                source, input_nodes[name], repr(variant)
            )
            if candidate is not None:
                yield candidate, None, {}, concepts
        for name, value_node in input_nodes.items():
            value = input_values[name]
            for variant in _value_variants(value):
                candidate = _replace_source_segment(source, value_node, repr(variant))
                if candidate is not None:
                    yield candidate, None, {}, concepts
        for node in ast.walk(module):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Name)
                or node.func.id != "range"
            ):
                continue
            for argument in node.args[:2]:
                try:
                    value = ast.literal_eval(argument)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, bool) or not isinstance(value, int):
                    continue
                for variant in _value_variants(value):
                    candidate = _replace_source_segment(
                        source, argument, repr(variant)
                    )
                    if candidate is not None:
                        yield candidate, None, {}, concepts

    @staticmethod
    def _effective_function_arguments(
        source: str,
        filename: str,
        function_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        analysis = analyze_source(source, filename)
        function_info = next(
            (item for item in analysis.functions if item.id == function_id),
            None,
        )
        if function_info is None:
            function_info = next(
                (item for item in analysis.functions if item.name == function_id),
                None,
            )
        if function_info is None:
            return dict(arguments)
        try:
            module = ast.parse(source, filename=filename)
        except SyntaxError:
            return dict(arguments)
        function = next(
            (
                node for node in module.body
                if isinstance(node, ast.FunctionDef)
                and node.name == function_info.name
            ),
            None,
        )
        if function is None:
            return dict(arguments)
        names = [item.arg for item in function.args.args]
        defaults: dict[str, Any] = {}
        default_names = names[-len(function.args.defaults):] if function.args.defaults else []
        for name, node in zip(default_names, function.args.defaults):
            try:
                defaults[name] = ast.literal_eval(node)
            except (ValueError, TypeError):
                continue
        effective: dict[str, Any] = {}
        for name in names:
            if name in arguments:
                effective[name] = arguments[name]
            elif name in defaults:
                effective[name] = defaults[name]
        return effective

    def _similar_logic_candidates(
        self,
        mode: str,
        source: str,
        filename: str,
        function_id: str | None,
        arguments: dict[str, Any],
    ) -> Iterator[tuple[str, str | None, dict[str, Any], tuple[str, ...]]]:
        if mode == "code":
            yield from self._program_logic_templates(source)
            return
        if function_id is None:
            return
        yield from self._function_logic_templates(
            source, filename, function_id, arguments
        )

    @staticmethod
    def _program_logic_templates(
        source: str,
    ) -> Iterator[tuple[str, str | None, dict[str, Any], tuple[str, ...]]]:
        try:
            module = ast.parse(source)
        except SyntaxError:
            return
        if any(isinstance(node, ast.FunctionDef) for node in module.body):
            return
        body = _module_body_without_docstring(module.body)
        nodes = list(ast.walk(module))
        fors = [node for node in nodes if isinstance(node, ast.For)]
        whiles = [node for node in nodes if isinstance(node, ast.While)]
        branches = [node for node in nodes if isinstance(node, ast.If)]
        updates = [node for node in nodes if isinstance(node, ast.AugAssign)]
        prints = [
            node for node in nodes
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]
        other_calls = [
            node for node in nodes
            if isinstance(node, ast.Call)
            and not (
                isinstance(node.func, ast.Name)
                and node.func.id in {"print", "range"}
            )
        ]
        if other_calls:
            return

        if (
            len(prints) == 1
            and len(fors) == 1
            and not whiles
            and len(branches) == 1
            and len(updates) == 1
            and len(body) == 4
            and isinstance(body[0], (ast.Assign, ast.AnnAssign))
            and isinstance(body[1], (ast.Assign, ast.AnnAssign))
            and body[2] is fors[0]
            and isinstance(body[3], ast.Expr)
            and len(fors[0].body) == 1
            and isinstance(fors[0].body[0], ast.If)
            and len(fors[0].body[0].body) == 1
            and isinstance(fors[0].body[0].body[0], ast.AugAssign)
            and not fors[0].body[0].orelse
            and isinstance(fors[0].iter, ast.Name)
            and branches[0] in list(ast.walk(fors[0]))
            and updates[0] in list(ast.walk(branches[0]))
        ):
            templates = (
                (
                    "prices = [5, 2, 8]\n"
                    "total = 0\n"
                    "for price in prices:\n"
                    "    if price >= 5:\n"
                    "        total += price + 1\n"
                    "print(total)\n",
                    ("condition", "loop", "variable update", "arithmetic", "output"),
                ),
                (
                    "scores = [4, 9, 6]\n"
                    "passed = 0\n"
                    "for score in scores:\n"
                    "    if score >= 6:\n"
                    "        passed += score + 1\n"
                    "print(passed)\n",
                    ("condition", "loop", "variable update", "arithmetic", "output"),
                ),
            )
            for template, concepts in templates:
                yield template, None, {}, concepts
            return

        if (
            len(prints) == 1
            and len(fors) == 1
            and not whiles
            and not branches
            and len(updates) == 1
            and len(body) == 4
            and isinstance(body[0], (ast.Assign, ast.AnnAssign))
            and isinstance(body[1], (ast.Assign, ast.AnnAssign))
            and body[2] is fors[0]
            and isinstance(body[3], ast.Expr)
            and len(fors[0].body) == 1
            and isinstance(fors[0].body[0], ast.AugAssign)
            and isinstance(fors[0].iter, ast.Name)
        ):
            templates = (
                (
                    "values = [3, 1, 4]\n"
                    "total = 0\n"
                    "for value in values:\n"
                    "    total += value + 1\n"
                    "print(total)\n",
                    ("loop", "variable update", "arithmetic", "output"),
                ),
                (
                    "values = [2, 5, 3]\n"
                    "total = 0\n"
                    "for value in values:\n"
                    "    total += value - 1\n"
                    "print(total)\n",
                    ("loop", "variable update", "arithmetic", "output"),
                ),
            )
            for template, concepts in templates:
                yield template, None, {}, concepts
            return

        if (
            len(prints) == 1
            and len(whiles) == 1
            and not fors
            and not branches
            and len(updates) >= 2
            and len(body) == 4
            and isinstance(body[0], (ast.Assign, ast.AnnAssign))
            and isinstance(body[1], (ast.Assign, ast.AnnAssign))
            and body[2] is whiles[0]
            and isinstance(body[3], ast.Expr)
            and len(whiles[0].body) == 2
            and all(isinstance(item, ast.AugAssign) for item in whiles[0].body)
        ):
            templates = (
                (
                    "count = 3\n"
                    "total = 0\n"
                    "while count > 0:\n"
                    "    total += count + 1\n"
                    "    count -= 1\n"
                    "print(total)\n",
                    ("loop", "condition", "variable update", "arithmetic", "output"),
                ),
                (
                    "count = 4\n"
                    "total = 0\n"
                    "while count > 0:\n"
                    "    total += count - 1\n"
                    "    count -= 1\n"
                    "print(total)\n",
                    ("loop", "condition", "variable update", "arithmetic", "output"),
                ),
            )
            for template, concepts in templates:
                yield template, None, {}, concepts
            return

        if (
            len(prints) >= 1
            and len(branches) == 1
            and not fors and not whiles and not updates
            and len(body) == 2
            and isinstance(body[0], (ast.Assign, ast.AnnAssign))
            and body[1] is branches[0]
            and branches[0].body
            and branches[0].orelse
            and all(
                isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Call)
                and isinstance(item.value.func, ast.Name)
                and item.value.func.id == "print"
                for item in branches[0].body + branches[0].orelse
            )
        ):
            templates = (
                (
                    "score = 6\n"
                    "if score >= 5:\n"
                    "    print('ready')\n"
                    "else:\n"
                    "    print('keep practising')\n",
                    ("condition", "branch", "output"),
                ),
                (
                    "temperature = 2\n"
                    "if temperature > 0:\n"
                    "    print('above zero')\n"
                    "else:\n"
                    "    print('zero or below')\n",
                    ("condition", "branch", "output"),
                ),
            )
            for template, concepts in templates:
                yield template, None, {}, concepts

    @staticmethod
    def _function_logic_templates(
        source: str,
        filename: str,
        function_id: str,
        arguments: dict[str, Any],
    ) -> Iterator[tuple[str, str | None, dict[str, Any], tuple[str, ...]]]:
        analysis = analyze_source(source, filename)
        info = next(
            (item for item in analysis.functions if item.id == function_id),
            None,
        )
        if info is None:
            info = next(
                (item for item in analysis.functions if item.name == function_id),
                None,
            )
        if info is None:
            return
        try:
            module = ast.parse(source, filename=filename)
        except SyntaxError:
            return
        function = next(
            (
                node for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == info.name
            ),
            None,
        )
        if (
            function is None
            or function.args.posonlyargs
            or function.args.kwonlyargs
            or function.decorator_list
            or function.returns is not None
        ):
            return
        if function.args.vararg or function.args.kwarg:
            return
        if any(argument.annotation is not None for argument in function.args.args):
            return
        if any(
            isinstance(node, ast.FunctionDef) and node is not function
            for node in ast.walk(function)
        ):
            return
        names = [item.arg for item in function.args.args]
        body = _function_body_without_docstring(function.body)
        effective_arguments = PracticeExerciseGenerator._effective_function_arguments(
            source, filename, info.id, arguments
        )
        optional_names = (
            set(names[-len(function.args.defaults):])
            if function.args.defaults else set()
        )
        nodes = list(ast.walk(function))
        branches = [node for node in nodes if isinstance(node, ast.If)]
        fors = [node for node in nodes if isinstance(node, ast.For)]
        whiles = [node for node in nodes if isinstance(node, ast.While)]
        returns = [node for node in nodes if isinstance(node, ast.Return)]
        updates = [node for node in nodes if isinstance(node, ast.AugAssign)]
        calls = [
            node for node in nodes
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        call_names = {node.func.id for node in calls}
        helper_names = {
            node.name for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name != info.name
        }
        project_calls = call_names & helper_names

        if (
            fors and len(fors) == 1 and not whiles and not branches
            and updates and returns and len(names) == 1
            and len(body) == 3
            and isinstance(body[0], ast.Assign)
            and isinstance(body[1], ast.For)
            and body[1] is fors[0]
            and isinstance(body[2], ast.Return)
            and len(fors[0].body) == 1
            and isinstance(fors[0].body[0], ast.AugAssign)
            and isinstance(fors[0].iter, ast.Name)
            and fors[0].iter.id == names[0]
            and isinstance(body[2].value, ast.Name)
            and isinstance(body[1].target, ast.Name)
            and isinstance(fors[0].body[0].target, ast.Name)
            and body[2].value.id == fors[0].body[0].target.id
            and isinstance(body[0].targets[0], ast.Name)
            and body[0].targets[0].id == body[2].value.id
            and not calls
        ):
            parameter = names[0]
            for values, expression in (
                ([2, 5, 3], "item + 1"),
                ([4, 1, 6], "item - 1"),
            ):
                template = (
                    f"def {info.name}({_function_signature(function)}):\n"
                    "    total = 0\n"
                    f"    for item in {parameter}:\n"
                    f"        total += {expression}\n"
                    "    return total\n"
                )
                yield template, info.id, {parameter: values}, (
                    "function parameters", "loop", "variable update", "arithmetic", "return"
                )
            return

        if (
            project_calls and len(names) == 1 and returns
            and not branches and not fors and not whiles
            and len(body) == 1 and isinstance(body[0], ast.Return)
            and isinstance(body[0].value, ast.BinOp)
            and any(isinstance(node, ast.BinOp) for node in nodes)
            and _is_number(effective_arguments.get(names[0]))
            and len(calls) == 1
            and len(project_calls) == 1
        ):
            parameter = names[0]
            helper = "_pov_adjust"
            while helper == info.name or helper in helper_names:
                helper += "_"
            template = (
                f"def {helper}(value):\n"
                "    return value * 2\n\n"
                f"def {info.name}({_function_signature(function)}):\n"
                f"    return {helper}({parameter}) * 2\n"
            )
            for value in (3, 5):
                candidate_arguments = dict(arguments)
                candidate_arguments[parameter] = value
                yield template, info.id, candidate_arguments, (
                    "function parameters", "function call", "arithmetic", "return"
                )
            return

        branch_body_supported = (
            len(body) == 1
            and isinstance(body[0], ast.If)
            and len(body[0].body) == 1
            and isinstance(body[0].body[0], ast.Return)
            and len(body[0].orelse) == 1
            and isinstance(body[0].orelse[0], ast.Return)
        ) or (
            len(body) == 2
            and isinstance(body[0], ast.If)
            and len(body[0].body) == 1
            and isinstance(body[0].body[0], ast.Return)
            and not body[0].orelse
            and isinstance(body[1], ast.Return)
        )
        if (
            branches and len(branches) == 1 and returns and not fors and not whiles
            and len(names) in {1, 2}
            and branch_body_supported
            and not project_calls
            and not calls
            and any(isinstance(node, (ast.BinOp, ast.AugAssign)) for node in nodes)
        ):
            first = names[0]
            second = names[1] if len(names) == 2 else None
            boolean_names = [
                name for name in names
                if isinstance(effective_arguments.get(name), bool)
            ]
            numeric_names = [
                name for name in names
                if _is_number(effective_arguments.get(name))
            ]
            if len(names) == 2 and len(boolean_names) == 1 and len(numeric_names) == 1:
                branch = body[0]
                if not (
                    isinstance(branch, ast.If)
                    and isinstance(branch.test, ast.Name)
                    and branch.test.id == boolean_names[0]
                ):
                    return
                flag = boolean_names[0]
                value_name = numeric_names[0]
                discount_rules = (
                    (f"{value_name} - 2", value_name),
                    (f"{value_name} * 0.8", value_name),
                )
                for member_value, nonmember_value in discount_rules:
                    template = (
                        f"def {info.name}({_function_signature(function)}):\n"
                        f"    if {flag}:\n"
                        f"        return {member_value}\n"
                        f"    return {nonmember_value}\n"
                    )
                    yield template, info.id, dict(arguments), (
                        "function parameters", "condition", "branch", "arithmetic", "return"
                    )
                return
            if not all(_is_number(effective_arguments.get(name)) for name in names):
                return
            for threshold in (5, 7):
                candidate_arguments = dict(arguments)
                if second:
                    body = (
                        f"    if {first} >= {threshold}:\n"
                        f"        return {first} + {second}\n"
                        f"    return {first} - {second}\n"
                    )
                    if first not in candidate_arguments:
                        candidate_arguments[first] = threshold + 1
                    if second not in candidate_arguments:
                        candidate_arguments[second] = 2
                else:
                    body = (
                        f"    if {first} >= {threshold}:\n"
                        f"        return {first} + 1\n"
                        f"    return {first} - 1\n"
                    )
                    if first not in candidate_arguments and first not in optional_names:
                        candidate_arguments[first] = threshold + 1
                template = f"def {info.name}({_function_signature(function)}):\n" + body
                yield template, info.id, candidate_arguments, (
                    "function parameters", "condition", "branch", "arithmetic", "return"
                )
            return

        if (
            returns and not branches and not fors and not whiles
            and not calls and not project_calls and len(names) in {1, 2}
            and len(body) == 1 and isinstance(body[0], ast.Return)
        ):
            if not any(isinstance(node, ast.BinOp) for node in nodes):
                return
            if not all(_is_number(effective_arguments.get(name)) for name in names):
                return
            for multiplier in (2, 3):
                if len(names) == 1:
                    first = names[0]
                    expression = f"{first} * {multiplier} + 1"
                    candidate_arguments = dict(arguments)
                    if first not in candidate_arguments:
                        candidate_arguments[first] = 4 + multiplier
                else:
                    first, second = names
                    expression = f"{first} + {second} * {multiplier}"
                    candidate_arguments = dict(arguments)
                    if first not in candidate_arguments and first not in optional_names:
                        candidate_arguments[first] = 3
                    if second not in candidate_arguments and second not in optional_names:
                        candidate_arguments[second] = 2 + multiplier
                template = (
                    f"def {info.name}({_function_signature(function)}):\n"
                    f"    return {expression}\n"
                )
                yield template, info.id, candidate_arguments, (
                    "function parameters", "arithmetic", "return"
                )


def _replace_source_segment(source: str, node: ast.AST, replacement: str) -> str | None:
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    lines = source.splitlines(keepends=True)
    if node.lineno < 1 or node.end_lineno > len(lines):
        return None

    def absolute_offset(line_number: int, byte_column: int) -> int:
        prefix = lines[line_number - 1].encode("utf-8")[:byte_column]
        character_column = len(prefix.decode("utf-8"))
        return sum(len(line) for line in lines[:line_number - 1]) + character_column

    start = absolute_offset(node.lineno, node.col_offset)
    end = absolute_offset(node.end_lineno, node.end_col_offset)
    if start < 0 or end < start or end > len(source):
        return None
    return source[:start] + replacement + source[end:]


def _module_body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _function_body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    return _module_body_without_docstring(body)


def _function_signature(function: ast.FunctionDef) -> str:
    names = [item.arg for item in function.args.args]
    defaults = function.args.defaults
    default_names = names[-len(defaults):] if defaults else []
    default_values = {
        name: ast.unparse(value)
        for name, value in zip(default_names, defaults)
    }
    return ", ".join(
        name + ("=" + default_values[name] if name in default_values else "")
        for name in names
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _selected_function_concepts(
    source: str,
    filename: str,
    function_id: str,
) -> tuple[str, ...]:
    analysis = analyze_source(source, filename)
    info = next(
        (item for item in analysis.functions if item.id == function_id),
        None,
    )
    if info is None:
        info = next(
            (item for item in analysis.functions if item.name == function_id),
            None,
        )
    if info is None:
        return ("function parameters",)
    try:
        module = ast.parse(source, filename=filename)
    except SyntaxError:
        return ("function parameters",)
    function = next(
        (
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == info.name
        ),
        None,
    )
    if function is None:
        return ("function parameters",)
    concepts = list(_concepts(function))
    if function.args.args:
        concepts.insert(0, "function parameters")
    return tuple(dict.fromkeys(concepts))


def _selected_function_node(
    source: str,
    filename: str,
    function_id: str,
) -> ast.FunctionDef | None:
    try:
        module = ast.parse(source, filename=filename)
    except SyntaxError:
        return None
    analysis = analyze_source(source, filename)
    info = next(
        (item for item in analysis.functions if item.id == function_id),
        None,
    )
    if info is None:
        info = next(
            (item for item in analysis.functions if item.name == function_id),
            None,
        )
    if info is None:
        return None
    return next(
        (
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == info.name
        ),
        None,
    )


def _branch_boundary_candidates(
    scope: ast.AST,
    input_values: dict[str, Any],
) -> Iterator[tuple[str, Any]]:
    loop_inputs = {
        node.target.id: node.iter.id
        for node in ast.walk(scope)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and isinstance(node.iter, ast.Name)
        and node.iter.id in input_values
    }

    def input_name(name: str) -> str | None:
        if name in input_values:
            return name
        return loop_inputs.get(name)

    for node in ast.walk(scope):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        if len(node.comparators) != 1:
            continue
        left, right = node.left, node.comparators[0]
        for value_node, threshold_node, value_is_left in (
            (left, right, True),
            (right, left, False),
        ):
            if not isinstance(value_node, ast.Name):
                continue
            name = input_name(value_node.id)
            if name is None:
                continue
            if isinstance(threshold_node, ast.Constant):
                threshold = threshold_node.value
            elif isinstance(threshold_node, ast.Name):
                threshold = input_values.get(threshold_node.id)
            else:
                continue
            if not _is_number(threshold):
                continue
            for variant in _boundary_value_variants(
                input_values[name], threshold, node.ops[0], value_is_left
            ):
                yield name, variant


def _boundary_value_variants(
    value: Any,
    threshold: int | float,
    operator: ast.cmpop,
    value_is_left: bool,
) -> list[Any]:
    if not math.isfinite(float(threshold)):
        return []
    if isinstance(value, (list, tuple)):
        if not value or not all(
            _is_number(item) and type(item) is type(value[0]) for item in value
        ):
            return []
        points = _boundary_points(value[0], threshold)
        if not points:
            return []
        candidate = [points[index % len(points)] for index in range(len(value))]
        if candidate == list(value):
            return []
        return [tuple(candidate) if isinstance(value, tuple) else candidate]
    if not _is_number(value):
        return []
    points = _boundary_points(value, threshold)
    original_result = (
        _compare(operator, value, threshold)
        if value_is_left
        else _compare(operator, threshold, value)
    )

    def priority(candidate: int | float) -> tuple[int, int, float]:
        result = (
            _compare(operator, candidate, threshold)
            if value_is_left
            else _compare(operator, threshold, candidate)
        )
        return (
            0 if result != original_result else 1,
            0 if candidate == threshold else 1,
            abs(candidate - threshold),
        )

    return [
        candidate
        for candidate in sorted(points, key=priority)
        if candidate != value
    ]


def _boundary_points(value: int | float, threshold: int | float) -> list[int | float]:
    if isinstance(value, float):
        return [float(threshold - 1), float(threshold), float(threshold + 1)]
    lower = math.floor(threshold)
    upper = math.ceil(threshold)
    return list(dict.fromkeys((lower - 1, lower, upper, upper + 1)))


def _compare(operator: ast.cmpop, left: int | float, right: int | float) -> bool:
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    return False


def _logic_change_explanation(
    original_source: str,
    candidate_source: str,
    mode: str,
    function_id: str | None,
    filename: str,
) -> str | None:
    original_function = (
        _selected_function_node(original_source, filename, function_id)
        if mode == "function" and function_id is not None
        else None
    )
    if mode == "function" and original_function is None:
        return None
    candidate_function_id = (
        original_function.name if original_function is not None else function_id
    )
    original = _logic_ast(original_source, mode, function_id, filename)
    candidate = _logic_ast(
        candidate_source, mode, candidate_function_id, filename
    )
    if original is None or candidate is None:
        return None
    if _normalized_logic_signature(original) == _normalized_logic_signature(candidate):
        if mode != "function":
            return None
        try:
            original_module = ast.parse(original_source, filename=filename)
            candidate_module = ast.parse(candidate_source, filename=filename)
        except SyntaxError:
            return None
        if _normalized_logic_signature(
            original_module
        ) == _normalized_logic_signature(candidate_module):
            return None
        original, candidate = original_module, candidate_module

    original_comparisons = [
        type(operator)
        for node in ast.walk(original)
        if isinstance(node, ast.Compare)
        for operator in node.ops
    ]
    candidate_comparisons = [
        type(operator)
        for node in ast.walk(candidate)
        if isinstance(node, ast.Compare)
        for operator in node.ops
    ]
    if original_comparisons != candidate_comparisons:
        return "The comparison rule changed; practise evaluating the condition and choosing a branch."

    operator_types = (ast.operator, ast.boolop, ast.unaryop)
    original_operators = [
        type(node)
        for node in ast.walk(original)
        if isinstance(node, operator_types)
    ]
    candidate_operators = [
        type(node)
        for node in ast.walk(candidate)
        if isinstance(node, operator_types)
    ]
    if original_operators != candidate_operators:
        return "The arithmetic or variable-update rule changed; practise tracing each calculation."

    flow_types = (ast.If, ast.For, ast.While)
    original_flow = [
        type(node) for node in ast.walk(original) if isinstance(node, flow_types)
    ]
    candidate_flow = [
        type(node) for node in ast.walk(candidate) if isinstance(node, flow_types)
    ]
    if original_flow != candidate_flow:
        return "The branch or loop structure changed; practise tracing the new execution path."
    return "The expression structure changed; practise tracing how it affects the result."


def _logic_ast(
    source: str,
    mode: str,
    function_id: str | None,
    filename: str,
) -> ast.AST | None:
    try:
        module = ast.parse(source, filename=filename)
    except SyntaxError:
        return None
    if mode == "code":
        return module
    if function_id is None:
        return None
    function = _selected_function_node(source, filename, function_id)
    if function is None:
        return None
    return ast.Module(body=function.body, type_ignores=[])


def _normalized_logic_signature(node: ast.AST) -> str:
    normalized = copy.deepcopy(node)
    for item in ast.walk(normalized):
        if isinstance(item, ast.Name):
            item.id = "_"
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            item.name = "_"
        elif isinstance(item, ast.arg):
            item.arg = "_"
        elif isinstance(item, ast.keyword) and item.arg is not None:
            item.arg = "_"
        elif isinstance(item, ast.Constant):
            item.value = None
    return ast.dump(normalized, include_attributes=False)


def _value_variants(value: Any) -> list[Any]:
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        return [value + offset for offset in (5, -5, 10, -10, 2, -2)]
    if isinstance(value, float) and math.isfinite(value):
        return [
            value + offset
            for offset in (5.0, -5.0, 10.0, -10.0, 2.0, -2.0)
            if math.isfinite(value + offset)
        ]
    if isinstance(value, str):
        if len(value) > 9990:
            return []
        return [value + " " + str(number) for number in range(1, 5)]
    if isinstance(value, (list, tuple)):
        variants: list[Any] = []
        if value and all(_is_number(item) for item in value):
            for offset in (5, -5, 10, -10):
                changed = [item + offset for item in value]
                variants.append(
                    tuple(changed) if isinstance(value, tuple) else changed
                )
        elif value and all(isinstance(item, bool) for item in value):
            changed = [not item for item in value]
            variants.append(tuple(changed) if isinstance(value, tuple) else changed)
        elif value and all(isinstance(item, str) for item in value):
            for number in range(1, 5):
                changed = [item + " " + str(number) for item in value]
                variants.append(tuple(changed) if isinstance(value, tuple) else changed)
        for index, item in enumerate(value):
            if isinstance(item, (list, tuple)):
                continue
            for replacement in _value_variants(item):
                changed = list(value)
                changed[index] = replacement
                variants.append(tuple(changed) if isinstance(value, tuple) else changed)
                if len(variants) >= 24:
                    return variants
        return variants
    return []


def _concepts(node: ast.AST) -> tuple[str, ...]:
    nodes = list(ast.walk(node))
    concepts: list[str] = []
    if any(isinstance(item, ast.If) for item in nodes):
        concepts.append("condition")
        concepts.append("branch")
    if any(isinstance(item, (ast.For, ast.While)) for item in nodes):
        concepts.append("loop")
    if any(isinstance(item, ast.AugAssign) for item in nodes):
        concepts.append("variable update")
    if any(isinstance(item, (ast.BinOp, ast.AugAssign)) for item in nodes):
        concepts.append("arithmetic")
    if any(
        isinstance(item, ast.FunctionDef) and item.args.args
        for item in nodes
    ):
        concepts.append("function parameters")
    if any(isinstance(item, ast.Return) for item in nodes):
        concepts.append("return")
    if any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == "print"
        for item in nodes
    ):
        concepts.append("output")
    if any(
        isinstance(item, ast.Call)
        and not (
            isinstance(item.func, ast.Name)
            and item.func.id in {"print", "range"}
        )
        for item in nodes
    ):
        concepts.append("function call")
    return tuple(dict.fromkeys(concepts))
