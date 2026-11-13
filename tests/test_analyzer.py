import tempfile
import unittest
from pathlib import Path

from function_pov import analyze_project
from function_pov.analyzer import analyze_source


class AnalyzeProjectTests(unittest.TestCase):
    def test_analyzes_virtual_source_and_extracts_docstrings_without_writing_files(self):
        source = (
            '"""Temporary source is only parsed."""\n'
            "def double(value: int):\n"
            '    """Return twice the value."""\n'
            "    return value * 2\n"
            "\n"
            "def total(value=3):\n"
            "    return double(value) + 1\n"
        )

        result = analyze_source(source)

        self.assertEqual(result.root, "<memory>")
        self.assertEqual(
            [function.id for function in result.functions],
            ["pasted.double", "pasted.total"],
        )
        self.assertEqual(result.functions[0].docstring, "Return twice the value.")
        self.assertEqual(
            [(call.caller, call.callee) for call in result.calls],
            [("pasted.total", "pasted.double")],
        )
        self.assertFalse(Path("pasted.py").exists())

    def test_virtual_source_reports_syntax_errors_and_no_function_input(self):
        invalid = analyze_source("def broken(:\n    pass\n")
        empty = analyze_source("answer = 42\n")

        self.assertEqual(invalid.functions, ())
        self.assertEqual(invalid.diagnostics[0].severity, "error")
        self.assertEqual(invalid.diagnostics[0].line, 1)
        self.assertEqual(empty.functions, ())
        self.assertEqual(empty.calls, ())

    def test_extracts_functions_parameters_returns_and_imported_calls(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text(
                "from helpers import double as twice\n"
                "def start(value: int, /, step=2, *items, flag=False, **options):\n"
                "    result = twice(value)\n"
                "    return result + step\n",
                encoding="utf-8",
            )
            (root / "helpers.py").write_text(
                "def double(value):\n"
                "    return value * 2\n",
                encoding="utf-8",
            )

            result = analyze_project(str(root))

            self.assertEqual(
                [function.id for function in result.functions],
                ["helpers.double", "main.start"],
            )
            start = next(function for function in result.functions if function.name == "start")
            self.assertEqual(
                [(item.name, item.kind, item.default, item.annotation) for item in start.parameters],
                [
                    ("value", "positional_only", None, "int"),
                    ("step", "positional_or_keyword", "2", None),
                    ("items", "var_positional", None, None),
                    ("flag", "keyword_only", "False", None),
                    ("options", "var_keyword", None, None),
                ],
            )
            self.assertEqual(start.return_expressions, ("result + step",))
            self.assertEqual(
                [(call.caller, call.callee, call.expression) for call in result.calls],
                [("main.start", "helpers.double", "twice")],
            )

    def test_does_not_scan_excluded_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "app.py").write_text("def entry():\n    return 1\n", encoding="utf-8")
            excluded = root / ".venv"
            excluded.mkdir()
            (excluded / "ignored.py").write_text(
                "def hidden():\n    return 2\n",
                encoding="utf-8",
            )

            result = analyze_project(str(root))

            self.assertEqual([function.id for function in result.functions], ["app.entry"])

    def test_resolves_package_module_calls_and_ignores_unknown_methods(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "main.py").write_text(
                "import pkg.helpers\n"
                "from .helpers import double as twice\n"
                "def run(value):\n"
                "    obj.unknown()\n"
                "    return pkg.helpers.double(twice(value))\n",
                encoding="utf-8",
            )
            (package / "helpers.py").write_text(
                "def double(value):\n"
                "    return value * 2\n",
                encoding="utf-8",
            )

            result = analyze_project(str(root))

            self.assertEqual(
                [(call.caller, call.callee) for call in result.calls],
                [
                    ("pkg.main.run", "pkg.helpers.double"),
                    ("pkg.main.run", "pkg.helpers.double"),
                ],
            )

    def test_reports_syntax_errors_and_unsupported_definitions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
            (root / "other.py").write_text(
                "class Example:\n"
                "    def method(self):\n"
                "        return 1\n"
                "async def later():\n"
                "    return 2\n",
                encoding="utf-8",
            )

            result = analyze_project(str(root))

            self.assertEqual(result.functions, ())
            self.assertEqual(
                [(item.file, item.severity) for item in result.diagnostics],
                [("bad.py", "error"), ("other.py", "warning"), ("other.py", "warning")],
            )

    def test_rejects_non_python_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "notes.txt"
            path.write_text("not Python", encoding="utf-8")

            with self.assertRaises(ValueError):
                analyze_project(str(path))


if __name__ == "__main__":
    unittest.main()
