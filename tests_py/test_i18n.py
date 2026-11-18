"""Tests for the interface-string layer.

The important one is the coverage test: it walks the UI modules' source, collects
every literal passed to ``tr``, and fails when a string has no translation. That
is what keeps the Chinese table from silently drifting as the UI grows.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from python_app import i18n  # noqa: E402

UI_MODULES = ["native_app.py", "compare.py"]
APP_DIR = Path(__file__).resolve().parent.parent / "python_app"


def literal_keys(path: Path) -> set[str]:
    """Every constant string passed to tr(...) in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "tr":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.add(argument.value)
    return found


class TranslationTableTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("en")

    def test_english_is_the_identity(self) -> None:
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Compare versions"), "Compare versions")

    def test_chinese_lookup(self) -> None:
        i18n.set_language("zh")
        self.assertEqual(i18n.tr("Compare versions"), "对比版本")
        self.assertEqual(i18n.tr("Added"), "新增")

    def test_unknown_language_falls_back_to_english(self) -> None:
        i18n.set_language("fr")
        self.assertEqual(i18n.language(), "en")
        self.assertEqual(i18n.tr("Added"), "Added")

    def test_missing_key_returns_the_source_string(self) -> None:
        i18n.set_language("zh")
        self.assertEqual(i18n.tr("Never translated"), "Never translated")

    def test_fields_are_applied_after_lookup(self) -> None:
        i18n.set_language("zh")
        self.assertEqual(i18n.tr("Added"), "新增")
        self.assertIn("BOOM", i18n.tr("Could not compare: {error}", error="BOOM"))

    def test_missing_field_does_not_raise(self) -> None:
        i18n.set_language("zh")
        self.assertEqual(i18n.tr("Could not compare: {error}"), "无法对比：{error}")

    def test_every_used_string_is_translated(self) -> None:
        used: set[str] = set()
        for module in UI_MODULES:
            used |= literal_keys(APP_DIR / module)
        self.assertTrue(used, "no tr() literals found - did the scan break?")
        missing = sorted(i18n.untranslated(used))
        self.assertEqual(missing, [], f"untranslated interface strings: {missing}")


if __name__ == "__main__":
    unittest.main()
