"""Unit tests for code complexity and readability advisor."""

import json
import unittest

from python_app.analysis import analyze_python
from python_app.compiled_analysis import analyze_compiled
from python_app.metrics_advisor import (
    evaluate_code_health,
    export_health_json,
    format_health_markdown,
)


class TestMetricsAdvisor(unittest.TestCase):
    def test_flat_python_code_grade_a(self):
        result = analyze_python("x = 10\ny = x + 5\nprint(y)\n")
        health = evaluate_code_health(result["analysis"], result["trace"])
        self.assertEqual(health["cyclomaticComplexity"], 1)
        self.assertEqual(health["grade"], "A")

    def test_branching_and_report_formats(self):
        code = (
            "for i in range(4):\n"
            "    if i > 1:\n"
            "        for j in range(2):\n"
            "            if j == 1:\n"
            "                print(i, j)\n"
        )
        result = analyze_python(code)
        health = evaluate_code_health(result["analysis"], result["trace"])
        self.assertGreaterEqual(health["cyclomaticComplexity"], 5)
        self.assertIn(health["grade"], {"B", "C"})

        md = format_health_markdown(health)
        self.assertIn("## Code Health & Complexity", md)

        parsed = json.loads(export_health_json(result["analysis"], result["trace"]))
        self.assertEqual(parsed["language"], "python")
        self.assertEqual(parsed["health"]["cyclomaticComplexity"], health["cyclomaticComplexity"])

    def test_compiled_java_code_health(self):
        java_code = """public class Main {
    public static void main(String[] args) {
        int[] scores = {72, 88, 91, 65};
        int passed = 0;
        for (int score : scores) {
            if (score >= 70) {
                passed += 1;
            }
        }
        System.out.println(passed);
    }
}"""
        result = analyze_compiled(java_code, "java")
        health = evaluate_code_health(result["analysis"], result["trace"])
        self.assertEqual(health["cyclomaticComplexity"], 3)
        self.assertIn(health["grade"], {"A", "B", "C"})


if __name__ == "__main__":
    unittest.main()