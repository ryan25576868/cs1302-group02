"""Tests for Java, C++ and C analysis."""

from __future__ import annotations

import unittest

from python_app.compiled_analysis import analyze_compiled


class CompiledAnalysisTests(unittest.TestCase):
    def test_java_loop(self) -> None:
        source = """public class Main {
  public static void main(String[] args) {
    int[] prices = {12, 8, 25};
    int total = 0;
    for (int price : prices) {
      if (price >= 10) { total += price; }
    }
    System.out.println(total);
  }
}
"""
        result = analyze_compiled(source, "java")
        self.assertEqual(result["analysis"]["metrics"]["loops"], 1)
        self.assertEqual(result["trace"]["output"], "37\n")
        self.assertTrue(result["trace"]["complete"])
        self.assertEqual(result["analysis"]["entry"]["name"], "main")

    def test_cpp_loop(self) -> None:
        source = """#include <iostream>
using namespace std;
int main() {
  int prices[] = {12, 8, 25};
  int total = 0;
  for (int price : prices) {
    if (price >= 10) { total += price; }
  }
  cout << total << endl;
  return 0;
}
"""
        result = analyze_compiled(source, "cpp")
        self.assertEqual(result["trace"]["output"], "37\n")
        self.assertTrue(result["trace"]["complete"])

    def test_c_loop(self) -> None:
        source = """#include <stdio.h>
int main() {
  int prices[] = {12, 8, 25};
  int total = 0;
  for (int i = 0; i < 3; i++) {
    if (prices[i] >= 10) { total += prices[i]; }
  }
  printf("%d\\n", total);
  return 0;
}
"""
        result = analyze_compiled(source, "c")
        self.assertEqual(result["trace"]["output"], "37\n")
        self.assertTrue(result["trace"]["complete"])


if __name__ == "__main__":
    unittest.main()
