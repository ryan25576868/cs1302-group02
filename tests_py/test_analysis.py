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
    def test_formatted_strings_and_format_limits(self):
        source = ('scores = [72, 88, 91, 65]\npassed = 0\n'
                  'for score in scores:\n    if score >= 70:\n        passed += 1\n'
                  'print(f"Passed: {passed}")\nprint(f"{1.5:.2f} {passed!r}")')
        trace = analyze_python(source)["trace"]
        self.assertTrue(trace["complete"], trace["warnings"])
        self.assertEqual(trace["output"], "Passed: 3\n1.50 3\n")
        trace = analyze_python('print(f"{1:1000000000}")')["trace"]
        self.assertFalse(trace["complete"])
        self.assertIn("safe limit", trace["warnings"][0])

    def test_unary_and_mutable_aliases_follow_python(self):
        source = "a=[1]\nb=a\nb += [2]\nb *= 2\nprint(~1, a)"
        trace = analyze_python(source)["trace"]
        self.assertTrue(trace["complete"], trace["warnings"])
        self.assertEqual(trace["output"], "-2 [1, 2, 1, 2]\n")

    def test_local_read_before_assignment_stops(self):
        source = "x=1\ndef f():\n print(x)\n x=2\nf()"
        trace = analyze_python(source)["trace"]
        self.assertFalse(trace["complete"])
        self.assertEqual(trace["output"], "")
        self.assertIn("before assignment", trace["warnings"][0])
        self.assertEqual(trace["stoppedLine"], 3)

    def test_python_expression_semantics_and_defaults(self):
        source = "x = 5\ndef f(n=3):\n    if n:\n        return x + n\nprint(2 ** 3, not True, 1 < 2 < 0, f(), sep='|', end='!')"
        trace = analyze_python(source)["trace"]
        self.assertTrue(trace["complete"], trace["warnings"])
        self.assertEqual(trace["output"], "8|False|False|8!")
        self.assertEqual(trace["lastTopLevelReturn"]["value"], "8")
        self.assertNotIn("n", [item["name"] for item in trace["finalVars"]])

    def test_loop_limits_and_else(self):
        for limit in (60, 61):
            trace = analyze_python(f"i=0\nwhile i<{limit}:\n i+=1\nprint(i)")["trace"]
            self.assertEqual(trace["complete"], limit == 60)
        trace = analyze_python("for i in range(1000000000):\n pass")["trace"]
        self.assertFalse(trace["complete"])
        self.assertEqual(trace["stoppedReason"], "step_limit")
        self.assertEqual(analyze_python("for i in range(2):\n pass\nelse:\n print(99)")["trace"]["output"], "99\n")
        self.assertEqual(analyze_python("for i in range(2):\n break\nelse:\n print(99)")["trace"]["output"], "")

    def test_unsupported_code_stops_without_fabricated_output(self):
        for source in ("print(missing)", "a=[1]\na[0]=2", "try:\n print(1)\nexcept:\n pass"):
            trace = analyze_python(source)["trace"]
            self.assertFalse(trace["complete"], source)
            self.assertTrue(trace["warnings"])

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
