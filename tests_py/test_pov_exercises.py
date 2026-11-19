"""Tests for deterministic Practice Similar Questions generation."""

from __future__ import annotations

import ast
import unittest

from python_app.function_pov.analyzer import analyze_source
from python_app.function_pov.pov.exercises import (
    ExerciseGenerationError,
    PracticeExerciseGenerator,
    _logic_change_explanation,
)


LOOP_AND_TOTAL = (
    "prices = [12, 8, 25]\n"
    "total = 0\n"
    "for price in prices:\n"
    "    if price >= 10:\n"
    "        total += price\n"
    "print(total)\n"
)


def _function_id(source: str, name: str, filename: str = "sample.py") -> str:
    return next(
        function.id
        for function in analyze_source(source, filename).functions
        if function.name == name
    )


class PracticeExerciseGeneratorTests(unittest.TestCase):
    def test_new_values_are_deterministic_distinct_and_simulated(self) -> None:
        generator = PracticeExerciseGenerator()
        original_tree = ast.dump(ast.parse(LOOP_AND_TOTAL), include_attributes=False)

        first = generator.generate(
            "new_values", "code", LOOP_AND_TOTAL, "sample.py"
        )
        second = generator.generate(
            "new_values", "code", LOOP_AND_TOTAL, "sample.py"
        )
        other_session_first = PracticeExerciseGenerator().generate(
            "new_values", "code", LOOP_AND_TOTAL, "sample.py"
        )

        self.assertNotEqual(first.source, LOOP_AND_TOTAL)
        self.assertNotEqual(first.source, second.source)
        self.assertEqual(first.source, other_session_first.source)
        self.assertEqual(
            [type(node) for node in ast.walk(ast.parse(LOOP_AND_TOTAL))],
            [type(node) for node in ast.walk(ast.parse(first.source))],
        )
        self.assertEqual(original_tree, ast.dump(ast.parse(LOOP_AND_TOTAL), include_attributes=False))
        self.assertTrue(any(step.challenge for step in first.simulation.steps))
        self.assertEqual(first.simulation.mode, "code")
        self.assertNotEqual(
            first.simulation.output,
            second.simulation.output,
        )

    def test_function_new_values_keep_source_and_optional_defaults(self) -> None:
        source = "def add(value, amount=2):\n    return value + amount\n"
        function_id = _function_id(source, "add")
        candidate = PracticeExerciseGenerator().generate(
            "new_values",
            "function",
            source,
            "sample.py",
            function_id,
            {"value": 3},
        )

        self.assertEqual(candidate.source, source)
        self.assertEqual(candidate.function_id, function_id)
        self.assertEqual(candidate.arguments, {"value": 8, "amount": 2})
        return_step = next(
            step for step in candidate.simulation.steps if step.kind == "return"
        )
        self.assertEqual(return_step.expected, 10)
        self.assertIn("arithmetic", candidate.concepts)
        self.assertIn("return", candidate.concepts)

    def test_new_values_preserve_source_comments_and_surrounding_text(self) -> None:
        source = "# keep this note\nvalues = [1, 2]  # input data\nprint(values)\n"
        candidate = PracticeExerciseGenerator().generate(
            "new_values", "code", source, "sample.py"
        )

        self.assertIn("# keep this note", candidate.source)
        self.assertIn("# input data", candidate.source)
        self.assertTrue(candidate.source.startswith("# keep this note\n"))

    def test_new_values_can_vary_bounded_range_literals(self) -> None:
        source = (
            "total = 0\n"
            "for value in range(3):\n"
            "    total += value\n"
            "print(total)\n"
        )
        candidate = PracticeExerciseGenerator().generate(
            "new_values", "code", source, "sample.py"
        )

        self.assertNotEqual(candidate.source, source)
        self.assertIn("range(", candidate.source)
        self.assertTrue(candidate.simulation.output)

    def test_new_values_prioritize_branch_boundary_and_batch_list_changes(self) -> None:
        branch_source = (
            "score = 4\n"
            "if score >= 5:\n"
            "    print('ready')\n"
            "else:\n"
            "    print('retry')\n"
        )
        branch_exercise = PracticeExerciseGenerator().generate(
            "new_values", "code", branch_source, "sample.py"
        )
        branch_tree = ast.parse(branch_exercise.source)
        self.assertEqual(ast.literal_eval(branch_tree.body[0].value), 5)
        condition = next(
            step for step in branch_exercise.simulation.steps
            if step.kind == "condition"
        )
        self.assertTrue(condition.expected)

        list_exercise = PracticeExerciseGenerator().generate(
            "new_values", "code", LOOP_AND_TOTAL, "sample.py"
        )
        list_assignment = ast.parse(list_exercise.source).body[0]
        self.assertEqual(
            ast.literal_eval(list_assignment.value),
            [9, 10, 11],
        )
        branch_answers = [
            step.expected for step in list_exercise.simulation.steps
            if step.kind == "condition"
        ]
        self.assertIn(False, branch_answers)
        self.assertIn(True, branch_answers)

    def test_new_values_use_meaningful_multi_value_changes_without_ast_changes(self) -> None:
        source = "values = [10, 20, 30]\nprint(values)\n"
        exercise = PracticeExerciseGenerator().generate(
            "new_values", "code", source, "sample.py"
        )

        original_tree = ast.parse(source)
        generated_tree = ast.parse(exercise.source)
        self.assertEqual(
            [type(node) for node in ast.walk(original_tree)],
            [type(node) for node in ast.walk(generated_tree)],
        )
        original_values = ast.literal_eval(original_tree.body[0].value)
        generated_values = ast.literal_eval(generated_tree.body[0].value)
        self.assertEqual(
            [new - old for old, new in zip(original_values, generated_values)],
            [5, 5, 5],
        )
        self.assertTrue(any(step.challenge for step in exercise.simulation.steps))

    def test_similar_logic_templates_are_unique_and_exhaust_explicitly(self) -> None:
        generator = PracticeExerciseGenerator()
        first = generator.generate(
            "similar_logic", "code", LOOP_AND_TOTAL, "sample.py"
        )
        second = generator.generate(
            "similar_logic", "code", LOOP_AND_TOTAL, "sample.py"
        )
        self.assertNotEqual(first.source, second.source)
        self.assertIn("if ", first.source)
        self.assertIn("for ", first.source)
        self.assertIn("total +=", first.source)
        self.assertTrue(first.simulation.output)
        self.assertTrue(second.simulation.output)
        self.assertTrue(first.logic_change)
        self.assertNotEqual(
            ast.dump(ast.parse(LOOP_AND_TOTAL), include_attributes=False),
            ast.dump(ast.parse(first.source), include_attributes=False),
        )
        with self.assertRaisesRegex(
            ExerciseGenerationError, "No unused Similar Logic"
        ):
            generator.generate(
                "similar_logic", "code", LOOP_AND_TOTAL, "sample.py"
            )

    def test_similar_logic_rejects_changes_to_only_names_and_literals(self) -> None:
        original = "total = 1\ntotal += 2\nprint(total)\n"
        renamed_and_revalued = "answer = 10\nanswer += 20\nprint(answer)\n"
        arithmetic_change = "answer = 10\nanswer *= 20\nprint(answer)\n"

        self.assertIsNone(
            _logic_change_explanation(
                original, renamed_and_revalued, "code", None, "sample.py"
            )
        )
        self.assertIsNotNone(
            _logic_change_explanation(
                original, arithmetic_change, "code", None, "sample.py"
            )
        )

    def test_code_similar_logic_supports_while_and_branch_output(self) -> None:
        while_source = (
            "count = 3\n"
            "total = 0\n"
            "while count > 0:\n"
            "    total += count\n"
            "    count -= 1\n"
            "print(total)\n"
        )
        while_exercise = PracticeExerciseGenerator().generate(
            "similar_logic", "code", while_source, "sample.py"
        )
        self.assertIn("while ", while_exercise.source)
        self.assertEqual(while_exercise.simulation.output, "9\n")

        branch_source = (
            "score = 4\n"
            "if score >= 5:\n"
            "    print('ready')\n"
            "else:\n"
            "    print('retry')\n"
        )
        branch_exercise = PracticeExerciseGenerator().generate(
            "similar_logic", "code", branch_source, "sample.py"
        )
        self.assertIn("if ", branch_exercise.source)
        self.assertIn("output", branch_exercise.concepts)
        self.assertEqual(
            type(ast.parse(branch_exercise.source).body[1].test.ops[0]),
            ast.Gt,
        )
        self.assertTrue(branch_exercise.logic_change)
        self.assertTrue(branch_exercise.simulation.output)

    def test_function_similar_logic_preserves_branch_and_return_practice(self) -> None:
        source = (
            "def choose(value):\n"
            "    if value > 2:\n"
            "        return value + 1\n"
            "    return value - 1\n"
        )
        function_id = _function_id(source, "choose")
        candidate = PracticeExerciseGenerator().generate(
            "similar_logic",
            "function",
            source,
            "sample.py",
            function_id,
            {"value": 3},
        )
        kinds = [step.kind for step in candidate.simulation.steps]

        self.assertEqual(candidate.function_id, function_id)
        self.assertIn("if ", candidate.source)
        self.assertIn("return ", candidate.source)
        self.assertIn("condition", candidate.concepts)
        self.assertIn("return", candidate.concepts)
        self.assertIn("condition", kinds)
        self.assertEqual(
            next(step.expected for step in candidate.simulation.steps if step.kind == "return"),
            2,
        )
        self.assertTrue(candidate.logic_change)

    def test_function_similar_logic_supports_loops_and_project_calls(self) -> None:
        loop_source = (
            "def total(values):\n"
            "    result = 0\n"
            "    for value in values:\n"
            "        result += value\n"
            "    return result\n"
        )
        loop_candidate = PracticeExerciseGenerator().generate(
            "similar_logic",
            "function",
            loop_source,
            "sample.py",
            _function_id(loop_source, "total"),
            {"values": [1, 2]},
        )
        self.assertIn("loop", loop_candidate.concepts)
        self.assertEqual(loop_candidate.simulation.answer(
            next(i for i, step in enumerate(loop_candidate.simulation.steps) if step.kind == "return")
        ), 13)

        call_source = (
            "def increment(value):\n"
            "    return value + 1\n"
            "def double(value):\n"
            "    return increment(value) * 2\n"
        )
        call_candidate = PracticeExerciseGenerator().generate(
            "similar_logic",
            "function",
            call_source,
            "sample.py",
            _function_id(call_source, "double"),
            {"value": 3},
        )
        kinds = [step.kind for step in call_candidate.simulation.steps]
        self.assertIn("function call", call_candidate.concepts)
        self.assertIn("function_call", kinds)
        self.assertIn("return", kinds)
        self.assertIn("return value * 2", call_candidate.source)
        self.assertTrue(call_candidate.logic_change)

    def test_function_similar_logic_supports_arithmetic_returns(self) -> None:
        source = "def scale(value):\n    return value * 3\n"
        candidate = PracticeExerciseGenerator().generate(
            "similar_logic",
            "function",
            source,
            "sample.py",
            _function_id(source, "scale"),
            {"value": 2},
        )
        return_step = next(
            step for step in candidate.simulation.steps if step.kind == "return"
        )

        self.assertIn("arithmetic", candidate.concepts)
        self.assertEqual(return_step.expected, 5)

    def test_function_similar_logic_preserves_boolean_branch_types(self) -> None:
        source = (
            "def apply_discount(price, is_member):\n"
            "    if is_member:\n"
            "        return price * 0.9\n"
            "    return price\n"
        )
        candidate = PracticeExerciseGenerator().generate(
            "similar_logic",
            "function",
            source,
            "sample.py",
            _function_id(source, "apply_discount"),
            {"price": 10, "is_member": True},
        )
        return_step = next(
            step for step in candidate.simulation.steps if step.kind == "return"
        )

        self.assertIn("if is_member:", candidate.source)
        self.assertIn("price - 2", candidate.source)
        self.assertEqual(return_step.expected, 8)

    def test_unavailable_or_unsafe_variants_are_not_reused_or_shown(self) -> None:
        generator = PracticeExerciseGenerator()
        boolean_source = "ready = True\nprint(ready)\n"
        generator.generate("new_values", "code", boolean_source, "sample.py")
        with self.assertRaisesRegex(ExerciseGenerationError, "No safe, unused"):
            generator.generate("new_values", "code", boolean_source, "sample.py")

        unsupported_logic = "try:\n    value = 1\nexcept Exception:\n    value = 2\n"
        with self.assertRaisesRegex(ExerciseGenerationError, "does not match"):
            PracticeExerciseGenerator().generate(
                "similar_logic", "code", unsupported_logic, "sample.py"
            )

        unsafe_source = "import os\nvalues = [1, 2]\nprint(values)\n"
        with self.assertRaisesRegex(ExerciseGenerationError, "No safe, unused"):
            PracticeExerciseGenerator().generate(
                "new_values", "code", unsafe_source, "sample.py"
            )

    def test_multi_function_program_keeps_new_values_but_no_similar_logic(self) -> None:
        source = (
            "def adjust(score, bonus=2):\n"
            "    if score >= 70:\n"
            "        if score >= 90:\n"
            "            return score + bonus\n"
            "        return score\n"
            "    return 0\n"
            "\n"
            "def total(scores):\n"
            "    result = 0\n"
            "    for score in scores:\n"
            "        result += adjust(score)\n"
            "    return result\n"
            "\n"
            "scores = [60, 75, 95]\n"
            "answer = total(scores)\n"
            "print(answer)\n"
        )
        generator = PracticeExerciseGenerator()
        exercise = generator.generate(
            "new_values", "code", source, "sample.py"
        )
        self.assertEqual(
            [type(node) for node in ast.walk(ast.parse(source))],
            [type(node) for node in ast.walk(ast.parse(exercise.source))],
        )
        self.assertTrue(exercise.simulation.output)
        self.assertEqual(
            generator.similar_logic_availability(
                "code", source, "sample.py"
            ),
            "This code does not match a supported Similar Logic pattern.",
        )
        with self.assertRaisesRegex(ExerciseGenerationError, "does not match"):
            generator.generate(
                "similar_logic", "code", source, "sample.py"
            )


if __name__ == "__main__":
    unittest.main()
