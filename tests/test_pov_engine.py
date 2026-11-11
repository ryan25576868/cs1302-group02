import tempfile
import unittest
from pathlib import Path

from function_pov.pov.engine import SimulationError, build_simulation


class PovEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write(self, source):
        (self.root / "main.py").write_text(source, encoding="utf-8")

    def test_binds_user_arguments_and_default_values(self):
        self.write(
            "def greet(name, suffix='!'):\n"
            "    return name + suffix\n"
        )
        simulation = build_simulation(str(self.root), "main.greet", {"name": "Ada"})

        entry = simulation.steps[0]
        self.assertEqual(entry.kind, "enter")
        self.assertEqual(entry.variables, {"name": "Ada", "suffix": "!"})
        self.assertEqual(simulation.steps[-1].expected, "Ada!")

    def test_arithmetic_answers_hints_and_show_answer(self):
        self.write(
            "def square(x):\n"
            "    result = x ** 2\n"
            "    return result\n"
        )
        simulation = build_simulation(str(self.root), "main.square", {"x": 4})
        arithmetic_index = next(
            index for index, step in enumerate(simulation.steps)
            if step.kind == "arithmetic"
        )

        self.assertEqual(simulation.steps[arithmetic_index].expected, 16)
        self.assertFalse(simulation.check(arithmetic_index, 15)["correct"])
        self.assertTrue(simulation.check(arithmetic_index, 16)["correct"])
        self.assertIn("operator order", simulation.hint(arithmetic_index))
        self.assertEqual(simulation.answer(arithmetic_index), 16)
        self.assertNotIn("expected", simulation.public_dict()["steps"][arithmetic_index])

    def test_follows_true_and_false_conditional_branches(self):
        self.write(
            "def classify(value):\n"
            "    if value > 0:\n"
            "        return 1\n"
            "    else:\n"
            "        return -1\n"
        )
        positive = build_simulation(str(self.root), "main.classify", {"value": 2})
        negative = build_simulation(str(self.root), "main.classify", {"value": -2})

        positive_condition = next(step for step in positive.steps if step.kind == "condition")
        negative_condition = next(step for step in negative.steps if step.kind == "condition")
        self.assertIs(positive_condition.expected, True)
        self.assertIs(negative_condition.expected, False)
        self.assertEqual(positive.steps[-1].expected, 1)
        self.assertEqual(negative.steps[-1].expected, -1)

    def test_boolean_conditions_preserve_short_circuit_behavior(self):
        self.write(
            "def is_ready(value):\n"
            "    if value != 0 and 1 / value > 0:\n"
            "        return True\n"
            "    else:\n"
            "        return False\n"
        )
        simulation = build_simulation(str(self.root), "main.is_ready", {"value": 0})

        condition = next(step for step in simulation.steps if step.kind == "condition")
        self.assertIs(condition.expected, False)
        self.assertIs(simulation.steps[-1].expected, False)

    def test_calls_function_and_returns_value_to_caller(self):
        self.write(
            "def square(x):\n"
            "    return x ** 2\n"
            "\n"
            "def start(value):\n"
            "    result = square(value)\n"
            "    return result + 1\n"
        )
        simulation = build_simulation(str(self.root), "main.start", {"value": 4})
        steps = simulation.steps
        call_index = next(index for index, step in enumerate(steps) if step.kind == "function_call")
        child_entry = steps[call_index + 1]
        child_return = steps[call_index + 2]
        return_token = steps[call_index + 3]

        self.assertEqual(steps[call_index].expected, "square")
        self.assertEqual(child_entry.function_name, "square")
        self.assertEqual(child_entry.variables, {"x": 4})
        self.assertEqual(len(child_entry.stack), 2)
        self.assertEqual(child_return.kind, "return")
        self.assertEqual(return_token.kind, "call_return")
        self.assertEqual(return_token.expression, "square(value) → 16")
        self.assertEqual(steps[-1].expected, 17)

    def test_simulates_cross_file_imports_in_basic_project(self):
        project = Path(__file__).resolve().parents[1] / "examples" / "basic_project"
        simulation = build_simulation(
            str(project),
            "main.calculate",
            {"value": 21},
        )

        call = next(step for step in simulation.steps if step.kind == "function_call")
        helper_entry = simulation.steps[simulation.steps.index(call) + 1]
        helper_return = next(
            step for step in simulation.steps
            if step.function_id == "helpers.format_result" and step.kind == "return"
        )
        caller_return = next(
            step for step in reversed(simulation.steps)
            if step.function_id == "main.calculate" and step.kind == "return"
        )

        self.assertEqual(call.expected, "format_result")
        self.assertEqual(call.target, "helpers.format_result")
        self.assertEqual(helper_entry.variables, {"value": 42})
        self.assertEqual(helper_return.expected, "Result: 42")
        self.assertEqual(caller_return.expected, "Result: 42")

    def test_resolves_imported_module_aliases_in_a_temporary_project(self):
        (self.root / "helpers.py").write_text(
            "def format_result(value):\n"
            "    return 'value={}'.format(value)\n",
            encoding="utf-8",
        )
        self.write(
            "import helpers as formatting\n"
            "def calculate(value):\n"
            "    return formatting.format_result(value)\n"
        )
        simulation = build_simulation(str(self.root), "main.calculate", {"value": 7})

        call = next(step for step in simulation.steps if step.kind == "function_call")
        self.assertEqual(call.target, "helpers.format_result")
        self.assertEqual(simulation.steps[-1].expected, "value=7")

    def test_string_format_rejects_attribute_field_access(self):
        self.write(
            "def describe(value):\n"
            "    return '{value.__class__}'.format(value=value)\n"
        )

        with self.assertRaisesRegex(SimulationError, "attribute or index access"):
            build_simulation(str(self.root), "main.describe", {"value": "safe"})

    def test_rejects_unsupported_syntax_without_running_it(self):
        marker = self.root / "must-not-exist"
        self.write(
            "def unsafe():\n"
            "    open({!r}, 'w').write('ran')\n"
            "    return 1\n".format(str(marker))
        )

        with self.assertRaisesRegex(SimulationError, "safe POV subset|project function"):
            build_simulation(str(self.root), "main.unsafe", {})
        self.assertFalse(marker.exists())

    def test_rejects_loops_and_missing_required_parameters(self):
        self.write(
            "def repeat(value):\n"
            "    while value:\n"
            "        value = value - 1\n"
            "    return value\n"
        )
        with self.assertRaisesRegex(SimulationError, "Supported statements"):
            build_simulation(str(self.root), "main.repeat", {"value": 3})

        self.write("def needs(value):\n    return value\n")
        with self.assertRaisesRegex(SimulationError, "required parameter"):
            build_simulation(str(self.root), "main.needs", {})

    def test_limits_recursive_calls(self):
        self.write(
            "def again(value):\n"
            "    return again(value)\n"
        )
        with self.assertRaisesRegex(SimulationError, "Call depth"):
            build_simulation(str(self.root), "main.again", {"value": 1})


if __name__ == "__main__":
    unittest.main()
