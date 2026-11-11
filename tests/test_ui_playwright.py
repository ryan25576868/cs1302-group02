import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path

from function_pov.server import create_server


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "Install the test extra to run browser tests.")
class FunctionGraphBrowserTests(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        (self.project / "main.py").write_text(
            "def start(value: int = 4):\n"
            "    return multiply(value)\n"
            "\n"
            "def multiply(value):\n"
            "    return value * 2\n"
            "\n"
            "def unused():\n"
            "    return 0\n",
            encoding="utf-8",
        )
        self.server = create_server()
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.playwright_context = sync_playwright()
        self.playwright = self.playwright_context.start()
        self.browser = self.playwright.chromium.launch()
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 960})
        self.page.goto("http://127.0.0.1:{}".format(self.server.server_port))
        self.page.locator("#folder-input").set_input_files(str(self.project))
        self.page.locator(".node-group").first.wait_for()
        self.page.get_by_text("3 functions · 1 connections").wait_for()

    def tearDown(self):
        if hasattr(self, "browser"):
            self.browser.close()
        if hasattr(self, "playwright"):
            self.playwright.stop()
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.server_thread.join(timeout=2)
        if hasattr(self, "temporary_directory"):
            self.temporary_directory.cleanup()

    def test_mouse_click_selects_node_and_drag_pan_zoom_remain_independent(self):
        start_node = self.page.locator('[data-id$=".main.start"]')
        node_box = start_node.bounding_box()
        self.page.mouse.click(
            node_box["x"] + node_box["width"] / 2,
            node_box["y"] + node_box["height"] / 2,
        )

        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")
        self.assertIn("def start(value: int = 4):", self.page.locator("#source-code").inner_text())
        self.assertIn("value", self.page.locator("#parameter-list").inner_text())
        self.assertIn("is-selected", start_node.get_attribute("class"))

        multiply_node = self.page.locator('[data-id$=".main.multiply"]')
        before_drag = multiply_node.get_attribute("transform")
        node_box = multiply_node.bounding_box()
        start_x = node_box["x"] + node_box["width"] / 2
        start_y = node_box["y"] + node_box["height"] / 2
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(start_x + 36, start_y + 24, steps=4)
        self.page.mouse.up()

        self.assertNotEqual(multiply_node.get_attribute("transform"), before_drag)
        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")

        graph = self.page.locator("#function-graph")
        graph_box = graph.bounding_box()
        before_pan = self.page.locator("#graph-content").get_attribute("transform")
        self.page.mouse.move(graph_box["x"] + 12, graph_box["y"] + 12)
        self.page.mouse.down()
        self.page.mouse.move(graph_box["x"] + 62, graph_box["y"] + 48, steps=4)
        self.page.mouse.up()
        self.assertNotEqual(self.page.locator("#graph-content").get_attribute("transform"), before_pan)
        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")

        self.page.get_by_role("button", name="Zoom in").click()
        self.assertEqual(self.page.locator("#zoom-label").inner_text(), "120%")
        self.page.get_by_role("button", name="Zoom out").click()
        self.assertEqual(self.page.locator("#zoom-label").inner_text(), "100%")
        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")

        self.page.mouse.move(graph_box["x"] + 15, graph_box["y"] + 15)
        self.page.mouse.wheel(0, -500)
        self.assertEqual(self.page.locator("#zoom-label").inner_text(), "110%")

        self.page.get_by_role("button", name="Reset view").click()
        self.assertEqual(self.page.locator("#graph-content").get_attribute("transform"), "translate(0 0) scale(1)")
        self.assertEqual(self.page.locator("#zoom-label").inner_text(), "100%")
        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")


if __name__ == "__main__":
    unittest.main()
