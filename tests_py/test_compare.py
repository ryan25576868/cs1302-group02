"""Tests for the structural compare engine (Prism trees -> structscope diff)."""

from __future__ import annotations

import unittest

from python_app import compare_engine
from python_app.compare_engine import (
    aligned_rows,
    analyze_source,
    compare_sources,
    describe,
    model_from_analysis,
)

ENGINE_MISSING = compare_engine.ENGINE_ERROR


@unittest.skipIf(ENGINE_MISSING, f"structscope not importable: {ENGINE_MISSING}")
class ModelFromAnalysisTests(unittest.TestCase):
    def test_maps_nested_symbols_and_kinds(self):
        analysis = {
            "lines": [{"number": i, "text": text} for i, text in enumerate(
                ["class Shape {", "  int area() {", "    return 1;", "  }", "}"], start=1
            )],
            "root": {"type": "root", "body": {"children": [
                {
                    "type": "class", "name": "Shape", "startLine": 1, "endLine": 5,
                    "header": "class Shape",
                    "body": {"children": [
                        {
                            "type": "function", "name": "area", "startLine": 2, "endLine": 4,
                            "header": "int area()", "params": [],
                            "body": {"children": [
                                {"type": "return", "header": "return 1", "startLine": 3},
                            ]},
                        },
                    ]},
                },
            ]}},
        }
        model = model_from_analysis(analysis, "shape.java")
        self.assertEqual(len(model.symbols), 1)
        shape = model.symbols[0]
        self.assertEqual(shape.kind, "class")
        self.assertEqual(shape.qualname, "Shape")
        self.assertEqual(shape.lineno, 1)
        self.assertEqual(shape.end_lineno, 5)
        self.assertEqual(shape.loc, 5)
        self.assertEqual(len(shape.children), 1)
        method = shape.children[0]
        self.assertEqual(method.kind, "method")
        self.assertEqual(method.qualname, "Shape.area")
        self.assertEqual(method.depth, 1)
        self.assertEqual(method.display, "area()")

    def test_ignores_nodes_that_are_not_containers(self):
        analysis = {
            "lines": [{"number": 1, "text": "if x: pass"}],
            "root": {"type": "root", "body": {"children": [
                {"type": "if", "header": "if x", "startLine": 1},
            ]}},
        }
        self.assertEqual(model_from_analysis(analysis, "x.py").symbols, [])


@unittest.skipIf(ENGINE_MISSING, f"structscope not importable: {ENGINE_MISSING}")
class CompareSourcesTests(unittest.TestCase):
    BEFORE = """def load(path):
    rows = []
    for line in open(path):
        rows.append(line.strip())
    return rows


def total(rows):
    return sum(len(row) for row in rows)
"""

    AFTER = """def load(path, encoding="utf-8"):
    rows = []
    for line in open(path, encoding=encoding):
        rows.append(line.strip())
    return rows


def total(rows):
    return sum(len(row) for row in rows)


def average(rows):
    return total(rows) / max(1, len(rows))
"""

    def test_statuses(self):
        result = compare_sources("python", self.BEFORE, self.AFTER, "a.py", "b.py")
        by_name = {pair.symbol.qualname: pair.status.value for pair in result.pairs}
        self.assertEqual(by_name["load"], "modified")
        self.assertEqual(by_name["total"], "unchanged")
        self.assertEqual(by_name["average"], "added")

    def test_summary_counts_and_labels(self):
        result = compare_sources("python", self.BEFORE, self.AFTER, "a.py", "b.py")
        summary = result.summary()
        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["removed"], 0)
        self.assertEqual(summary["language"], "python")
        self.assertEqual(result.old.label, "a.py")
        self.assertEqual(result.new.label, "b.py")
        line = describe(summary)
        self.assertIn("1 added", line)
        self.assertIn("LOC", line)

    def test_rename_is_moved(self):
        before = "def alpha(n):\n    return n * 2\n"
        after = "def beta(n):\n    return n * 2\n"
        result = compare_sources("python", before, after, "a.py", "b.py")
        statuses = [pair.status.value for pair in result.pairs]
        self.assertIn("moved", statuses)
        self.assertNotIn("added", statuses)
        self.assertNotIn("removed", statuses)

    def test_removal(self):
        before = "def gone():\n    return 1\n\ndef kept():\n    return 2\n"
        after = "def kept():\n    return 2\n"
        result = compare_sources("python", before, after, "a.py", "b.py")
        by_name = {pair.symbol.qualname: pair.status.value for pair in result.pairs}
        self.assertEqual(by_name["gone"], "removed")
        self.assertEqual(by_name["kept"], "unchanged")

    def test_parses_both_sides_with_the_same_analyzer(self):
        data = analyze_source("python", self.BEFORE)
        self.assertIn("analysis", data)
        self.assertIn("lines", data["analysis"])


class AlignedRowsTests(unittest.TestCase):
    def test_equal_replaced_and_inserted_lines(self):
        rows = aligned_rows(["a", "b", "c"], ["a", "B", "c", "d"], 1, 1)
        self.assertEqual(rows[0], ("eq", 1, "a", 1, "a"))
        self.assertEqual(rows[1], ("rep", 2, "b", 2, "B"))
        self.assertEqual(rows[2], ("eq", 3, "c", 3, "c"))
        self.assertEqual(rows[3], ("ins", 0, "", 4, "d"))

    def test_deleted_lines_keep_the_other_column_empty(self):
        rows = aligned_rows(["a", "b"], ["a"], 10, 20)
        self.assertEqual(rows[-1], ("del", 11, "b", 0, ""))


if __name__ == "__main__":
    unittest.main()
