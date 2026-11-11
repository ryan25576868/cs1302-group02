import tempfile
import unittest
from pathlib import Path

from function_pov import analyze_project, build_function_graph


class BuildFunctionGraphTests(unittest.TestCase):
    def test_builds_nodes_edges_and_json_compatible_data(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "sample.py").write_text(
                "def first():\n"
                "    second()\n"
                "def second():\n"
                "    return 1\n",
                encoding="utf-8",
            )

            graph = build_function_graph(analyze_project(str(root)))

            self.assertEqual(
                [(node.id, node.label) for node in graph.nodes],
                [("sample.first", "first"), ("sample.second", "second")],
            )
            self.assertEqual(
                [(edge.source, edge.target) for edge in graph.edges],
                [("sample.first", "sample.second")],
            )
            self.assertEqual(graph.to_dict()["edges"][0]["line"], 2)


if __name__ == "__main__":
    unittest.main()
