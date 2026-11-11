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
            "    result = multiply(value)\n"
            "    if result > 5:\n"
            "        return result + 1\n"
            "    else:\n"
            "        return 0\n"
            "\n"
            "def multiply(value):\n"
            "    doubled = value * 2\n"
            "    return doubled\n"
            "\n"
            "def unused():\n"
            "    return 0\n"
            "def classify(value):\n"
            "    if value > 0:\n"
            "        return 1\n"
            "    else:\n"
            "        return -1\n",
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
        self.page.get_by_text("4 functions · 1 connections").wait_for()

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
        start_node = self.page.locator('[data-id$=".start"]')
        node_box = start_node.bounding_box()
        self.page.mouse.click(
            node_box["x"] + node_box["width"] / 2,
            node_box["y"] + node_box["height"] / 2,
        )

        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")
        self.assertIn("def start(value: int = 4):", self.page.locator("#source-code").inner_text())
        self.assertIn("value", self.page.locator("#parameter-list").inner_text())
        self.assertIn("is-selected", start_node.get_attribute("class"))

        multiply_node = self.page.locator('[data-id$=".multiply"]')
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

    def enter_function(self, name, arguments):
        self.page.locator('[data-id$=".' + name + '"]').click()
        self.page.locator("#enter-pov").click()
        for key, value in arguments.items():
            self.page.locator("#pov-arg-" + key).fill(value)
        self.page.get_by_role("button", name="Enter POV").last.click()
        self.page.locator(
            "#pov-overlay:not([hidden]), #launch-error:not([hidden])"
        ).wait_for()
        if self.page.locator("#pov-overlay").is_hidden():
            self.fail(self.page.locator("#launch-error").inner_text())

    def test_pov_call_arithmetic_feedback_hint_answer_return_restart_and_back(self):
        self.enter_function("start", {"value": "4"})
        self.assertIn("start()", self.page.locator("#pov-progress-function").inner_text())
        self.assertIn("value =", self.page.locator("#pov-argument-tokens").inner_text())
        self.assertIn("4", self.page.locator("#pov-argument-tokens").inner_text())
        self.assertIn("start()", self.page.locator("#pov-stack").inner_text())

        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "FUNCTION CALL")
        self.page.locator(".pov-choice-row .pov-choice", has_text="multiply").click()
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-local-function").inner_text(), "multiply()")
        self.assertEqual(self.page.locator("#pov-stack .stack-frame").count(), 2)
        self.page.get_by_role("button", name="Previous").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "FUNCTION CALL")
        self.page.get_by_role("button", name="Next").click()

        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "SOLVE THE EXPRESSION")
        self.page.locator("#pov-answer-input").fill("7")
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_text("Not quite. Check the current values and try again.").wait_for()
        self.assertIn("Not quite", self.page.locator("#pov-feedback").inner_text())
        self.assertTrue(self.page.get_by_role("button", name="Next").is_disabled())
        self.page.get_by_role("button", name="Hint").click()
        self.page.get_by_text("Substitute the local values into the expression, then follow the operator order.").wait_for()
        self.assertIn("operator order", self.page.locator("#pov-feedback").inner_text())
        self.page.locator("#pov-answer-input").fill("8")
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_text("That's right! Your function can continue.").wait_for()
        self.assertIn("That's right", self.page.locator("#pov-feedback").inner_text())
        self.assertIn("Returned 8", self.page.locator("#pov-argument-tokens").inner_text())

        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "RETURN TO CALLER")
        self.page.get_by_role("button", name="Show answer").click()
        self.page.get_by_text("Returned 8", exact=False).wait_for()
        self.assertIn("Returned 8", self.page.locator("#pov-argument-tokens").inner_text())
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "BACK FROM A FUNCTION")
        self.page.get_by_role("button", name="Next").click()
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "CHOOSE A BRANCH")
        self.assertIn("result", self.page.locator("#pov-locals").inner_text())
        self.page.locator(".pov-choice", has_text="True").click()
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "RETURN TO CALLER")
        self.page.get_by_role("button", name="Show answer").click()
        self.page.get_by_text("Returned 9", exact=False).wait_for()
        self.page.get_by_role("button", name="Finish").click()
        self.assertIn("FUNCTION COMPLETE", self.page.locator("#pov-progress-label").inner_text())
        self.page.get_by_role("button", name="Restart").last.click()
        self.assertEqual(self.page.locator("#pov-progress-label").inner_text().split()[1], "1")
        self.page.get_by_role("button", name="Back to map").click()
        self.assertTrue(self.page.locator("#pov-overlay").is_hidden())
        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")

    def test_pov_runs_basic_project_import_and_returns_formatted_value(self):
        project = Path(__file__).resolve().parents[1] / "examples" / "basic_project"
        self.page.locator("#folder-input").set_input_files(str(project))
        calculate_node = self.page.locator('[data-id$=".calculate"]')
        calculate_node.wait_for()
        self.page.locator('[data-id$=".format_result"]').wait_for()
        self.assertEqual(calculate_node.get_attribute("data-id"), "main.calculate")
        self.enter_function("calculate", {"value": "21"})

        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "SOLVE THE EXPRESSION")
        self.page.locator("#pov-answer-input").fill("42")
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_text("That's right! Your function can continue.").wait_for()
        self.page.get_by_role("button", name="Next").click()

        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "FUNCTION CALL")
        self.page.get_by_role("button", name="format_result", exact=True).click()
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-local-function").inner_text(), "format_result()")
        self.assertEqual(self.page.locator("#pov-stack .stack-frame").count(), 2)

        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "RETURN TO CALLER")
        self.page.locator("#pov-answer-input").fill('"Result: 42"')
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_text("That's right! Your function can continue.").wait_for()
        self.page.get_by_role("button", name="Next").click()

        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "BACK FROM A FUNCTION")
        self.assertIn("Result: 42", self.page.locator("#pov-expression").inner_text())
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "RETURN TO CALLER")
        self.page.locator("#pov-answer-input").fill('"Result: 42"')
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_role("button", name="Finish").click()
        self.page.get_by_text("You did it. Function returned!").wait_for()
        self.page.get_by_role("button", name="Back to map").click()
        self.assertTrue(self.page.locator("#pov-overlay").is_hidden())

    def test_pov_takes_false_conditional_branch_and_return(self):
        self.enter_function("classify", {"value": "-2"})
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "CHOOSE A BRANCH")
        self.assertIn("value > 0", self.page.locator(".pov-source-line.is-active").inner_text())
        self.page.locator(".pov-choice", has_text="False").click()
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-expression").inner_text(), "-1")
        self.page.get_by_role("button", name="Show answer").click()
        self.page.get_by_text("Returned -1", exact=False).wait_for()
        self.assertIn("Returned -1", self.page.locator("#pov-argument-tokens").inner_text())

    def test_pov_explains_unsupported_syntax(self):
        source = "def loop(value):\n    while value:\n        value = value - 1\n    return value\n"
        (self.project / "main.py").write_text(source, encoding="utf-8")
        self.page.locator("#folder-input").set_input_files(str(self.project))
        self.page.locator('[data-id$=".loop"]').click()
        self.page.locator("#enter-pov").click()
        self.page.locator("#pov-arg-value").fill("1")
        self.page.get_by_role("button", name="Enter POV").click()
        self.page.get_by_text("Supported statements are local assignments, if/else, direct function calls, and return.", exact=False).wait_for()
        self.assertIn("Supported statements", self.page.locator("#launch-error").inner_text())

    def test_pov_layout_supports_small_screens_and_reduced_motion(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.emulate_media(reduced_motion="reduce")
        self.enter_function("classify", {"value": "1"})

        overlay = self.page.locator("#pov-overlay")
        self.assertEqual(overlay.bounding_box()["width"], 390)
        self.assertLessEqual(
            self.page.locator(".pov-controls").evaluate("(element) => element.scrollWidth"),
            self.page.locator(".pov-controls").evaluate("(element) => element.clientWidth") + 1,
        )
        self.assertLessEqual(
            overlay.evaluate(
                "(element) => {"
                " const duration = getComputedStyle(element).animationDuration;"
                " return duration.endsWith('ms')"
                "   ? parseFloat(duration)"
                "   : parseFloat(duration) * 1000;"
                "}"
            ),
            0.01,
        )


if __name__ == "__main__":
    unittest.main()
