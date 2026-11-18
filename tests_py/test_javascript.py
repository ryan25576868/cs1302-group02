"""Tests for the Python-native JavaScript/TypeScript analysis path."""

from __future__ import annotations

import unittest

from python_app.js_analysis import analyze_javascript


class JavaScriptAnalysisTests(unittest.TestCase):
    def test_loop_and_output(self) -> None:
        source = """const prices = [12, 8, 25];
let total = 0;
for (const price of prices) {
  if (price >= 10) {
    total += price;
  }
}
console.log(total);
"""
        result = analyze_javascript(source, "javascript")
        self.assertEqual(result["analysis"]["metrics"]["loops"], 1)
        self.assertEqual(result["analysis"]["metrics"]["conditions"], 1)
        self.assertEqual(result["trace"]["output"], "37\n")
        self.assertTrue(result["trace"]["complete"])
        self.assertEqual(result["trace"]["warnings"], [])
        self.assertGreaterEqual(len(result["guide"]["lineNotes"]), 5)

    def test_function_and_return(self) -> None:
        source = """function area(width, height) {
  return width * height;
}
const result = area(4, 5);
console.log(result);
"""
        result = analyze_javascript(source, "javascript")
        self.assertEqual(len(result["analysis"]["functions"]), 1)
        self.assertEqual(result["trace"]["output"], "20\n")
        self.assertTrue(result["trace"]["complete"])

    def test_typescript_parameters_and_types(self) -> None:
        source = """function greet(name: string): string {
  const message: string = "Hello, " + name;
  return message;
}
const result = greet("Ada");
console.log(result);
"""
        result = analyze_javascript(source, "typescript")
        self.assertEqual(result["analysis"]["language"]["name"], "TypeScript")
        self.assertEqual(result["trace"]["output"], "Hello, Ada\n")
        self.assertTrue(result["trace"]["complete"])

    def test_parse_warning_is_reported(self) -> None:
        result = analyze_javascript("const = ;\n", "javascript")
        self.assertIn("parsed", " ".join(item["message"] for item in result["analysis"]["diagnostics"]).lower())


if __name__ == "__main__":
    unittest.main()
