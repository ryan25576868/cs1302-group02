"""Tests for the safe Function POV simulator and Prism integration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from python_app import i18n
from python_app.analysis import analyze_python
from python_app.function_pov.analyzer import analyze_source
from python_app.function_pov.pov.engine import (
    MAX_SOURCE_CHARS,
    SimulationError,
    build_program_simulation_from_source,
    build_simulation_from_source,
)
from python_app.js_analysis import analyze_javascript
from python_app.native_app import MainWindow
from python_app.function_pov_ui import (
    MAX_JSON_INPUT_CHARS,
    FunctionPOVPage,
)


class FunctionPOVEngineTests(unittest.TestCase):
    def test_default_arguments_answers_and_private_expected_values(self) -> None:
        source = "def add(value, amount=2):\n    return value + amount\n"
        analysis = analyze_source(source)
        function = analysis.functions[0]
        simulation = build_simulation_from_source(source, function.id, {"value": 3})

        self.assertEqual(simulation.steps[-1].kind, "return")
        self.assertFalse(simulation.check(1, 4)["correct"])
        self.assertTrue(simulation.hint(1))
        self.assertEqual(simulation.answer(1), 5)
        self.assertTrue(simulation.check(1, 5)["correct"])
        self.assertNotIn("expected", simulation.public_dict()["steps"][-1])

    def test_nested_function_call_and_branch_challenges(self) -> None:
        source = (
            "def double(value):\n"
            "    return value * 2\n"
            "def choose(value):\n"
            "    if value > 2:\n"
            "        return double(value)\n"
            "    return 0\n"
        )
        analysis = analyze_source(source)
        simulation = build_simulation_from_source(
            source,
            next(function.id for function in analysis.functions if function.name == "choose"),
            {"value": 3},
        )
        branch_index = next(i for i, step in enumerate(simulation.steps) if step.kind == "condition")
        call_index = next(i for i, step in enumerate(simulation.steps) if step.kind == "function_call")

        self.assertTrue(simulation.check(branch_index, True)["correct"])
        self.assertFalse(simulation.check(call_index, "choose")["correct"])
        self.assertTrue(simulation.check(call_index, "double")["correct"])

    def test_rejects_unsupported_code_without_executing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed.txt"
            source = (
                "def unsafe():\n"
                f"    open({str(marker)!r}, 'w').write('executed')\n"
                "    return 1\n"
            )
            function = analyze_source(source).functions[0]

            with self.assertRaises(SimulationError):
                build_simulation_from_source(source, function.id)

            self.assertFalse(marker.exists())

    def test_function_simulation_checks_source_length_before_analysis(self) -> None:
        prefix = "def identity():\n    return 1\n"
        at_limit = prefix + "#" * (MAX_SOURCE_CHARS - len(prefix))
        analysis = analyze_source(at_limit)
        simulation = build_simulation_from_source(
            at_limit,
            analysis.functions[0].id,
        )
        self.assertEqual(simulation.steps[-1].expected, 1)

        source = " " * (MAX_SOURCE_CHARS + 1)

        with self.assertRaisesRegex(SimulationError, "60000"):
            build_simulation_from_source(source, "missing.function")

    def test_be_the_code_accepts_top_level_statements_without_functions(self) -> None:
        source = "value = 2\nvalue += 3\nprint(value)\n"
        simulation = build_program_simulation_from_source(source)
        challenges = [step for step in simulation.steps if step.challenge]

        self.assertEqual(simulation.mode, "code")
        self.assertEqual(simulation.entry_name, "Program")
        self.assertEqual(simulation.output, "5\n")
        self.assertEqual(simulation.final_variables, {"value": 5})
        self.assertEqual(
            [(step.kind, step.expected) for step in challenges],
            [("program_start", "variable update"), ("arithmetic", 5), ("output", "5")],
        )
        self.assertNotIn("expected", simulation.public_dict()["steps"][0])
        self.assertNotIn("output", simulation.public_dict())

    def test_be_the_code_challenges_nested_conditions_and_executes_selected_path(self) -> None:
        source = (
            "value = 4\n"
            "if value > 2:\n"
            "    if value < 5:\n"
            "        print('inside')\n"
            "    else:\n"
            "        print('large')\n"
            "else:\n"
            "    print('small')\n"
        )
        simulation = build_program_simulation_from_source(source)
        conditions = [step for step in simulation.steps if step.kind == "condition"]
        outputs = [step for step in simulation.steps if step.kind == "output"]

        self.assertEqual([step.expected for step in conditions], [True, True])
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].expected, "inside")
        self.assertEqual(simulation.output, "inside\n")

    def test_be_the_code_runs_for_and_while_iterations_with_updated_state(self) -> None:
        source = (
            "total = 0\n"
            "for item in range(2):\n"
            "    total += item + 1\n"
            "while total < 4:\n"
            "    total += 1\n"
            "print(total)\n"
        )
        simulation = build_program_simulation_from_source(source)
        loop_values = [step.expected for step in simulation.steps if step.kind == "loop_value"]
        loop_conditions = [
            step.expected for step in simulation.steps if step.kind == "loop_condition"
        ]
        arithmetic = [step.expected for step in simulation.steps if step.kind == "arithmetic"]

        self.assertEqual(loop_values, [0, 1])
        self.assertEqual(loop_conditions, [False, True, False])
        self.assertEqual(arithmetic, [1, 3, 4])
        self.assertEqual(simulation.final_variables, {"total": 4, "item": 1})
        self.assertEqual(simulation.output, "4\n")

    def test_be_the_code_follows_project_function_calls_and_returns(self) -> None:
        source = (
            "factor = 3\n"
            "def add(value, increment=2):\n"
            "    return value + increment + factor\n"
            "result = add(3)\n"
            "print(result)\n"
        )
        simulation = build_program_simulation_from_source(source)
        kinds = [step.kind for step in simulation.steps]
        return_step = next(step for step in simulation.steps if step.kind == "return")

        self.assertIn("function_call", kinds)
        self.assertIn("enter", kinds)
        self.assertIn("call_return", kinds)
        self.assertEqual(return_step.expected, 8)
        self.assertEqual(simulation.output, "8\n")
        self.assertEqual(simulation.final_variables, {"factor": 3, "result": 8})

    def test_be_the_code_rejects_unsupported_syntax_and_enforces_loop_limit(self) -> None:
        with self.assertRaisesRegex(SimulationError, "Supported statements"):
            build_program_simulation_from_source("import os\nprint(os.name)\n")
        with self.assertRaisesRegex(SimulationError, "literal must be a JSON value"):
            build_program_simulation_from_source("if False:\n    value = 1j\n")
        with self.assertRaisesRegex(SimulationError, "40"):
            build_program_simulation_from_source(
                "for item in range(41):\n    value = item\n"
            )
        with self.assertRaisesRegex(SimulationError, "40 total loop iterations"):
            build_program_simulation_from_source("while True:\n    pass\n")
        statements = "\n".join(
            "value{} = {}".format(index, index) for index in range(130)
        )
        with self.assertRaisesRegex(SimulationError, "safe limit of 120 steps"):
            build_program_simulation_from_source(statements)

    def test_be_the_code_never_executes_unsupported_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed.txt"
            source = (
                f"open({str(marker)!r}, 'w').write('executed')\n"
            )
            with self.assertRaisesRegex(SimulationError, "cannot be resolved"):
                build_program_simulation_from_source(source)
            self.assertFalse(marker.exists())

    def test_be_the_code_rejects_unbound_local_global_name_behavior(self) -> None:
        source = "value = 7\ndef read_then_assign():\n    print(value)\n    value = 2\nread_then_assign()\n"
        with self.assertRaisesRegex(SimulationError, "Local name 'value'"):
            build_program_simulation_from_source(source)


class FunctionPOVIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @staticmethod
    def _finish_current_practice(page: FunctionPOVPage) -> None:
        while page.screens.currentWidget() is not page.completion_screen:
            step = page._current_step()
            if step is None:
                raise AssertionError("practice has no current step")
            if step.challenge and page._step_index not in page._passed:
                answer = page._simulation.answer(page._step_index)
                page._submit_answer(answer, page._format_value(answer))
            page._next_step()

    def test_practice_history_completion_and_return_preserve_analysis(self) -> None:
        source = "def add(value, amount=1):\n    return value + amount\n"
        window = MainWindow()
        self.addCleanup(window.close)
        i18n.set_language("en")
        window.results.set_result(analyze_python(source), "sample.py", "python")
        window.open_function_pov()
        page = window.function_pov_page
        self.assertTrue(window.results.function_pov_button.isEnabled())
        self.assertIs(window.stack.currentWidget(), page)
        self.assertEqual(page.function_list.count(), 1)
        page.code_mode_button.click()
        self.assertTrue(page.code_mode_button.isChecked())
        self.assertFalse(page.start_button.isEnabled())
        page.function_mode_button.click()
        self.assertTrue(page.function_mode_button.isChecked())

        page._parameter_fields["value"].setText("2")
        page.start_button.click()
        self.assertIs(page.screens.currentWidget(), page.practice_screen)
        self.assertEqual(page._current_step().kind, "enter")
        page.next_button.click()
        self.assertEqual(page._current_step().kind, "return")

        page.answer_edit.setText("2")
        page.check_button.click()
        self.assertEqual(page.history_list.count(), 1)
        self.assertNotIn(page._step_index, page._passed)
        self.assertFalse(page.next_button.isEnabled())

        page.answer_edit.setText("3")
        page.check_button.click()
        self.assertEqual(page.history_list.count(), 2)
        self.assertIn(page._step_index, page._passed)
        self.assertTrue(page.next_button.isEnabled())
        page.next_button.click()
        self.assertIs(page.screens.currentWidget(), page.completion_screen)
        self.assertIn("2", page.completion_summary.text())
        self.assertIn("1", page.completion_summary.text())

        page.similar_button.click()
        self.assertIs(page.screens.currentWidget(), page.exercise_screen)
        self.assertTrue(page.similar_logic_button.isEnabled())
        page.similar_logic_button.click()
        exercise = page._pending_exercise
        self.assertIsNotNone(exercise)
        self.assertIn("Logic change:", page.exercise_status.text())
        self.assertIn("amount=1", exercise.source)
        self.assertEqual(page.original_code_view.toPlainText(), source)
        self.assertIn('"value": 2', page.original_inputs_label.text())
        self.assertIn('"amount": 1', page.generated_inputs_label.text())
        self.assertEqual(window.results.analysis["source"], source)
        page.start_exercise_button.click()
        self.assertIs(page.screens.currentWidget(), page.practice_screen)
        self.assertIs(page._simulation, exercise.simulation)
        self.assertEqual(page._source, source)
        self.assertFalse(page._history)
        self.assertFalse(page._passed)
        self.assertEqual(page._step_index, 0)

        page.back_button.click()
        self.assertIs(window.stack.currentWidget(), window.results)
        self.assertEqual(window.results.analysis["source"], source)

    def test_analysis_page_opens_be_the_code_without_definitions(self) -> None:
        source = "value = 3\nprint(value)\n"
        window = MainWindow()
        self.addCleanup(window.close)
        window.results.set_result(analyze_python(source), "sample.py", "python")

        window.open_function_pov()
        page = window.function_pov_page

        self.assertIs(window.stack.currentWidget(), page)
        self.assertTrue(page.code_mode_button.isChecked())
        self.assertEqual(page.function_list.count(), 0)
        self.assertTrue(page.start_button.isEnabled())
        page.back_button.click()
        self.assertIs(window.stack.currentWidget(), window.results)
        self.assertEqual(window.results.analysis["source"], source)

    def test_function_pov_button_visibility_matches_all_six_languages(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        result = analyze_python("value = 1\nprint(value)\n")

        for language in (
            "python",
            "javascript",
            "typescript",
            "java",
            "cpp",
            "c",
        ):
            window.results.set_result(result, "sample.py", language)
            expected = language == "python"
            with self.subTest(language=language):
                self.assertEqual(
                    window.results.function_pov_button.isHidden(),
                    not expected,
                )
                self.assertEqual(
                    window.results.function_pov_button.isEnabled(),
                    expected,
                )
                self.assertEqual(window.results.tabs.count(), 5)

    def test_python_unsupported_syntax_keeps_clear_simulation_explanation(self) -> None:
        source = (
            "with open('not-executed.txt') as handle:\n"
            "    print(handle.read())\n"
        )
        window = MainWindow()
        self.addCleanup(window.close)
        i18n.set_language("en")
        window.results.set_result(analyze_python(source), "sample.py", "python")

        self.assertFalse(window.results.function_pov_button.isHidden())
        self.assertTrue(window.results.function_pov_button.isEnabled())
        window.open_function_pov()

        self.assertIn(
            "outside the safe simulation subset",
            window.function_pov_page.selection_message.text(),
        )
        self.assertFalse(window.function_pov_page.start_button.isEnabled())

    def test_non_python_results_explain_function_pov_support(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        i18n.set_language("en")
        result = analyze_javascript("function greet(name) { return name; }", "javascript")
        window.results.set_result(result, "sample.js", "javascript")
        self.assertTrue(window.results.function_pov_button.isHidden())
        self.assertFalse(window.results.function_pov_button.isEnabled())

        window.open_function_pov()

        self.assertEqual(window.function_pov_page.function_list.count(), 0)
        self.assertIn("JavaScript", window.function_pov_page.selection_message.text())

    def test_missing_and_advanced_functions_are_explained(self) -> None:
        page = FunctionPOVPage()
        self.addCleanup(page.close)
        page.set_source("print('no function')\n", "sample.py")
        self.assertEqual(page.function_list.count(), 0)
        self.assertTrue(page.code_mode_button.isChecked())
        self.assertTrue(page.start_button.isEnabled())

        page.set_source("def collect(*values):\n    return values\n", "sample.py")
        self.assertEqual(page.function_list.count(), 1)
        self.assertFalse(page.start_button.isEnabled())
        self.assertTrue(page.support_note.text())

    def test_long_function_arguments_are_rejected_with_recoverable_feedback(self) -> None:
        i18n.set_language("en")
        page = FunctionPOVPage()
        self.addCleanup(page.close)
        page.set_source(
            "def identity(value):\n"
            "    return value\n",
            "sample.py",
        )
        field = page._parameter_fields["value"]

        field.setText("9" * 5000)
        page.start_button.click()
        self.assertIn("too large", page.selection_error.text().lower())
        self.assertIs(page.screens.currentWidget(), page.selection_screen)

        field.setText("9" * (MAX_JSON_INPUT_CHARS + 20))
        self.assertEqual(len(field.text()), MAX_JSON_INPUT_CHARS + 1)
        page.start_button.click()
        self.assertIn("maximum", page.selection_error.text().lower())
        self.assertIs(page.screens.currentWidget(), page.selection_screen)

    def test_long_numeric_answers_are_rejected_without_recording_attempts(self) -> None:
        i18n.set_language("en")
        page = FunctionPOVPage()
        self.addCleanup(page.close)
        page.set_source("def identity(value):\n    return value\n", "sample.py")
        page._parameter_fields["value"].setText("1")
        page.start_button.click()
        page.next_button.click()

        page.answer_edit.setText("9" * 5000)
        page.check_button.click()
        self.assertIn("too large", page.feedback_label.text().lower())
        self.assertEqual(page.history_list.count(), 0)
        self.assertNotIn(page._step_index, page._passed)

        page.answer_edit.setText("9" * (MAX_JSON_INPUT_CHARS + 20))
        self.assertEqual(len(page.answer_edit.text()), MAX_JSON_INPUT_CHARS + 1)
        page.check_button.click()
        self.assertIn("maximum", page.feedback_label.text().lower())
        self.assertEqual(page.history_list.count(), 0)

        i18n.set_language("zh")
        page.answer_edit.setText("9" * (MAX_JSON_INPUT_CHARS + 20))
        page.check_button.click()
        self.assertIn("输入过长", page.feedback_label.text())
        self.assertIn(str(MAX_JSON_INPUT_CHARS), page.feedback_label.text())

    def test_unsupported_function_error_is_understandable_in_chinese(self) -> None:
        i18n.set_language("zh")
        page = FunctionPOVPage()
        self.addCleanup(page.close)
        page.set_source(
            "def unsupported():\n"
            "    with open('sample.txt') as handle:\n"
            "        return handle.read()\n",
            "sample.py",
        )

        page.start_button.click()

        message = page.selection_error.text()
        self.assertIn("安全模拟范围", message)
        self.assertIn("第 2 行", message)
        self.assertNotIn("Supported statements", message)

    def test_be_the_code_ui_retries_answers_and_completes(self) -> None:
        i18n.set_language("en")
        page = FunctionPOVPage()
        self.addCleanup(page.close)
        page.set_source(
            "value = 2\nif value > 1:\n    print('ready')\n",
            "sample.py",
        )

        page.start_button.click()
        self.assertEqual(page._current_step().kind, "program_start")
        page.choice_layout.itemAt(0).widget().click()
        page.next_button.click()
        self.assertEqual(page._current_step().kind, "assignment")
        page.next_button.click()
        self.assertEqual(page._current_step().kind, "condition")
        page.choice_layout.itemAt(0).widget().click()
        page.next_button.click()
        self.assertEqual(page._current_step().kind, "output")

        page.answer_edit.setText('"wrong"')
        page.check_button.click()
        self.assertIn("Not quite", page.feedback_label.text())
        self.assertNotIn(page._step_index, page._passed)
        page.answer_edit.setText('"ready"')
        page.check_button.click()
        self.assertIn("Correct", page.feedback_label.text())
        self.assertIn(page._step_index, page._passed)
        self.assertEqual(page.history_list.count(), 2)
        page.next_button.click()
        page.next_button.click()
        self.assertIs(page.screens.currentWidget(), page.completion_screen)
        self.assertIn("ready", page.completion_summary.text())

    def test_be_the_code_new_values_preserves_original_and_gives_feedback(self) -> None:
        i18n.set_language("en")
        source = "value = 1\nprint(value)\n"
        window = MainWindow()
        self.addCleanup(window.close)
        window.results.set_result(analyze_python(source), "sample.py", "python")
        window.open_function_pov()
        page = window.function_pov_page
        page.start_button.click()
        self._finish_current_practice(page)

        page.similar_button.click()
        page.new_values_button.click()
        exercise = page._pending_exercise
        self.assertIsNotNone(exercise)
        self.assertNotEqual(exercise.source, source)
        self.assertEqual(page.original_code_view.toPlainText(), source)
        self.assertEqual(window.results.analysis["source"], source)
        page.start_exercise_button.click()
        self.assertIs(page._simulation, exercise.simulation)
        self.assertFalse(page._history)
        self.assertFalse(page._passed)
        self.assertEqual(page._step_index, 0)

        while page._current_step().kind != "output":
            step = page._current_step()
            if step.challenge:
                page._submit_answer(
                    page._simulation.answer(page._step_index),
                    page._format_value(page._simulation.answer(page._step_index)),
                )
            page._next_step()
        page._submit_answer("incorrect", '"incorrect"')
        self.assertIn(
            i18n.tr(
                "Not quite. Evaluate each print argument in order, convert the values "
                "to text, and join them with spaces."
            ),
            page.feedback_label.text(),
        )
        self.assertEqual(page.history_list.count(), 1)
        self.assertNotIn(page._step_index, page._passed)

        i18n.set_language("zh")
        page.retranslate()
        self.assertEqual(page.back_button.text(), "← 返回分析结果")
        self.assertEqual(page.similar_button.text(), "练习类似题目")
        i18n.set_language("en")
        page.retranslate()

    def test_unsupported_similar_logic_is_explained_in_the_ui(self) -> None:
        i18n.set_language("en")
        source = "value = 1\nprint(value)\n"
        page = FunctionPOVPage()
        self.addCleanup(page.close)
        page.set_source(source, "sample.py")
        page.start_button.click()
        self._finish_current_practice(page)

        page.similar_button.click()

        self.assertIsNone(page._pending_exercise)
        self.assertFalse(page.start_exercise_button.isEnabled())
        self.assertFalse(page.similar_logic_button.isEnabled())
        self.assertIn(
            "This code does not match a supported Similar Logic pattern.",
            page.exercise_status.text(),
        )


if __name__ == "__main__":
    unittest.main()
