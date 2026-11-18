"""Python-native analysis for Java, C++ and C.

This is a practical beginner subset: declarations, assignments, conditions,
loops, functions/methods, returns and common print calls. Parsing uses
tree-sitter; the trace is a bounded evaluator and never executes source code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tree_sitter import Language, Parser

import tree_sitter_java as tsjava
import tree_sitter_cpp as tscpp
import tree_sitter_c as tsc

from python_app.js_analysis import _guide

LANGUAGES = {
    "java": {"id": "java", "name": "Java", "extension": "java"},
    "cpp": {"id": "cpp", "name": "C++", "extension": "cpp"},
    "c": {"id": "c", "name": "C", "extension": "c"},
}
PARSERS = {
    "java": Language(tsjava.language()),
    "cpp": Language(tscpp.language()),
    "c": Language(tsc.language()),
}


def parser(language: str) -> Parser:
    return Parser(PARSERS.get(language, PARSERS["c"]))


class Factory:
    def __init__(self, source: str, language: str):
        self.source = source
        self.language = language
        self.bytes = source.encode("utf-8")
        self.lines = source.split("\n")
        self.parser = parser(language)
        self.counter = 0
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.assignments: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.counts = {"loops": 0, "conditions": 0, "returns": 0, "maxDepth": 0}

    def nid(self) -> str:
        self.counter += 1
        return f"cf-node-{self.counter}"

    def text(self, node) -> str:
        return self.bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def line(self, node) -> int:
        return node.start_point.row + 1

    def end(self, node) -> int:
        return node.end_point.row + 1

    def field(self, node, name: str):
        return node.child_by_field_name(name) if node else None

    def block(self, node, depth: int) -> dict[str, Any]:
        if node is None:
            return {"type": "block", "startLine": 1, "endLine": 1, "children": []}
        target = node
        if node.type in {"block", "compound_statement", "class_body", "program", "translation_unit"}:
            children = [self.convert(child, depth + 1) for child in node.named_children]
        else:
            children = [self.convert(node, depth + 1)]
        flat = []
        for child in children:
            if isinstance(child, list):
                flat.extend(child)
            elif child:
                flat.append(child)
        return {"type": "block", "startLine": self.line(target), "endLine": self.end(target),
                "children": flat}

    def action(self, node, subtype: str, **extra) -> dict[str, Any]:
        raw = self.text(node).strip()
        return {
            "type": "action", "id": self.nid(), "startLine": self.line(node),
            "endLine": self.end(node), "header": raw, "text": raw,
            "action": {"subtype": subtype, "raw": raw, "line": self.line(node),
                       "expressionText": raw, **extra},
        }

    def record(self, node, target: str, expression: str, dependencies: list[str],
               operator: str, declaration: bool) -> None:
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

    def names(self, node) -> list[str]:
        result = []
        def walk(n):
            if n.type in {"identifier", "field_identifier"}:
                value = self.text(n)
                if value not in result:
                    result.append(value)
            for child in n.named_children:
                walk(child)
        if node:
            walk(node)
        return result

    def params(self, node) -> list[dict[str, Any]]:
        result = []
        for child in node.named_children if node else []:
            if child.type in {"formal_parameter", "parameter_declaration"}:
                text = self.text(child)
                name = text.split("=")[0].strip().split()[-1].strip("[]") if text else ""
                result.append({"name": name, "type": "", "defaultValue": None, "raw": text})
        return result

    def convert(self, node, depth: int = 0):
        self.counts["maxDepth"] = max(self.counts["maxDepth"], depth)
        kind = node.type
        if kind in {"comment", "line_comment", "block_comment", "preproc_include", "using_declaration",
                    "import_declaration", "package_declaration"}:
            return None
        if kind == "class_declaration":
            name = self.field(node, "name")
            body = self.field(node, "body")
            item = {
                "type": "class", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end(node), "header": f"class {self.text(name) if name else 'Class'}",
                "name": self.text(name) if name else "Class",
                "body": self.block(body, depth), "keyword": "class",
            }
            self.classes.append(item)
            return item
        if kind in {"method_declaration", "constructor_declaration", "function_definition"}:
            return self.convert_function(node, depth)
        if kind in {"local_variable_declaration", "declaration"}:
            return self.convert_declaration(node, depth)
        if kind == "if_statement":
            self.counts["conditions"] += 1
            condition = self.field(node, "condition")
            consequence = self.field(node, "consequence")
            alternative = self.field(node, "alternative")
            return {
                "type": "if", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end(node), "header": self.text(node).split("{", 1)[0].strip(),
                "condition": self.text(condition).strip("()") if condition else "condition",
                "consequent": self.block(consequence, depth),
                "alternate": self.block(alternative, depth) if alternative else None,
                "hasElse": alternative is not None, "keyword": "if",
            }
        if kind in {"for_statement", "enhanced_for_statement", "for_range_loop"}:
            self.counts["loops"] += 1
            body = self.field(node, "body")
            header = self.text(node).split("{", 1)[0].strip()
            return {
                "type": "for", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end(node), "header": header, "loopHeader": header,
                "body": self.block(body, depth), "keyword": "for",
                "loopMeta": {"style": kind},
            }
        if kind == "while_statement":
            self.counts["loops"] += 1
            condition = self.field(node, "condition")
            body = self.field(node, "body")
            return {
                "type": "while", "id": self.nid(), "startLine": self.line(node),
                "endLine": self.end(node), "header": self.text(node).split("{", 1)[0].strip(),
                "condition": self.text(condition).strip("()") if condition else "true",
                "body": self.block(body, depth), "keyword": "while",
            }
        if kind == "return_statement":
            self.counts["returns"] += 1
            text = self.text(node).replace("return", "", 1).rstrip(";").strip()
            return self.action(node, "return", expressionText=text)
        if kind in {"break_statement", "continue_statement"}:
            return self.action(node, "break" if "break" in kind else "continue")
        if kind == "expression_statement":
            expr = node.named_children[0] if node.named_children else None
            if expr is None:
                return None
            return self.convert_expression(node, expr)
        return self.action(node, "expression", expressionText=self.text(node))

    def convert_function(self, node, depth: int):
        if node.type == "function_definition":
            declarator = self.field(node, "declarator")
            name_node = self._first(declarator, "identifier") if declarator else None
            params_node = self._first(declarator, "parameter_list") if declarator else None
            body = self.field(node, "body")
            name = self.text(name_node) if name_node else "function"
        else:
            name_node = self.field(node, "name")
            params_node = self.field(node, "parameters")
            body = self.field(node, "body")
            name = self.text(name_node) if name_node else "method"
        item = {
            "type": "function", "id": self.nid(), "startLine": self.line(node),
            "endLine": self.end(node), "header": self.text(node).split("{", 1)[0].strip(),
            "name": name, "params": self.params(params_node), "returnType": "",
            "body": self.block(body, depth), "keyword": "function", "scopeName": name,
        }
        item["actionCount"] = len(item["body"]["children"])
        self.functions.append(item)
        return item

    def _first(self, node, type_name: str):
        if node is None:
            return None
        if node.type == type_name:
            return node
        for child in node.named_children:
            found = self._first(child, type_name)
            if found:
                return found
        return None

    def convert_declaration(self, node, depth: int):
        results = []
        declarators = [child for child in node.named_children if child.type in {"variable_declarator", "init_declarator"}]
        for child in declarators:
            name_node = self.field(child, "name") or self.field(child, "declarator")
            value_node = self.field(child, "value")
            if name_node is None:
                name_node = self._first(child, "identifier")
            if name_node is None:
                continue
            target = self.text(name_node).replace("[]", "").strip()
            expression = self.text(value_node) if value_node else ""
            declaration = True
            action = self.action(node, "declaration", expressionText=expression)
            self.record(action, target, expression, self.names(value_node), "=", declaration)
            self.actions.append(action)
            results.append(action)
        if not results:
            return self.action(node, "expression", expressionText=self.text(node))
        return results[0] if len(results) == 1 else {
            "type": "block", "startLine": self.line(node), "endLine": self.end(node), "children": results,
        }

    def convert_expression(self, node, expr):
        raw = self.text(expr)
        if expr.type in {"assignment_expression", "augmented_assignment_expression"}:
            left = self.field(expr, "left")
            right = self.field(expr, "right")
            target = self.text(left) if left else "value"
            value = self.text(right) if right else ""
            operator = self.text(expr)[len(target):].rsplit(value, 1)[0].strip() if target and value else "="
            action = self.action(node, "assignment", expressionText=value, operator=operator or "=")
            self.record(action, target, value, self.names(right), operator or "=", False)
            self.actions.append(action)
            return action
        if expr.type == "update_expression":
            action = self.action(node, "update", expressionText=raw)
            self.actions.append(action)
            return action
        if self._is_print(expr):
            action = self.action(node, "print", printKind=self.language, expressionText=raw)
            self.actions.append(action)
            return action
        if expr.type in {"method_invocation", "call_expression"}:
            action = self.action(node, "call", expressionText=raw)
            self.actions.append(action)
            return action
        return self.action(node, "expression", expressionText=raw)

    def _is_print(self, expr) -> bool:
        text = self.text(expr)
        if "System.out.print" in text:
            return True
        if re.match(r"^(?:std::)?cout\s*<<", text):
            return True
        return expr.type == "call_expression" and re.match(r"printf\s*\(", text) is not None


@dataclass
class Trace:
    steps: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""
    warnings: list[str] = field(default_factory=list)
    complete: bool = False
    stopped: str | None = None
    calls: int = 0
    iterations: int = 0
    scopes: list[dict[str, Any]] = field(default_factory=list)
    global_scope: dict[str, Any] = field(default_factory=dict)

    def display(self, value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, list):
            return "{" + ", ".join(self.display(v) for v in value) + "}"
        if isinstance(value, str):
            return value
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def snapshot(self):
        seen = set()
        result = []
        for scope in reversed(self.scopes + [self.global_scope]):
            for name, value in scope.items():
                if name in seen:
                    continue
                seen.add(name)
                result.append({"name": name, "display": self.display(value), "type": "array" if isinstance(value, list) else "number" if isinstance(value, (int, float)) else "string"})
        return result[:20]

    def add(self, line, kind, title, detail, code="", extra=None):
        if len(self.steps) >= 420:
            self.warnings.append("The trace reached its 420-step limit.")
            raise StopIteration
        self.steps.append({"index": len(self.steps), "line": line, "endLine": line, "kind": kind,
                           "title": title, "detail": detail, "vars": self.snapshot(),
                           "output": self.output, "outputDelta": "", "callStack": [],
                           "scope": "Global", "code": code, "extra": extra})

    def event(self, kind, line, **data):
        self.events.append({"kind": kind, "line": line, "target": data.get("target"),
                            "name": data.get("target"), "expressionText": data.get("expressionText"),
                            "operator": data.get("operator"), "value": self.display(data.get("value")),
                            "valueType": "number", "scope": "Global",
                            "dependencies": data.get("dependencies", []),
                            "stepIndex": len(self.steps) - 1 if self.steps else 0,
                            "index": len(self.events)})


class Return(Exception):
    def __init__(self, value):
        self.value = value


class Break(Exception):
    pass


class Continue(Exception):
    pass


class Runner:
    def __init__(self, analysis: dict[str, Any], source: str):
        self.analysis = analysis
        self.source = source
        self.bytes = source.encode("utf-8")
        self.active_bytes = self.bytes
        self.parser = parser(analysis["languageId"])
        self.trace = Trace()
        self.functions = {fn["name"]: fn for fn in analysis["functions"]}

    def text(self, node):
        data = self.active_bytes or self.bytes
        return data[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def field(self, node, name: str):
        return node.child_by_field_name(name) if node else None

    def run(self):
        self.trace.add(1, "start", "Program starts", "The source is parsed and simulated locally.")
        target = self.analysis.get("entry", {}).get("node") if self.analysis.get("entry", {}).get("kind") == "function" else self.analysis["root"]
        try:
            if target and target.get("type") == "function":
                self.call_function(target, [], self.trace.global_scope)
            else:
                self.exec_block(self.analysis["root"]["body"]["children"], self.trace.global_scope)
            self.trace.complete = True
            self.trace.add(max(1, len(self.source.split("\n"))), "end", "Program ends", "The simulated run finished.")
        except StopIteration:
            self.trace.stopped = "step_limit"
        except Return:
            self.trace.complete = True
        except Exception as error:  # pragma: no cover
            self.trace.warnings.append(f"The trace stopped: {error}")
            self.trace.stopped = "error"
        return {"steps": self.trace.steps, "events": self.trace.events, "output": self.trace.output,
                "warnings": self.trace.warnings, "complete": self.trace.complete,
                "stoppedReason": self.trace.stopped, "entryName": self.analysis.get("entry", {}).get("name", "Program"),
                "functionCalls": self.trace.calls, "iterations": self.trace.iterations,
                "finalVars": self.trace.snapshot(), "callStackSupported": False,
                "interpreter": "compiled-safe-ast"}

    def exec_block(self, nodes, scope):
        for node in nodes:
            self.exec_node(node, scope)

    def exec_node(self, node, scope):
        kind = node.get("type")
        if kind == "function":
            scope[node["name"]] = ("function", node)
            return
        if kind == "class":
            return
        if kind == "if":
            value = self.eval(node.get("condition", "false"), scope)
            self.trace.add(node["startLine"], "condition", f"Check {node.get('condition')}",
                           f"The condition is {self.trace.display(value)}.", node.get("header", ""))
            branch = node.get("consequent") if value else node.get("alternate")
            if branch:
                self.exec_block(branch.get("children", []), scope)
            return
        if kind == "for":
            self.exec_loop(node, scope)
            return
        if kind == "while":
            guard = 0
            while self.eval(node.get("condition", "false"), scope) and guard < 50:
                guard += 1
                self.trace.iterations += 1
                self.trace.add(node["startLine"], "iteration", f"Loop pass {self.trace.iterations}",
                               "The condition is still true.", node.get("header", ""))
                try:
                    self.exec_block(node.get("body", {}).get("children", []), scope)
                except Continue:
                    continue
                except Break:
                    break
            return
        if kind == "action":
            self.exec_action(node, scope)

    def exec_loop(self, node, scope):
        header = node.get("loopHeader", "")
        match = re.search(r"for\s*\(\s*(?:[A-Za-z_]\w*(?:\[\])?\s+)?([A-Za-z_]\w*)\s*:\s*([^)]+)\)", header)
        if match:
            target, iterable_text = match.group(1), match.group(2).strip()
            iterable = self.eval(iterable_text, scope)
            if isinstance(iterable, list):
                for value in iterable:
                    self.trace.iterations += 1
                    scope[target] = value
                    self.trace.add(node["startLine"], "iteration", f"Loop pass {self.trace.iterations}",
                                   f"{target} receives {self.trace.display(value)}.", header)
                    try:
                        self.exec_block(node.get("body", {}).get("children", []), scope)
                    except Continue:
                        continue
                    except Break:
                        break
                return
        # Classic C-style loop: find the condition and an update.
        match = re.search(r"for\s*\((.*?);(.*?);(.*?)\)", header, re.S)
        if match:
            init, condition, update = match.groups()
            name_match = re.search(r"(?:int|let|var|auto)?\s*([A-Za-z_]\w*)\s*=", init)
            if name_match:
                name = name_match.group(1)
                start = self.eval(init.split("=", 1)[1], scope)
                scope[name] = start
                guard = 0
                while self.eval(condition, scope) and guard < 100:
                    guard += 1
                    self.trace.iterations += 1
                    self.trace.add(node["startLine"], "iteration", f"Loop pass {self.trace.iterations}",
                                   f"{name} is {self.trace.display(scope.get(name))}.", header)
                    try:
                        self.exec_block(node.get("body", {}).get("children", []), scope)
                    except Continue:
                        pass
                    except Break:
                        break
                    if "++" in update:
                        scope[name] = scope.get(name, 0) + 1
                    elif "--" in update:
                        scope[name] = scope.get(name, 0) - 1
                    else:
                        scope[name] = self.eval(update, scope)

    def exec_action(self, node, scope):
        action = node.get("action") or {}
        subtype = action.get("subtype")
        if subtype == "return":
            value = self.eval(action.get("expressionText", ""), scope)
            self.trace.add(node["startLine"], "return", "Return a value", f"Returns {self.trace.display(value)}.", node.get("text", ""))
            raise Return(value)
        if subtype == "break":
            raise Break
        if subtype == "continue":
            raise Continue
        if subtype in {"declaration", "assignment"}:
            target = action.get("targetDisplay") or action.get("targetName")
            expression = action.get("expressionText", "")
            value = self.eval(expression, scope)
            operator = action.get("operator", "=")
            if operator in {"+=", "-=", "*=", "/="}:
                old = scope.get(str(target), 0)
                value = old + value if operator == "+=" else old - value if operator == "-=" else old * value if operator == "*=" else old / value
            scope[str(target)] = value
            self.trace.event("assignment", node["startLine"], target=target, expressionText=expression, value=value)
            self.trace.add(node["startLine"], "assign", f"Set {target}", f"{target} becomes {self.trace.display(value)}.", node.get("text", ""))
            return
        if subtype == "print":
            text = self.format_print(action.get("expressionText", ""), scope)
            if not text.endswith("\n"):
                text += "\n"
            self.trace.output += text
            self.trace.add(node["startLine"], "print", "Print output", f"Output: {text.rstrip()}", node.get("text", ""))
            return
        if subtype == "call":
            self.eval(action.get("expressionText", ""), scope)

    def format_print(self, text, scope):
        if "System.out.print" in text or "printf" in text:
            match = re.search(r"\((.*)\)", text, re.S)
            args = self.split_args(match.group(1) if match else "")
            if "printf" in text and args:
                fmt = self.eval(args[0], scope)
                values = [self.eval(arg, scope) for arg in args[1:]]
                if isinstance(fmt, str):
                    result = fmt.replace("\\n", "\n").replace("%d", "{}").replace("%s", "{}")
                    try:
                        return result.format(*values)
                    except Exception:
                        return result
            return " ".join(self.trace.display(self.eval(arg, scope)) for arg in args)
        # C++ cout << value << endl
        rest = text.split("cout", 1)[-1]
        values = []
        for part in rest.split("<<"):
            part = part.strip()
            if part and "endl" not in part:
                values.append(self.trace.display(self.eval(part, scope)))
        return " ".join(values)

    def split_args(self, text):
        parts, current, depth, quote = [], "", 0, None
        for char in text:
            if quote:
                current += char
                if char == quote:
                    quote = None
                continue
            if char in "\"'":
                quote = char
                current += char
            elif char in "([{":
                depth += 1
                current += char
            elif char in ")]}":
                depth -= 1
                current += char
            elif char == "," and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            parts.append(current.strip())
        return parts

    def eval(self, text, scope):
        if not text or not text.strip():
            return None
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            inner = stripped[1:-1].strip()
            return [self.eval(part, scope) for part in self.split_args(inner)] if inner else []
        try:
            node = self.parse_expression(stripped)
            return self.eval_node(node, scope) if node else 0
        except Exception:
            return 0

    def parse_expression(self, text: str):
        """Wrap an expression so each grammar can parse it outside a statement."""
        if self.analysis["languageId"] == "java":
            wrapper = f"class __Prism {{ void __m() {{ Object __x = {text}; }} }}"
        else:
            wrapper = f"void __prism() {{ int __x = {text}; }}"
        self.active_bytes = wrapper.encode("utf-8")
        tree = self.parser.parse(self.active_bytes)
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in {"variable_declarator", "init_declarator"}:
                value = node.child_by_field_name("value")
                if value is not None:
                    return value
                named = node.named_children
                if len(named) >= 2:
                    return named[-1]
            stack.extend(reversed(node.named_children))
        return None

    def eval_node(self, node, scope):
        if node is None:
            return None
        kind = node.type
        if kind in {"program", "translation_unit", "expression_statement", "parenthesized_expression"}:
            return self.eval_node(node.named_children[0], scope) if node.named_children else None
        if kind in {"decimal_integer_literal", "number_literal", "integer_literal"}:
            value = self.text(node).replace("L", "")
            return float(value) if "." in value else int(value)
        if kind in {"string_literal", "string"}:
            return self.text(node).strip('"')
        if kind in {"character_literal"}:
            return self.text(node).strip("'")
        if kind in {"true", "false"}:
            return kind == "true"
        if kind == "null":
            return None
        if kind in {"identifier", "field_identifier"}:
            value = scope.get(self.text(node))
            return value if value is not None else 0
        if kind in {"array_initializer", "initializer_list"}:
            return [self.eval_node(child, scope) for child in node.named_children]
        if kind == "binary_expression":
            left_node = self.field(node, "left")
            right_node = self.field(node, "right")
            left = self.eval_node(left_node, scope)
            right = self.eval_node(right_node, scope)
            op = self.text(node.child_by_field_name("operator")) if node.child_by_field_name("operator") else ""
            return {
                "+": lambda: left + right, "-": lambda: left - right,
                "*": lambda: left * right, "/": lambda: left / right,
                "%": lambda: left % right, ">": lambda: left > right,
                "<": lambda: left < right, ">=": lambda: left >= right,
                "<=": lambda: left <= right, "==": lambda: left == right,
                "!=": lambda: left != right, "&&": lambda: bool(left) and bool(right),
                "||": lambda: bool(left) or bool(right),
            }.get(op, lambda: 0)()
        if kind == "unary_expression":
            operand = self.field(node, "argument")
            value = self.eval_node(operand, scope)
            op_node = self.field(node, "operator")
            op = self.text(op_node) if op_node else self.text(node)[0]
            return -value if op == "-" else (not bool(value) if op == "!" else value)
        if kind == "update_expression":
            return self.eval_node(node.named_children[0], scope) if node.named_children else 0
        if kind == "subscript_expression":
            array = self.eval_node(self.field(node, "argument") or node.named_children[0], scope)
            index = self.eval_node(self.field(node, "index") or node.named_children[-1], scope)
            try:
                return array[index]
            except Exception:
                return 0
        if kind in {"method_invocation", "call_expression"}:
            name_node = self.field(node, "name") or self.field(node, "function")
            name = self.text(name_node) if name_node else ""
            args_node = self.field(node, "arguments")
            args = [self.eval_node(child, scope) for child in args_node.named_children] if args_node else []
            if name in self.functions:
                item = self.functions[name]
                return self.call_function(item, args, scope)
            return 0
        return 0

    def call_function(self, item, args, scope):
        local = {param["name"]: value for param, value in zip(item["params"], args)}
        self.trace.scopes.append(local)
        self.trace.calls += 1
        self.trace.add(item["startLine"], "call", f"Call {item['name']}()", "Enters the function.")
        try:
            self.exec_block(item["body"]["children"], local)
        except Return as result:
            return result.value
        finally:
            self.trace.scopes.pop()
        return 0


def _metrics(source: str, factory: Factory) -> dict[str, int]:
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


def analyze_compiled(source: str, language: str = "java") -> dict[str, Any]:
    text = str(source or "").replace("\r\n", "\n").replace("\r", "\n")
    factory = Factory(text, language)
    tree = factory.parser.parse(text.encode("utf-8"))
    root = {
        "type": "program", "id": factory.nid(), "startLine": 1,
        "endLine": len(text.split("\n")), "header": "Program",
        "body": factory.block(tree.root_node, 0),
        "language": LANGUAGES[language]["name"], "parseMode": "braces",
        "diagnostics": [],
    }
    metrics = _metrics(text, factory)
    main = next((fn for fn in factory.functions if fn["name"] in {"main", "Main"}), None)
    entry = {"kind": "function", "node": main, "name": main["name"] if main else "main", "inferred": False} if main else {
        "kind": "program", "node": root, "name": "Program", "inferred": False
    }
    analysis = {
        "source": text, "language": LANGUAGES[language], "languageId": language,
        "root": root, "diagnostics": [], "lineCount": len(text.split("\n")),
        "lines": [{"number": i, "text": line} for i, line in enumerate(text.split("\n"), 1)],
        "highlightedLines": [line for line in text.split("\n")],
        "functions": factory.functions, "classes": factory.classes,
        "assignments": factory.assignments, "actionNodes": factory.actions,
        "metrics": metrics, "entry": entry,
        "flowFocus": {"kind": entry["kind"], "node": entry["node"], "name": entry["name"]},
        "parseDiagnostics": [], "confidence": "medium",
        "projectTitle": f"{LANGUAGES[language]['name']} program",
        "featureSummary": f"{LANGUAGES[language]['name']} · {metrics['loops']} loops · {metrics['functions']} functions",
    }
    trace = Runner(analysis, text).run()
    guide = _guide(analysis, trace, LANGUAGES[language]["name"])
    return {"analysis": analysis, "trace": trace, "guide": guide}
