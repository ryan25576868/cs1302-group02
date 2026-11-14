"""Python-native analysis path for Prism.

The parser, structural model, explanation and bounded trace for Python now live
in Python. The JS engine remains available for the other supported languages
while they are migrated in later phases.
"""

from __future__ import annotations

import ast
import html
import re
from dataclasses import dataclass, field
from typing import Any

LANGUAGE = {
    "id": "python", "name": "Python", "short": "PY", "monogram": "Py",
    "extension": "py", "family": "python", "entry": "script",
    "tagline": "Readable by design",
    "blurb": "Indentation, lists, and beginner-friendly syntax.",
    "tint": "#DCEAF7", "tintInk": "#275676", "wash": "#EFF6FB",
    "hoverWash": "#E4F0F9", "lineComment": "#", "blockComment": None,
    "keywords": [
        "def", "return", "if", "elif", "else", "for", "while", "in", "not",
        "and", "or", "is", "None", "True", "False", "class", "import", "from",
        "as", "try", "except", "finally", "raise", "with", "yield", "lambda",
        "pass", "break", "continue", "global", "nonlocal", "async", "await",
        "del", "assert", "self",
    ],
    "literals": ["True", "False", "None"],
    "capabilities": ["functions", "loops", "conditionals", "lists"],
    "interpreter": "full",
}


class _NodeFactory:
    def __init__(self, source: str):
        self.source = source
        self.lines = source.split("\n")
        self.next_id = 1
        self.assignments: list[dict[str, Any]] = []
        self.action_nodes: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.function_names: set[str] = set()
        self.assigned_names: set[str] = set()
        self.counts = {"loops": 0, "conditions": 0, "returns": 0, "maxDepth": 0}

    def nid(self) -> str:
        self.next_id += 1
        return f"node-{self.next_id}"

    def line(self, node: ast.AST) -> int:
        return int(getattr(node, "lineno", 1) or 1)

    def end_line(self, node: ast.AST) -> int:
        return int(getattr(node, "end_lineno", self.line(node)) or self.line(node))

    def text(self, node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return self.lines[self.line(node) - 1].strip() if self.line(node) <= len(self.lines) else ""

    def block(self, statements: list[ast.stmt], depth: int = 0, start: int | None = None) -> dict[str, Any]:
        children = [self.convert(statement, depth + 1) for statement in statements]
        first = start or (children[0]["startLine"] if children else 1)
        last = children[-1]["endLine"] if children else first
        return {"type": "block", "startLine": first, "endLine": last, "children": children}

    def action(self, statement: ast.stmt, subtype: str, **extra: Any) -> dict[str, Any]:
        line = self.line(statement)
        text = self.lines[line - 1].strip() if line <= len(self.lines) else self.text(statement)
        action: dict[str, Any] = {
            "subtype": subtype, "raw": text, "line": line,
            "expressionText": self.text(statement), **extra,
        }
        return {
            "type": "action", "id": self.nid(), "startLine": line,
            "endLine": self.end_line(statement), "header": text, "text": text,
            "action": action,
        }

    def record_assignment(self, node: dict[str, Any], target: str, expression: str,
                          dependencies: list[str], operator: str, is_declaration: bool,
                          scope: str = "Global") -> dict[str, Any]:
        action = node["action"]
        action.update({
            "subtype": "declaration" if is_declaration else "assignment",
            "assignment": True, "targetDisplay": target, "targetName": target,
            "targetChain": target, "isDeclaration": is_declaration,
            "isUpdate": not is_declaration or operator != "=",
            "declarationType": "", "operator": operator,
            "expressionText": expression, "expressionAST": None,
        })
        record = {
            "id": f"assignment-{len(self.assignments) + 1}", "nodeId": node["id"],
            "line": node["startLine"], "endLine": node["endLine"],
            "target": target, "targetName": target, "expressionText": expression,
            "dependencies": dependencies, "operator": operator,
            "isDeclaration": is_declaration, "declarationType": "",
            "scope": scope, "action": action,
        }
        self.assignments.append(record)
        node["assignmentRecord"] = record
        return record

    def convert(self, node: ast.stmt, depth: int = 0) -> dict[str, Any]:
        self.counts["maxDepth"] = max(self.counts["maxDepth"], depth)
        line = self.line(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return self.convert_function(node, depth)
        if isinstance(node, ast.ClassDef):
            body = self.block(node.body, depth)
            item = {
                "type": "class", "id": self.nid(), "startLine": line,
                "endLine": self.end_line(node), "header": f"class {node.name}",
                "name": node.name, "body": body, "keyword": "class",
            }
            self.classes.append(item)
            return item
        if isinstance(node, ast.If):
            self.counts["conditions"] += 1
            consequent = self.block(node.body, depth, line)
            alternate = self.block(node.orelse, depth) if node.orelse else None
            return {
                "type": "if", "id": self.nid(), "startLine": line,
                "endLine": self.end_line(node),
                "header": f"if {self.text(node.test)}",
                "condition": self.text(node.test),
                "consequent": consequent, "alternate": alternate,
                "hasElse": bool(node.orelse), "keyword": "if",
            }
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.counts["loops"] += 1
            body = self.block(node.body, depth, line)
            return {
                "type": "for", "id": self.nid(), "startLine": line,
                "endLine": self.end_line(node),
                "header": f"for {self.text(node.target)} in {self.text(node.iter)}",
                "loopHeader": f"{self.text(node.target)} in {self.text(node.iter)}",
                "body": body, "keyword": "for",
                "loopMeta": {"style": "for"},
            }
        if isinstance(node, ast.While):
            self.counts["loops"] += 1
            body = self.block(node.body, depth, line)
            return {
                "type": "while", "id": self.nid(), "startLine": line,
                "endLine": self.end_line(node),
                "header": f"while {self.text(node.test)}",
                "condition": self.text(node.test), "body": body, "keyword": "while",
            }
        if isinstance(node, ast.Assign):
            target = self.text(node.targets[0]) if node.targets else "value"
            expression = self.text(node.value)
            first = target not in self.assigned_names and isinstance(node.targets[0], ast.Name)
            self.assigned_names.add(target)
            action_node = self.action(node, "declaration" if first else "assignment",
                                      expressionText=expression)
            deps = sorted({n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)})
            self.record_assignment(action_node, target, expression, deps, "=", first)
            self.action_nodes.append(action_node)
            return action_node
        if isinstance(node, ast.AnnAssign):
            target = self.text(node.target)
            expression = self.text(node.value) if node.value is not None else ""
            first = target not in self.assigned_names
            self.assigned_names.add(target)
            action_node = self.action(node, "declaration", expressionText=expression)
            deps = sorted({n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}) if node.value else []
            self.record_assignment(action_node, target, expression, deps, "=", first)
            self.action_nodes.append(action_node)
            return action_node
        if isinstance(node, ast.AugAssign):
            target = self.text(node.target)
            right = self.text(node.value)
            operator = self.op(node.op)
            expression = f"{target} {operator} {right}"
            action_node = self.action(node, "assignment", operator=operator,
                                      expressionText=expression, rhs=right)
            deps = sorted({target, *{n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}})
            self.record_assignment(action_node, target, expression, deps, operator, False)
            self.action_nodes.append(action_node)
            return action_node
        if isinstance(node, ast.Return):
            self.counts["returns"] += 1
            return self.action(node, "return", expressionText=self.text(node.value) if node.value else "")
        if isinstance(node, ast.Break):
            return self.action(node, "break")
        if isinstance(node, ast.Continue):
            return self.action(node, "continue")
        if isinstance(node, ast.Pass):
            return self.action(node, "pass")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return self.action(node, "import")
        if isinstance(node, (ast.Expr, ast.Raise, ast.Assert)):
            value = getattr(node, "value", None)
            is_print = isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "print"
            is_call = isinstance(value, ast.Call)
            subtype = "print" if is_print else "call" if is_call else "expression"
            extra: dict[str, Any] = {}
            if is_print:
                extra = {"printKind": "python", "expressionText": self.text(value)}
            elif is_call:
                extra = {"expressionText": self.text(value), "calleeName": self.text(value.func)}
            action_node = self.action(node, subtype, **extra)
            self.action_nodes.append(action_node)
            return action_node
        # Fallback for try/with/other structures: keep a readable structural leaf.
        return {
            "type": "action", "id": self.nid(), "startLine": line,
            "endLine": self.end_line(node),
            "header": self.text(node), "text": self.text(node),
            "action": {"subtype": "expression", "raw": self.text(node), "line": line,
                       "expressionText": self.text(node)},
        }

    def convert_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, depth: int) -> dict[str, Any]:
        body = self.block(node.body, depth, self.line(node) + 1)
        params = []
        for arg in node.args.posonlyargs + node.args.args:
            params.append({"name": arg.arg, "type": "", "defaultValue": None, "raw": arg.arg})
        for arg in node.args.kwonlyargs:
            params.append({"name": arg.arg, "type": "", "defaultValue": None, "raw": arg.arg})
        item = {
            "type": "function", "id": self.nid(), "startLine": self.line(node),
            "endLine": self.end_line(node),
            "header": f"def {node.name}({', '.join(p['name'] for p in params)})",
            "name": node.name, "params": params, "returnType": "",
            "body": body, "keyword": "def", "scopeName": node.name,
        }
        item["actionCount"] = len([n for n in ast.walk(node) if isinstance(n, (ast.Assign, ast.AugAssign, ast.Expr))])
        self.functions.append(item)
        self.function_names.add(node.name)
        return item

    @staticmethod
    def op(node: ast.operator) -> str:
        return {
            ast.Add: "+=", ast.Sub: "-=", ast.Mult: "*=", ast.Div: "/=",
        }.get(type(node), "=")


@dataclass
class TraceState:
    steps: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""
    warnings: list[str] = field(default_factory=list)
    complete: bool = False
    stopped_reason: str | None = None
    function_calls: int = 0
    iterations: int = 0
    scopes: list[dict[str, Any]] = field(default_factory=list)
    call_stack: list[str] = field(default_factory=list)
    max_steps: int = 420
    lines: list[str] = field(default_factory=list)

    def add_step(self, line: int, kind: str, title: str, detail: str,
                 code: str = "", extra: Any = None, scope: str = "Global") -> int:
        if len(self.steps) >= self.max_steps:
            if not self.warnings:
                self.warnings.append(f"The trace reached its {self.max_steps}-step limit.")
            raise StopIteration
        index = len(self.steps)
        previous = self.steps[-1]["output"] if self.steps else ""
        self.steps.append({
            "index": index, "line": line, "endLine": line, "kind": kind,
            "title": title, "detail": detail,
            "vars": self.snapshot(scope), "output": self.output,
            "outputDelta": self.output[len(previous):], "callStack": list(self.call_stack),
            "scope": scope, "code": code, "extra": extra,
        })
        return index

    def snapshot(self, scope: str) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for frame in reversed(self.scopes):
            for name, value in frame.items():
                if name in found:
                    continue
                found[name] = {
                    "name": name, "display": display(value),
                    "type": value_type(value), "scope": scope, "changed": False,
                }
        return list(found.values())[:20]

    def event(self, kind: str, line: int, **data: Any) -> None:
        self.events.append({
            "kind": kind, "line": line, "target": data.get("target"),
            "name": data.get("name"), "expressionText": data.get("expressionText"),
            "operator": data.get("operator"), "value": display(data.get("value")),
            "valueType": value_type(data.get("value")),
            "scope": data.get("scope", "Global"),
            "dependencies": data.get("dependencies", []),
            "stepIndex": len(self.steps) - 1 if self.steps else 0,
            "index": len(self.events),
        })


def display(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(display(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{display(k)}: {display(v)}" for k, v in value.items()) + "}"
    return str(value)


def value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if callable(value):
        return "function"
    return "unknown"


class _ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


class _PyRunner:
    def __init__(self, root: dict[str, Any], source: str, analysis: dict[str, Any]):
        self.root = root
        self.trace = TraceState(lines=source.split("\n"))
        self.functions: dict[str, dict[str, Any]] = {fn["name"]: fn for fn in analysis["functions"]}
        self.global_scope: dict[str, Any] = {}
        self.trace.scopes = [self.global_scope]
        self.current_line = 1

    def run(self) -> dict[str, Any]:
        t = self.trace
        t.add_step(1, "start", "Program starts",
                   "This is a safe simulated run. Prism follows the code locally; your browser never executes it.",
                   code=t.lines[0].strip() if t.lines else "")
        try:
            self.exec_block(self.root["body"]["children"], self.global_scope, "Global")
            t.complete = True
            t.add_step(len(t.lines), "end", "Program ends",
                       "The program finished. The final output is shown in the terminal.",
                       code="")
        except StopIteration:
            t.stopped_reason = "step_limit"
        except _ReturnSignal:
            t.complete = True
        except Exception as error:  # pragma: no cover - defensive boundary
            t.warnings.append(f"The trace stopped at line {self.current_line}: {error}")
            t.stopped_reason = "error"
        return {
            "steps": t.steps, "events": t.events, "output": t.output,
            "warnings": t.warnings, "complete": t.complete,
            "stoppedReason": t.stopped_reason, "entryName": "Program",
            "functionCalls": t.function_calls, "iterations": t.iterations,
            "finalVars": t.snapshot("Global"), "callStackSupported": True,
            "interpreter": "python-safe-ast",
        }

    def exec_block(self, nodes: list[dict[str, Any]], scope: dict[str, Any], scope_name: str) -> None:
        for node in nodes:
            self.exec_node(node, scope, scope_name)

    def exec_node(self, node: dict[str, Any], scope: dict[str, Any], scope_name: str) -> None:
        kind = node.get("type")
        self.current_line = node.get("startLine", 1)
        if kind == "function":
            scope[node["name"]] = ("function", node)
            return
        if kind == "class":
            return
        if kind == "if":
            value = self.eval(node["condition"], scope)
            self.trace.event("condition", self.current_line, expressionText=node["condition"], value=value)
            self.trace.add_step(self.current_line, "condition", f"Check {node['condition']}",
                                f"The condition evaluates to {display(value)}.",
                                code=node["header"], scope=scope_name, extra={"value": display(value)})
            branch = node["consequent"] if value else node.get("alternate")
            if branch:
                self.trace.scopes.append({})
                self.exec_block(branch["children"], scope, scope_name)
                self.trace.scopes.pop()
            return
        if kind == "for":
            iterable = self.eval(node.get("loopHeader", "").split(" in ", 1)[-1], scope)
            if not isinstance(iterable, (list, tuple, range)):
                self.trace.warnings.append(f"The loop on line {self.current_line} could not be iterated safely.")
                return
            target = node.get("loopHeader", "").split(" in ", 1)[0].strip()
            for value in iterable:
                self.trace.iterations += 1
                scope[target] = value
                self.trace.event("loop-target", self.current_line, target=target, name=target,
                                 expressionText=self._iter_text(node), value=value, dependencies=[])
                self.trace.add_step(self.current_line, "iteration", f"Loop pass {self.trace.iterations}",
                                    f"`{target}` receives `{display(value)}`.",
                                    code=node["header"], scope=scope_name)
                try:
                    self.exec_block(node["body"]["children"], scope, scope_name)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    break
            return
        if kind == "while":
            guard = 0
            while self.eval(node.get("condition", "False"), scope) and guard < 60:
                guard += 1
                self.trace.iterations += 1
                self.trace.add_step(self.current_line, "iteration", f"Loop pass {self.trace.iterations}",
                                    f"`{node.get('condition')}` is still true.",
                                    code=node["header"], scope=scope_name)
                try:
                    self.exec_block(node["body"]["children"], scope, scope_name)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    break
            return
        if kind == "action":
            self.exec_action(node, scope, scope_name)

    def _iter_text(self, node: dict[str, Any]) -> str:
        return node.get("loopHeader", "").split(" in ", 1)[-1]

    def exec_action(self, node: dict[str, Any], scope: dict[str, Any], scope_name: str) -> None:
        action = node.get("action") or {}
        subtype = action.get("subtype")
        text_line = node.get("text", "")
        if subtype in {"return"}:
            value = self.eval(action.get("expressionText", ""), scope)
            self.trace.event("return", self.current_line, value=value)
            self.trace.add_step(self.current_line, "return", "Return a value",
                                f"Returns `{display(value)}`.", code=text_line,
                                scope=scope_name, extra={"value": display(value)})
            raise _ReturnSignal(value)
        if subtype == "break":
            raise _BreakSignal
        if subtype == "continue":
            raise _ContinueSignal
        if subtype in {"declaration", "assignment"}:
            target = action.get("targetDisplay") or action.get("targetName")
            expression = action.get("expressionText", "")
            operator = action.get("operator", "=")
            if operator != "=" and action.get("rhs"):
                old = scope.get(str(target), 0)
                right = self.eval(action["rhs"], scope)
                if operator == "+=":
                    value = old + right
                elif operator == "-=":
                    value = old - right
                elif operator == "*=":
                    value = old * right
                elif operator == "/=":
                    value = old / right
                else:
                    value = right
            else:
                value = self.eval(expression, scope)
            is_decl = bool(action.get("isDeclaration"))
            scope[str(target)] = value
            self.trace.event(
                "assignment", self.current_line, target=target, name=target,
                expressionText=expression, operator=action.get("operator", "="), value=value,
                dependencies=action.get("dependencies", []), scope=scope_name,
            )
            self.trace.add_step(self.current_line, "assign", f"Set {target}",
                                f"The right side ({expression}) is evaluated and stored in {target}, which now holds {display(value)}.",
                                code=text_line, scope=scope_name,
                                extra={"target": target, "value": display(value)})
            return
        if subtype == "print":
            args = self._print_args(action.get("expressionText", ""), scope)
            text = " ".join(display(arg) for arg in args)
            self.trace.output += text + "\n"
            self.trace.event("print", self.current_line, value=text)
            self.trace.add_step(self.current_line, "print", "Print output",
                                f"Appends `{text}` to the output.", code=text_line,
                                scope=scope_name, extra={"value": text})
            return
        if subtype == "call":
            self.eval(action.get("expressionText", ""), scope)
            return
        if subtype in {"import", "comment", "empty", "pass"}:
            return

    def _print_args(self, text: str, scope: dict[str, Any]) -> list[Any]:
        try:
            call = ast.parse(text, mode="eval").body
            if isinstance(call, ast.Call):
                return [self.eval(ast.unparse(arg), scope) for arg in call.args]
        except Exception:
            pass
        return []

    def eval(self, expression: str, scope: dict[str, Any]) -> Any:
        if not expression:
            return None
        try:
            tree = ast.parse(expression, mode="eval").body
        except SyntaxError:
            return None
        return self._eval_node(tree, scope)

    def _eval_node(self, node: ast.AST, scope: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in {"True", "False", "None"}:
                return {"True": True, "False": False, "None": None}[node.id]
            return scope.get(node.id, 0)
        if isinstance(node, ast.List):
            return [self._eval_node(v, scope) for v in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(v, scope) for v in node.elts)
        if isinstance(node, ast.Dict):
            return {self._eval_node(k, scope): self._eval_node(v, scope) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, scope)
            right = self._eval_node(node.right, scope)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            return 0
        if isinstance(node, ast.UnaryOp):
            value = self._eval_node(node.operand, scope)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BoolOp):
            values = [self._eval_node(v, scope) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, scope)
            right = self._eval_node(node.comparators[0], scope)
            kind = type(node.ops[0])
            if kind is ast.Eq:
                return left == right
            if kind is ast.NotEq:
                return left != right
            if kind is ast.Lt:
                return left < right
            if kind is ast.LtE:
                return left <= right
            if kind is ast.Gt:
                return left > right
            if kind is ast.GtE:
                return left >= right
            if kind is ast.In:
                return left in right
            if kind is ast.NotIn:
                return left not in right
            return False
        if isinstance(node, ast.IfExp):
            return self._eval_node(node.body if self._eval_node(node.test, scope) else node.orelse, scope)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name == "print":
                    return None
                if name == "range":
                    values = [self._eval_node(arg, scope) for arg in node.args]
                    return list(range(*(int(v) for v in values)))
                if name == "len":
                    return len(self._eval_node(node.args[0], scope))
                if name == "int":
                    return int(self._eval_node(node.args[0], scope))
                if name == "float":
                    return float(self._eval_node(node.args[0], scope))
                if name == "str":
                    return str(self._eval_node(node.args[0], scope))
                if name in self.functions:
                    item = self.functions[name]
                    args = [self._eval_node(arg, scope) for arg in node.args]
                    self.trace.function_calls += 1
                    frame: dict[str, Any] = {param["name"]: value for param, value in zip(item["params"], args)}
                    self.trace.scopes.append(frame)
                    self.trace.call_stack.append(name)
                    self.trace.add_step(node.lineno if hasattr(node, "lineno") else self.current_line,
                                        "call", f"Call {name}()", f"Enters `{name}` with {len(args)} argument(s).",
                                        scope=name)
                    try:
                        self.exec_block(item["body"]["children"], frame, name)
                    except _ReturnSignal as result:
                        return result.value
                    finally:
                        self.trace.call_stack.pop()
                        self.trace.scopes.pop()
                    return None
            return None
        if isinstance(node, ast.Subscript):
            value = self._eval_node(node.value, scope)
            index = self._eval_node(node.slice, scope)
            try:
                return value[index]
            except Exception:
                return None
        return None


def _line_metrics(source: str, tree: ast.AST, functions: int, classes: int, assignments: int, counts: dict[str, int]) -> dict[str, int]:
    lines = source.split("\n")
    code = 0
    blank = 0
    comments = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank += 1
        elif stripped.startswith("#"):
            comments += 1
        else:
            code += 1
    return {
        "totalLines": len(lines), "codeLines": code, "blankLines": blank,
        "commentLines": comments, "characters": len(source),
        "functions": functions, "classes": classes,
        "loops": counts["loops"], "conditions": counts["conditions"],
        "returns": counts["returns"], "assignments": assignments,
        "maxDepth": counts["maxDepth"],
    }


def _make_guide(analysis: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    functions = analysis["functions"]
    metrics = analysis["metrics"]
    output = trace["output"].strip()
    output_display = f"{output} ⏎" if output else "No output"
    summary = f"This Python program "
    if functions:
        summary += f"defines {len(functions)} helper{'s' if len(functions) != 1 else ''}, "
    if metrics["loops"]:
        summary += f"uses {metrics['loops']} loop{'s' if metrics['loops'] != 1 else ''}, "
    summary += f"and produces `{output_display}` in the safe sample run."
    lines = analysis["lines"]
    walkthrough = []
    for fn in functions:
        walkthrough.append({
            "title": f"The reusable helper: {fn['name']}()",
            "body": f"Defines `{fn['name']}` with {len(fn['params'])} input(s). The body runs only when the helper is called.",
            "lines": [fn["startLine"]], "badge": "HELPER",
            "points": [f"Parameter `{param['name']}`" for param in fn["params"]],
        })
    setup = [a for a in analysis["assignments"] if a["line"] <= (analysis.get("entry") or {}).get("node", {}).get("startLine", 1) + 4][:3]
    if setup:
        walkthrough.append({
            "title": "The starting values are put in place",
            "body": "Named values are created before the main work begins.",
            "lines": [a["line"] for a in setup], "badge": "SETUP",
            "points": [f"`{a['target']}` becomes `{a['expressionText']}`" for a in setup],
        })
    walkthrough.append({
        "title": "The sample run",
        "body": "Prism follows the program locally without executing arbitrary code.",
        "lines": [trace["steps"][-2]["line"]] if len(trace["steps"]) > 1 else [1],
        "badge": "TRACE",
        "points": [f"{len(trace['steps'])} recorded steps", f"Output: `{output_display}`"],
    })
    line_notes = []
    for number, item in enumerate(lines, start=1):
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        stripped = text.strip()
        if not stripped:
            continue
        tone = "statement"
        if re.match(r"^(def |class )", stripped):
            tone = "function"
        elif re.match(r"^(if |elif |else\b|for |while )", stripped):
            tone = "decision"
        elif stripped.startswith("return"):
            tone = "return"
        elif stripped.startswith("print"):
            tone = "output"
        line_notes.append({
            "line": number, "endLine": number, "code": stripped,
            "note": f"Python executes this statement in sequence. Source text: `{stripped}`.",
            "tone": tone, "synthetic": False,
        })
    concepts = []
    if functions:
        concepts.append({"term": "Function", "definition": "A reusable block of instructions with a name.", "inThisCode": f"`{functions[0]['name']}` packages reusable logic.", "line": functions[0]["startLine"]})
    if metrics["loops"]:
        concepts.append({"term": "Loop", "definition": "A loop repeats a block for each value or while a condition holds.", "inThisCode": "The sample trace shows each pass and the changed values.", "line": next((n["startLine"] for n in analysis["root"]["body"]["children"] if n["type"] == "for"), 1)})
    concepts.append({"term": "Assignment", "definition": "Assignment stores a value under a name so later lines can reuse it.", "inThisCode": "The setup and accumulator updates create the program state.", "line": analysis["assignments"][0]["line"] if analysis["assignments"] else 1})
    concepts.append({"term": "Print output", "definition": "Print sends text to the program's output stream.", "inThisCode": f"The sample output is `{output_display}`.", "line": max(1, len(lines))})
    quiz = [
        {"question": "What exact text did this run print?", "answer": f"`{output_display}`"},
        {"question": "How many Python statements are in the program?", "answer": f"{len(line_notes)} statements, spread over {analysis['lineCount']} source lines."},
    ]
    if metrics["loops"]:
        quiz.append({"question": "How many times did the loop run in the sample?", "answer": f"{trace['iterations']} passes were recorded."})
    return {
        "version": 1, "author": "local", "headline": "How this Python program works",
        "sourceLineCount": analysis["lineCount"], "summary": summary,
        "overview": {
            "paragraphs": [
                f"It runs from the top of the file to the bottom. The sample run produces `{output_display}`.",
                "The key idea is to follow named values and control flow in order, then connect those values to the output.",
                "Use **Line by line** for the close reading and the trace tab for the recorded values.",
            ],
            "mentalModel": {
                "title": "A short sequence of named steps",
                "body": "Imagine a notebook: each assignment writes a value into a named slot, branches choose which lines to read, and loops repeat a page. The output is the final note left on the page.",
            },
            "glance": [
                {"label": "Language", "value": "Python", "hint": "Readable by design"},
                {"label": "Entry point", "value": "Top-level code", "hint": "Runs from the first line"},
                {"label": "Shape", "value": f"{metrics['functions']} function · {metrics['loops']} loop · {metrics['conditions']} decision", "hint": f"{analysis['lineCount']} lines in total"},
                {"label": "Sample output", "value": output_display, "hint": "From the Python safe run", "mono": True},
            ],
        },
        "walkthrough": walkthrough, "lineNotes": line_notes, "concepts": concepts,
        "watchOuts": [
            {"title": "Indentation is structure", "body": "In Python, indentation decides which lines belong to a block. Keep it consistent."},
            {"title": "Assignments replace or update values", "body": "A later assignment to the same name replaces the previous value unless the expression uses the old value, as an accumulator does."},
        ],
        "quiz": quiz,
        "traceNote": {"complete": trace["complete"], "output": trace["output"], "warnings": trace["warnings"], "stoppedReason": trace["stoppedReason"]},
        "readingMinutes": max(2, min(9, round(len(lines) / 2) + 1)),
        "wordCount": max(120, len(lines) * 55),
    }


def analyze_python(source: str) -> dict[str, Any]:
    text = str(source or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise ValueError(f"Python syntax error on line {error.lineno}: {error.msg}") from error
    factory = _NodeFactory(text)
    root = {
        "type": "program", "startLine": 1, "endLine": len(lines),
        "body": factory.block(tree.body), "header": "Program",
        "language": "Python", "parseMode": "indentation", "diagnostics": [],
    }
    root["id"] = factory.nid()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pass
    metrics = _line_metrics(text, tree, len(factory.functions), len(factory.classes),
                            len(factory.assignments), factory.counts)
    analysis = {
        "source": text, "language": LANGUAGE, "languageId": "python", "root": root,
        "diagnostics": [], "lineCount": len(lines), "lines": [
            {"number": index, "text": line} for index, line in enumerate(lines, start=1)
        ], "highlightedLines": [html.escape(line) if line else "" for line in lines],
        "functions": factory.functions, "classes": factory.classes,
        "assignments": factory.assignments, "actionNodes": factory.action_nodes,
        "metrics": metrics,
        "entry": {"kind": "program", "node": root, "name": "Program", "inferred": False},
        "flowFocus": {"kind": "program", "node": root, "name": "Program"},
        "parseDiagnostics": [], "confidence": "high",
        "projectTitle": "Python program",
        "featureSummary": f"Python · {metrics['loops']} loops · {metrics['functions']} functions",
    }
    trace = _PyRunner(root, text, analysis).run()
    guide = _make_guide(analysis, trace)
    return {"analysis": analysis, "trace": trace, "guide": guide}
