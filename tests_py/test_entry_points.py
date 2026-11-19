from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


class EntryPointTests(unittest.TestCase):
    def test_native_and_desktop_commands_use_the_native_launcher(self) -> None:
        project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
        scripts = project["project"]["scripts"]

        self.assertIn("prism-native", scripts)
        self.assertIn("prism-desktop", scripts)
        self.assertEqual(scripts["prism-native"], "python_app.launch_native:main")
        self.assertEqual(scripts["prism-desktop"], scripts["prism-native"])


if __name__ == "__main__":
    unittest.main()
