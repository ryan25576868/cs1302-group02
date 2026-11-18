"""Native Python analyst for JavaScript and TypeScript.

Uses tree-sitter grammars for parsing, then builds the same structural model
consumed by Prism's four native views. The trace is a deliberately bounded
evaluator for common beginner JavaScript, never an execution of the source.
"""

from __future__ import annotations

import ast
import html
from dataclasses import dataclass, field
from typing import Any

from tree_sitter import Language, Parser

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts

MAX_STEPS = 420
PARSERS = {
    "javascript": Language(tsjs.language()),
    "typescript": Language(tsts.language_typescript()),
    "tsx": Language(tsts.language_tsx()),
}

LANGUAGES = {
    "javascript": {"id": "javascript", "name": "JavaScript", "extension": "js"},
    "typescript": {"id": "typescript", "name": "TypeScript", "extension": "ts"},
}


def _parser(language: str) -> Parser:
    return Parser(PARSERS.get(language, PARSERS["javascript"]))


class _Factory:
    def __init__(self, source: str, language: str):
        self.source = source
        self.language = language
        self.bytes = source.encode("utf-8")
        self.lines = source.split("\n")
        self.parser = _parser(language)
        self.counter = 0
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.assignments: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.counts = {"loops": 0, "conditions": 0, "returns": 0, "maxDepth": 0}

    def nid(self) -> str:
        self.counter += 1
        return f"js-node-{self.counter}"

    def text(self, node) -> str:
        return self.bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def line(self, node) -> int:
        return node.start_point.row + 1

    def end_line(self, node) -> int:
        return node.end_point.row + 1

    def field(self, node, name: str):
        return node.child_by_field_name(name)

    def block(self, node, depth: int) -> dict[str, Any]:
        if node is None:
            return {"type": "block", "startLine": 1, "endLine": 1, "children": []}
        if node.type == "statement_block":
            children = [self.convert(child, depth + 1) for child in node.named_children]
            start = self.line(node)
        else:
            children = [self.convert(node, depth + 1)]
            start = self.line(node)
        end = self.end_line(node)
        return {"type": "block", "startLine": start, "endLine": end,
                "children": [child for child in children if child]}

    def action(self, node, subtype: str, **extra: Any) -> dict[str, Any]:
        raw = self.text(node).strip()
        action = {"subtype": subtype, "raw": raw, "line": self.line(node),
                  "expressionText": raw, **extra}
        return {"type": "action", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end_line(node), "header": raw, "text": raw,
                "action": action}

    def record(self, node: dict[str, Any], target: str, expression: str,
               dependencies: list[str], operator: str, declaration: bool) -> None:
        node["action"].update({
            "subtype": "declaration" if declaration else "assignment",
            "assignment": True, "targetDisplay": target, "targetName": target,
            "isDeclaration": declaration, "operator": operator,
            "expressionText": expression, "dependencies": dependencies,
        })
        record = {
            "id": f"assignment-{len(self.assignments) + 1}", "nodeId": node["id"],
            "line": node["startLine"], "endLine": node["endLine"], "target": target,
            "targetName": target, "expressionText": expression,
            "dependencies": dependencies, "operator": operator,
            "isDeclaration": declaration, "scope": "Global", "action": node["action"],
        }
        self.assignments.append(record)
        node["assignmentRecord"] = record

    def names_in(self, node) -> list[str]:
        found = []
        def walk(n):
            if n.type in {"identifier", "shorthand_property_identifier"}:
                name = self.text(n)
                if name not in found:
                    found.append(name)
            for child in n.named_children:
                walk(child)
        walk(node)
        return found

    def convert(self, node, depth: int = 0) -> dict[str, Any] | None:
        self.counts["maxDepth"] = max(self.counts["maxDepth"], depth)
        kind = node.type
        if kind in {"comment", "hash_bang_line"}:
            return None
        if kind in {"lexical_declaration", "variable_declaration"}:
            results = []
            declaration_kind = self.text(node).split(maxsplit=1)[0] if self.text(node) else "let"
            for declarator in [c for c in node.named_children if c.type == "variable_declarator"]:
                name_node = self.field(declarator, "name")
                value_node = self.field(declarator, "value")
                target = self.text(name_node) if name_node else "value"
                expression = self.text(value_node) if value_node else ""
                action = self.action(node, "declaration" if declaration_kind == "const" else "assignment",
                                     expressionText=expression)
                self.record(action, target, expression, self.names_in(value_node) if value_node else [], "=", True)
                self.actions.append(action)
                results.append(action)
            return results[0] if len(results) == 1 else {
                "type": "block", "startLine": self.line(node), "endLine": self.end_line(node),
                "children": results,
            }
        if kind == "function_declaration":
            name_node = self.field(node, "name")
            body = self.field(node, "body")
            params_node = self.field(node, "parameters")
            params = []
            if params_node:
                for param in params_node.named_children:
                    raw_param = self.text(param)
                    pattern = self.field(param, "pattern") or self.field(param, "name")
                    param_name = self.text(pattern) if pattern else raw_param.split(":", 1)[0].split("=", 1)[0].strip()
                    params.append({"name": param_name, "type": "", "defaultValue": None, "raw": raw_param})
            item = {
                "type": "function", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end_line(node),
                "header": self.text(node).split("{", 1)[0].strip(),
                "name": self.text(name_node) if name_node else "function",
                "params": params, "returnType": "", "body": self.block(body, depth),
                "keyword": "function", "scopeName": self.text(name_node) if name_node else "function",
            }
            item["actionCount"] = len([n for n in self._all(body) if n.type in {"lexical_declaration", "expression_statement", "return_statement"}]) if body else 0
            self.functions.append(item)
            return item
        if kind == "class_declaration":
            name_node = self.field(node, "name")
            body = self.field(node, "body")
            item = {
                "type": "class", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end_line(node), "header": f"class {self.text(name_node) if name_node else 'Class'}",
                "name": self.text(name_node) if name_node else "Class",
                "body": {"type": "block", "startLine": self.line(node), "endLine": self.end_line(node), "children": []},
                "keyword": "class",
            }
            self.classes.append(item)
            return item
        if kind == "if_statement":
            self.counts["conditions"] += 1
            condition = self.field(node, "condition")
            consequence = self.field(node, "consequence")
            alternative = self.field(node, "alternative")
            return {
                "type": "if", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end_line(node), "header": self.text(node).split("{", 1)[0].strip(),
                "condition": self.text(condition).strip("()") if condition else "condition",
                "consequent": self.block(consequence, depth),
                "alternate": self.block(alternative, depth) if alternative else None,
                "hasElse": alternative is not None, "keyword": "if",
            }
        if kind in {"for_statement", "for_in_statement"}:
            self.counts["loops"] += 1
            body = self.field(node, "body")
            return {
                "type": "for", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end_line(node), "header": self.text(node).split("{", 1)[0].strip(),
                "loopHeader": self.text(node).split("{", 1)[0].strip(),
                "body": self.block(body, depth), "keyword": "for",
                "loopMeta": {"style": "for"},
            }
        if kind == "while_statement":
            self.counts["loops"] += 1
            condition = self.field(node, "condition")
            body = self.field(node, "body")
            return {
                "type": "while", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end_line(node), "header": self.text(node).split("{", 1)[0].strip(),
                "condition": self.text(condition).strip("()") if condition else "true",
                "body": self.block(body, depth), "keyword": "while",
            }
        if kind == "return_statement":
            self.counts["returns"] += 1
            expression = self.text(node).removeprefix("return").rstrip(";").strip()
            return self.action(node, "return", expressionText=expression)
        if kind == "break_statement":
            return self.action(node, "break")
        if kind == "continue_statement":
            return self.action(node, "continue")
        if kind == "expression_statement":
            expression = node.named_children[0] if node.named_children else None
            if expression is None:
                return None
            if expression.type in {"assignment_expression", "augmented_assignment_expression"}:
                left = self.field(expression, "left")
                right = self.field(expression, "right")
                target = self.text(left) if left else "value"
                value = self.text(right) if right else ""
                operator = self.text(expression).split(target, 1)[1].split(value, 1)[0].strip() if right else "="
                operator = operator or "="
                action = self.action(node, "assignment", expressionText=value, operator=operator)
                self.record(action, target, value, self.names_in(right) if right else [], operator, False)
                self.actions.append(action)
                return action
            if expression.type == "call_expression":
                function = self.field(expression, "function")
                function_name = self.text(function) if function else ""
                if function_name == "console.log":
                    action = self.action(node, "print", printKind="console",
                                         expressionText=self.text(expression))
                    self.actions.append(action)
                    return action
                action = self.action(node, "call", expressionText=self.text(expression), calleeName=function_name)
                self.actions.append(action)
                return action
            if expression.type == "update_expression":
                action = self.action(node, "update", expressionText=self.text(expression))
                self.actions.append(action)
                return action
            return self.action(node, "expression", expressionText=self.text(expression))
        # Unknown statement: retain it as an action so nothing silently disappears.
        raw = self.text(node).strip()
        if not raw:
            return None
        return self.action(node, "expression", expressionText=raw)

    def _all(self, node):
        yield node
        for child in node.named_children:
            yield from self._all(child)


def _metrics(source: str, factory: _Factory) -> dict[str, int]:
    lines = source.split("\n")
    code = sum(1 for line in lines if line.strip() and not line.strip().startswith("//"))
    comments = sum(1 for line in lines if line.strip().startswith("//"))
    blank = sum(1 for line in lines if not line.strip())
    return {
        "totalLines": len(lines), "codeLines": code, "blankLines": blank,
        "commentLines": comments, "characters": len(source),
        "functions": len(factory.functions), "classes": len(factory.classes),
        "loops": factory.counts["loops"], "conditions": factory.counts["conditions"],
        "returns": factory.counts["returns"], "assignments": len(factory.assignments),
        "maxDepth": factory.counts["maxDepth"],
    }


@dataclass
class _Trace:
    steps: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""
    warnings: list[str] = field(default_factory=list)
    complete: bool = False
    stopped_reason: str | None = None
    function_calls: int = 0
    iterations: int = 0
    globals: dict[str, Any] = field(default_factory=dict)
    scopes: list[dict[str, Any]] = field(default_factory=list)

    def display(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, list):
            return "[" + ", ".join(self.display(v) for v in value) + "]"
        if isinstance(value, dict):
            return "{" + ", ".join(f"{k}: {self.display(v)}" for k, v in value.items()) + "}"
        return str(value)

    def snapshot(self) -> list[dict[str, Any]]:
        result = []
        seen = set()
        for scope in reversed(self.scopes + [self.globals]):
            for name, value in scope.items():
                if name in seen:
                    continue
                seen.add(name)
                result.append({"name": name, "display": self.display(value),
                               "type": "array" if isinstance(value, list) else "number" if isinstance(value, (int, float)) else "string"})
        return result[:20]

    def add(self, line: int, kind: str, title: str, detail: str, code: str = "", extra=None) -> None:
        if len(self.steps) >= MAX_STEPS:
            self.warnings.append(f"The trace reached its {MAX_STEPS}-step limit.")
            raise StopIteration
        self.steps.append({
            "index": len(self.steps), "line": line, "endLine": line, "kind": kind,
            "title": title, "detail": detail, "vars": self.snapshot(), "output": self.output,
            "outputDelta": "", "callStack": [], "scope": "Global", "code": code, "extra": extra,
        })

    def event(self, kind: str, line: int, **data: Any) -> None:
        self.events.append({
            "kind": kind, "line": line, "target": data.get("target"),
            "name": data.get("target"), "expressionText": data.get("expressionText"),
            "operator": data.get("operator"), "value": self.display(data.get("value")),
            "valueType": "array" if isinstance(data.get("value"), list) else "number",
            "scope": "Global", "dependencies": data.get("dependencies", []),
            "stepIndex": len(self.steps) - 1 if self.steps else 0, "index": len(self.events),
        })


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Runner:
    def __init__(self, analysis: dict[str, Any], source: str):
        self.analysis = analysis
        self.source = source
        self.lines = source.split("\n")
        self.parser = _parser(analysis["languageId"])
        self.trace = _Trace()
        self.functions = {item["name"]: item for item in analysis["functions"]}
        self.trace.scopes = []

    def run(self) -> dict[str, Any]:
        self.trace.add(1, "start", "Program starts", "Prism follows the program locally; the source is not executed.")
        try:
            self.exec_block(self.analysis["root"]["body"]["children"], self.trace.globals)
            self.trace.complete = True
            self.trace.add(max(1, len(self.lines)), "end", "Program ends", "The simulated run finished.")
        except StopIteration:
            self.trace.stopped_reason = "step_limit"
        except _Return:
            self.trace.complete = True
        except Exception as error:  # pragma: no cover - defensive
            self.trace.warnings.append(f"The trace stopped at line {getattr(error, 'line', '?')}: {error}")
            self.trace.stopped_reason = "error"
        return {
            "steps": self.trace.steps, "events": self.trace.events, "output": self.trace.output,
            "warnings": self.trace.warnings, "complete": self.trace.complete,
            "stoppedReason": self.trace.stopped_reason, "entryName": "Program",
            "functionCalls": self.trace.function_calls, "iterations": self.trace.iterations,
            "finalVars": self.trace.snapshot(), "callStackSupported": False,
            "interpreter": "js-tree-sitter-safe",
        }

    def exec_block(self, nodes, scope) -> None:
        for node in nodes:
            self.exec_node(node, scope)

    def exec_node(self, node, scope) -> None:
        kind = node.get("type")
        if kind == "function":
            scope[node["name"]] = ("function", node)
            return
        if kind == "class":
            return
        if kind == "if":
            value = self.eval(node.get("condition", "false"), scope)
            self.trace.add(node["startLine"], "condition", f"Check {node.get('condition')}",
                           f"The condition is `{self.trace.display(value)}`.", node.get("header", ""))
            branch = node.get("consequent") if value else node.get("alternate")
            if branch:
                self.exec_block(branch.get("children", []), scope)
            return
        if kind == "for":
            header = node.get("loopHeader", "")
            match = __import__("re").search(r"for\s*\(\s*(?:const|let|var)?\s*(\w+)\s+of\s+(.+?)\)", header)
            if match:
                target, iterable_text = match.group(1), match.group(2).strip()
                iterable = self.eval(iterable_text, scope)
                if not isinstance(iterable, list):
                    self.trace.warnings.append(f"The loop on line {node['startLine']} could not be iterated safely.")
                    return
                for value in iterable:
                    self.trace.iterations += 1
                    scope[target] = value
                    self.trace.event("loop-target", node["startLine"], target=target, value=value)
                    self.trace.add(node["startLine"], "iteration", f"Loop pass {self.trace.iterations}",
                                   f"`{target}` receives `{self.trace.display(value)}`.", header)
                    try:
                        self.exec_block(node.get("body", {}).get("children", []), scope)
                    except _Continue:
                        continue
                    except _Break:
                        break
            return
        if kind == "while":
            guard = 0
            while self.eval(node.get("condition", "false"), scope) and guard < 60:
                guard += 1
                self.trace.iterations += 1
                self.trace.add(node["startLine"], "iteration", f"Loop pass {self.trace.iterations}",
                               "The condition is still true.", node.get("header", ""))
                try:
                    self.exec_block(node.get("body", {}).get("children", []), scope)
                except _Continue:
                    continue
                except _Break:
                    break
            return
        if kind == "action":
            self.exec_action(node, scope)

    def exec_action(self, node, scope) -> None:
        action = node.get("action") or {}
        subtype = action.get("subtype")
        if subtype == "return":
            value = self.eval(action.get("expressionText", ""), scope)
            self.trace.add(node["startLine"], "return", "Return a value",
                           f"Returns `{self.trace.display(value)}`.", node.get("text", ""))
            raise _Return(value)
        if subtype == "break":
            raise _Break
        if subtype == "continue":
            raise _Continue
        if subtype in {"declaration", "assignment"}:
            target = action.get("targetDisplay") or action.get("targetName")
            expression = action.get("expressionText", "")
            operator = action.get("operator", "=")
            if operator != "=" and operator in {"+=", "-=", "*=", "/="}:
                right = self.eval(expression, scope)
                old = scope.get(str(target), 0)
                value = old + right if operator == "+=" else old - right if operator == "-=" else old * right if operator == "*=" else old / right
            else:
                value = self.eval(expression, scope)
            scope[str(target)] = value
            self.trace.event("assignment", node["startLine"], target=target, expressionText=expression,
                             operator=operator, value=value, dependencies=action.get("dependencies", []))
            self.trace.add(node["startLine"], "assign", f"Set {target}",
                           f"`{target}` becomes `{self.trace.display(value)}`.", node.get("text", ""))
            return
        if subtype == "print":
            call = self._parse_expr(action.get("expressionText", ""))
            args = []
            if call and call.type == "call_expression":
                args_node = call.child_by_field_name("arguments")
                if args_node:
                    args = [self.eval(self.bytes_text(arg), scope) for arg in args_node.named_children]
            text = " ".join(self.trace.display(value) for value in args)
            self.trace.output += text + "\n"
            self.trace.event("print", node["startLine"], value=text)
            self.trace.add(node["startLine"], "print", "Print output", f"Output: `{text}`.",
                           node.get("text", ""))
            return
        if subtype == "call":
            expression = action.get("expressionText", "")
            self.eval(expression, scope)

    def _parse_expr(self, text: str):
        tree = self.parser.parse(text.encode("utf-8"))
        node = tree.root_node
        while node.type in {"program", "expression_statement"} and node.named_children:
            node = node.named_children[0]
        return node

    def bytes_text(self, node) -> str:
        return node.text.decode("utf-8", "replace")

    def eval(self, text: str, scope) -> Any:
        if not text:
            return None
        node = self._parse_expr(text)
        return self.eval_node(node, scope) if node else None

    def eval_node(self, node, scope) -> Any:
        if node is None:
            return None
        kind = node.type
        if kind in {"program", "expression_statement"}:
            return self.eval_node(node.named_children[0], scope) if node.named_children else None
        if kind == "number":
            value = self.bytes_text(node)
            return float(value) if "." in value else int(value)
        if kind in {"string", "template_string"}:
            return self.bytes_text(node).strip("'\"`")
        if kind in {"true", "false"}:
            return kind == "true"
        if kind == "null":
            return None
        if kind == "identifier":
            name = self.bytes_text(node)
            value = scope.get(name)
            if isinstance(value, tuple) and value and value[0] == "function":
                return value[1]
            return value if value is not None else 0
        if kind == "array":
            return [self.eval_node(child, scope) for child in node.named_children]
        if kind == "parenthesized_expression":
            return self.eval_node(node.named_children[0], scope) if node.named_children else None
        if kind == "binary_expression":
            left_node = node.child_by_field_name("left")
            right_node = node.child_by_field_name("right")
            left = self.eval_node(left_node, scope)
            right = self.eval_node(right_node, scope)
            op = self.bytes_text(node.child_by_field_name("operator")) if node.child_by_field_name("operator") else ""
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                return left / right
            if op == "%":
                return left % right
            if op == ">":
                return left > right
            if op == "<":
                return left < right
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
            if op in {"==", "==="}:
                return left == right
            if op in {"!=", "!=="}:
                return left != right
            if op == "&&":
                return bool(left) and bool(right)
            if op == "||":
                return bool(left) or bool(right)
            return None
        if kind == "unary_expression":
            operator = node.child_by_field_name("operator")
            operand = node.child_by_field_name("argument")
            value = self.eval_node(operand, scope)
            if operator and self.bytes_text(operator) == "!":
                return not bool(value)
            if operator and self.bytes_text(operator) == "-":
                return -value
            return value
        if kind == "ternary_expression":
            condition = node.child_by_field_name("condition")
            return self.eval_node(node.child_by_field_name("consequence") if self.eval_node(condition, scope) else node.child_by_field_name("alternative"), scope)
        if kind in {"call_expression", "member_expression"}:
            # Only user functions and console.log need evaluation for the trace.
            if kind == "call_expression":
                function = node.child_by_field_name("function")
                function_name = self.bytes_text(function) if function else ""
                args_node = node.child_by_field_name("arguments")
                args = [self.eval_node(arg, scope) for arg in args_node.named_children] if args_node else []
                if function_name in self.functions:
                    item = self.functions[function_name]
                    self.trace.function_calls += 1
                    local = {param["name"]: value for param, value in zip(item["params"], args)}
                    self.trace.scopes.append(local)
                    self.trace.add(item["startLine"], "call", f"Call {function_name}()",
                                   "Enters the helper.")
                    try:
                        self.exec_block(item["body"]["children"], local)
                    except _Return as result:
                        return result.value
                    finally:
                        self.trace.scopes.pop()
                return None
            return None
        if kind == "subscript_expression":
            value = self.eval_node(node.child_by_field_name("object"), scope)
            index = self.eval_node(node.child_by_field_name("index"), scope)
            try:
                return value[index]
            except Exception:
                return None
        return None


def _guide(analysis: dict[str, Any], trace: dict[str, Any], language_name: str) -> dict[str, Any]:
    metrics = analysis["metrics"]
    output = trace["output"].strip()
    display = f"{output} ⏎" if output else "No output"
    line_count = analysis["lineCount"]
    lines = [line for line in analysis["source"].split("\n")]
    notes = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        tone = "statement"
        if stripped.startswith(("//", "/*", "*")):
            tone = "comment"
        elif stripped.startswith(("if ", "if(", "for ", "for(", "while ", "while(")):
            tone = "decision"
        elif stripped.startswith("return"):
            tone = "return"
        elif "console.log" in stripped:
            tone = "output"
        notes.append({"line": index, "endLine": index, "code": stripped,
                      "note": "Executed in sequence as part of the program.", "tone": tone,
                      "synthetic": False})
    concepts = [
        {"term": "Variable", "definition": "A named slot that stores a value.", "inThisCode": "Assignments create and update the running state.", "line": 1},
        {"term": "Control flow", "definition": "Conditions and loops decide which statements run.", "inThisCode": f"There are {metrics['conditions']} decisions and {metrics['loops']} loops.", "line": 1},
        {"term": "Output", "definition": "console.log writes values to the program output.", "inThisCode": f"The sample output is `{display}`.", "line": max(1, line_count)},
    ]
    walkthrough = [{
        "title": "Read from top to bottom",
        "body": "Start with the values created near the top, then follow conditions, loops and calls.",
        "lines": [1], "badge": "FLOW", "points": [
            f"{metrics['assignments']} assignments",
            f"{trace['iterations']} loop passes",
            f"Output: `{display}`",
        ],
    }]
    for fn in analysis["functions"][:3]:
        walkthrough.append({
            "title": f"Helper: {fn['name']}()", "body": "A function groups reusable statements.",
            "lines": [fn["startLine"]], "badge": "HELPER",
            "points": [f"{len(fn['params'])} parameter(s)"],
        })
    return {
        "version": 1, "author": "local", "headline": f"How this {language_name} program works",
        "sourceLineCount": line_count,
        "summary": f"This {language_name} program has {metrics['assignments']} assignments, {metrics['loops']} loop(s), and produces `{display}` in the safe sample run.",
        "overview": {
            "paragraphs": [
                f"The program runs from top to bottom. The sample run produces `{display}`.",
                "Follow the named values first, then trace the conditions and repeated blocks.",
            ],
            "mentalModel": {"title": "A sequence of named values", "body": "Each assignment writes a value into a name. Conditions choose a path; loops repeat a block."},
            "glance": [
                {"label": "Language", "value": language_name, "hint": "Parsed locally"},
                {"label": "Shape", "value": f"{metrics['functions']} function · {metrics['loops']} loop · {metrics['conditions']} decision", "hint": f"{line_count} lines"},
                {"label": "Output", "value": display, "hint": "Safe sample run", "mono": True},
            ],
        },
        "walkthrough": walkthrough, "lineNotes": notes, "concepts": concepts,
        "watchOuts": [{"title": "Equality matters", "body": "Use === when you mean exact equality; avoid relying on loose coercion in beginner code."}],
        "quiz": [
            {"question": "What did the sample run print?", "answer": f"`{display}`"},
            {"question": "How many loop passes were recorded?", "answer": str(trace["iterations"])},
        ],
        "traceNote": {"complete": trace["complete"], "output": trace["output"], "warnings": trace["warnings"], "stoppedReason": trace["stoppedReason"]},
        "readingMinutes": max(2, min(8, line_count // 2 + 1)), "wordCount": max(120, line_count * 40),
    }


def analyze_javascript(source: str, language: str = "javascript") -> dict[str, Any]:
    text = str(source or "").replace("\r\n", "\n").replace("\r", "\n")
    parser = _parser(language)
    tree = parser.parse(text.encode("utf-8"))
    if tree.root_node.has_error:
        # Tree-sitter can still produce a useful partial tree; expose a warning rather than failing.
        diagnostics = [{"severity": "warning", "message": "Some JavaScript could not be parsed completely.", "line": 1}]
    else:
        diagnostics = []
    factory = _Factory(text, language)
    children = [factory.convert(child) for child in tree.root_node.named_children]
    body_children = []
    for child in children:
        if isinstance(child, list):
            body_children.extend(child)
        elif child:
            body_children.append(child)
    root = {
        "type": "program", "id": factory.nid(), "startLine": 1,
        "endLine": len(text.split("\n")), "header": "Program",
        "body": {"type": "block", "startLine": 1, "endLine": len(text.split("\n")),
                 "children": body_children},
        "language": LANGUAGES.get(language, LANGUAGES["javascript"])["name"],
        "parseMode": "braces", "diagnostics": diagnostics,
    }
    metrics = _metrics(text, factory)
    language_info = LANGUAGES.get(language, LANGUAGES["javascript"])
    analysis = {
        "source": text, "language": language_info, "languageId": language,
        "root": root, "diagnostics": diagnostics, "lineCount": len(text.split("\n")),
        "lines": [{"number": i, "text": line} for i, line in enumerate(text.split("\n"), 1)],
        "highlightedLines": [html.escape(line) for line in text.split("\n")],
        "functions": factory.functions, "classes": factory.classes,
        "assignments": factory.assignments, "actionNodes": factory.actions,
        "metrics": metrics,
        "entry": {"kind": "program", "node": root, "name": "Program", "inferred": False},
        "flowFocus": {"kind": "program", "node": root, "name": "Program"},
        "parseDiagnostics": diagnostics, "confidence": "medium" if diagnostics else "high",
        "projectTitle": f"{language_info['name']} program",
        "featureSummary": f"{language_info['name']} · {metrics['loops']} loops · {metrics['functions']} functions",
    }
    trace = _Runner(analysis, text).run()
    guide = _guide(analysis, trace, language_info["name"])
    return {"analysis": analysis, "trace": trace, "guide": guide}
