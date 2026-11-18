"""Tests for the Python-native analysis path."""

from __future__ import annotations

import unittest

from python_app.analysis import analyze_python


LOOP_SOURCE = """prices = [12, 8, 25]
total = 0
for price in prices:
    if price >= 10:
        total += price
print(total)
"""

FUNCTION_SOURCE = """def apply_discount(price, is_member):
    if is_member:
        return price * 0.9
    return price

prices = [12, 8, 25]
total = 0
for price in prices:
    total += apply_discount(price, True)
print("Total:", total)
"""


class PythonAnalysisTests(unittest.TestCase):
    def test_loop_analysis_and_trace(self) -> None:
        result = analyze_python(LOOP_SOURCE)
        analysis, trace, guide = result["analysis"], result["trace"], result["guide"]
        self.assertEqual(analysis["metrics"]["loops"], 1)
        self.assertEqual(analysis["metrics"]["conditions"], 1)
        self.assertEqual(trace["output"], "37\n")
        self.assertTrue(trace["complete"])
        self.assertGreaterEqual(len(trace["steps"]), 8)
        self.assertTrue(any(event["kind"] == "assignment" for event in trace["events"]))
        self.assertGreaterEqual(len(guide["lineNotes"]), 5)
        self.assertGreaterEqual(len(guide["concepts"]), 3)
        self.assertIn("37", guide["summary"])

    def test_function_call_and_return(self) -> None:
        result = analyze_python(FUNCTION_SOURCE)
        analysis, trace = result["analysis"], result["trace"]
        self.assertEqual(len(analysis["functions"]), 1)
        self.assertEqual(trace["output"], "Total: 40.5\n")
        self.assertTrue(trace["complete"])
        self.assertGreaterEqual(trace["functionCalls"], 3)
        self.assertEqual(trace["warnings"], [])

    def test_syntax_error_is_reported(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            analyze_python("def broken(:\n    pass")
        self.assertIn("syntax", str(ctx.exception).lower())

    def test_empty_source_is_analysable(self) -> None:
        result = analyze_python("")
        self.assertEqual(result["analysis"]["lineCount"], 1)
        self.assertEqual(result["trace"]["warnings"], [])


if __name__ == "__main__":
    unittest.main()
