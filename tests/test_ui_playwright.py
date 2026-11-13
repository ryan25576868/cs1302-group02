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

    def test_paste_code_maps_functions_explains_them_and_enters_pov(self):
        self.page.get_by_role("button", name="Paste code").first.click()
        self.assertTrue(self.page.locator("#paste-modal").is_visible())
        self.page.locator("#paste-source").fill("temporary text")
        self.page.get_by_role("button", name="Clear").click()
        self.assertEqual(self.page.locator("#paste-source").input_value(), "")
        self.page.get_by_role("button", name="Cancel").click()
        self.assertTrue(self.page.locator("#paste-modal").is_hidden())

        self.page.get_by_role("button", name="Paste code").first.click()
        self.page.locator("#paste-source").fill(
            "def double(value: int):\n"
            '    """Return twice the value."""\n'
            "    return value * 2\n"
            "\n"
            "def total(value=3):\n"
            "    return double(value) + 1\n"
        )
        self.page.get_by_role("button", name="Generate map").click()
        self.page.locator('[data-id="pasted.total"]').wait_for()
        self.assertEqual(self.page.locator(".node-group").count(), 2)
        self.assertIn("single file", self.page.locator("#project-label").inner_text())
        self.assertIn("imports may not resolve", self.page.locator("#project-label").inner_text())

        self.page.locator('[data-id="pasted.total"]').click()
        explanation = self.page.locator("#function-explanation").inner_text()
        self.assertIn("optional; default: 3", explanation)
        self.assertIn("Calls double", explanation)
        self.assertIn("runtime results have not been executed", explanation)
        self.assertIn("imports from other project files may not resolve", explanation)

        self.page.locator("#enter-pov").click()
        self.page.get_by_role("button", name="Enter POV").last.click()
        self.page.locator("#pov-overlay:not([hidden])").wait_for()
        self.assertEqual(self.page.locator("#pov-code-file").inner_text(), "pasted.py")
        self.assertIn("def total(value=3):", self.page.locator("#pov-source").inner_text())

    def test_paste_code_shows_friendly_syntax_and_no_function_messages(self):
        self.page.get_by_role("button", name="Paste code").first.click()
        self.page.locator("#paste-source").fill("def broken(:\n    pass\n")
        self.page.get_by_role("button", name="Generate map").click()
        self.page.locator("#paste-error:not([hidden])").wait_for()
        self.assertIn("Python syntax error on line 1", self.page.locator("#paste-error").inner_text())
        self.assertTrue(self.page.locator("#paste-modal").is_visible())

        self.page.get_by_role("button", name="Clear").click()
        self.page.locator("#paste-source").fill("answer = 42\n")
        self.page.get_by_role("button", name="Generate map").click()
        self.page.locator("#paste-modal[hidden]").wait_for(state="hidden")
        self.page.get_by_text("0 functions · 0 connections").wait_for()
        self.assertEqual(self.page.locator(".node-group").count(), 0)
        self.assertEqual(self.page.locator("#graph-empty .empty-title").inner_text(), "No functions found")
        self.assertIn("no top-level function definitions", self.page.locator("#graph-empty").inner_text())

    def test_paste_code_explains_that_a_stale_server_must_be_restarted(self):
        def not_found(route):
            route.fulfill(
                status=404,
                content_type="application/json",
                body='{"error":"Not found"}',
            )

        self.page.route("**/api/analyze-source", not_found)
        self.page.get_by_role("button", name="Paste code").first.click()
        self.page.locator("#paste-source").fill("def add(a, b):\n    return a + b\n")
        self.page.get_by_role("button", name="Generate map").click()
        self.page.locator("#paste-error:not([hidden])").wait_for()

        self.assertIn("server is out of date", self.page.locator("#paste-error").inner_text())
        self.assertIn("Restart it, then reload", self.page.locator("#paste-error").inner_text())

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
        self.page.get_by_role("button", name="Back to map").last.click()
        self.assertTrue(self.page.locator("#pov-overlay").is_hidden())
        self.assertEqual(self.page.locator("#details-heading").inner_text(), "start")

    def test_pov_entry_and_gameplay_keep_the_light_pixel_game_identity(self):
        project = Path(__file__).resolve().parents[1] / "examples" / "basic_project"
        self.page.locator("#folder-input").set_input_files(str(project))
        self.page.locator('[data-id$=".calculate"]').click()
        self.page.locator("#enter-pov").click()

        self.assertIn("mysterious function space", self.page.locator(".launch-description").inner_text())
        self.assertEqual(self.page.locator(".launch-mascot").count(), 1)
        self.assertEqual(self.page.locator("#launch-arguments input").count(), 2)
        self.assertEqual(
            self.page.locator(".launch-card").evaluate(
                "(element) => getComputedStyle(element).borderTopColor"
            ),
            "rgb(237, 83, 97)",
        )

        self.page.locator("#pov-arg-value").fill("21")
        self.page.get_by_role("button", name="Enter POV").last.click()
        self.page.locator("#pov-overlay:not([hidden])").wait_for()
        self.assertEqual(
            self.page.locator("#pov-overlay").evaluate(
                "(element) => getComputedStyle(element).backgroundColor"
            ),
            "rgb(245, 248, 253)",
        )
        self.assertEqual(self.page.locator(".pov-guide-mascot").count(), 1)
        self.assertEqual(
            self.page.locator(".pov-code-card").evaluate(
                "(element) => getComputedStyle(element).backgroundColor"
            ),
            "rgb(255, 255, 255)",
        )
        self.page.get_by_role("button", name="Next").click()
        self.page.locator("#pov-answer-input").fill("42")
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_text("Attempt 1: 42").wait_for()
        self.assertEqual(self.page.locator("#pov-answer-input").input_value(), "42")

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
        self.page.get_by_role("button", name="Back to map").last.click()
        self.assertTrue(self.page.locator("#pov-overlay").is_hidden())

    def test_pov_preserves_attempts_across_retries_and_step_navigation(self):
        self.enter_function("start", {"value": "4"})
        self.page.get_by_role("button", name="Next").click()
        self.page.get_by_role("button", name="multiply", exact=True).click()
        self.page.get_by_role("button", name="Next").click()
        self.page.get_by_role("button", name="Next").click()

        self.assertEqual(self.page.locator("#pov-step-type").inner_text(), "SOLVE THE EXPRESSION")
        answer = self.page.locator("#pov-answer-input")
        answer.fill("7")
        self.page.get_by_role("button", name="Check answer").click()
        self.assertEqual(answer.input_value(), "7")
        self.assertIn("Attempt 1: 7", self.page.locator(".pov-answer-review").inner_text())

        answer.fill("8")
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_text("Attempt 2: 8").wait_for()
        self.assertEqual(self.page.locator("#pov-answer-input").input_value(), "8")
        review = self.page.locator(".pov-answer-review")
        self.assertIn("Attempt 1: 7", review.inner_text())
        self.assertIn("Attempt 2: 8", review.inner_text())
        self.assertIn("CHECKED RESULT", review.inner_text())

        self.page.get_by_role("button", name="Previous").click()
        self.page.get_by_role("button", name="Next").click()
        self.assertEqual(self.page.locator("#pov-answer-input").input_value(), "8")
        self.assertIn("Attempt 1: 7", self.page.locator(".pov-answer-review").inner_text())

    def test_pov_reveal_keeps_attempt_and_stage_clear_has_result_and_actions(self):
        self.enter_function("classify", {"value": "-2"})
        self.page.get_by_role("button", name="Next").click()
        self.page.locator(".pov-choice", has_text="False").click()
        self.page.get_by_role("button", name="Next").click()
        self.page.locator("#pov-answer-input").fill("99")
        self.page.get_by_role("button", name="Check answer").click()
        self.page.get_by_role("button", name="Show answer").click()

        self.page.get_by_text("REVEALED ANSWER").wait_for()
        self.assertEqual(self.page.locator("#pov-answer-input").input_value(), "99")
        self.assertTrue(self.page.locator("#pov-answer-input").is_disabled())
        review = self.page.locator(".pov-answer-review")
        self.assertIn("Attempt 1: 99", review.inner_text())
        self.assertIn("REVEALED ANSWER", review.inner_text())
        self.assertIn("-1", review.inner_text())
        self.assertIn("revealed", self.page.locator("#pov-feedback").inner_text().lower())

        self.page.get_by_role("button", name="Finish").click()
        self.assertEqual(self.page.locator("#pov-completion-title").inner_text(), "Stage clear!")
        self.assertIn("-1", self.page.locator("#pov-completion-value").inner_text())
        self.assertIn("classify", self.page.locator("#pov-completion-summary").inner_text())
        self.assertIn("1 revealed", self.page.locator("#pov-completion-effort").inner_text())
        self.assertEqual(self.page.locator(".completion-mascot").count(), 1)
        self.assertTrue(self.page.locator("#pov-main").is_hidden())
        self.assertTrue(self.page.locator("#pov-controls").is_hidden())
        self.assertEqual(self.page.locator("#pov-overlay").evaluate("(element) => element.scrollTop"), 0)

        self.page.get_by_role("button", name="Replay function").click()
        self.assertFalse(self.page.locator("#pov-main").is_hidden())
        self.assertTrue(self.page.locator("#pov-completion").is_hidden())
        self.assertEqual(self.page.locator("#pov-progress-label").inner_text(), "STEP 1 OF 3")
        self.page.get_by_role("button", name="Back to map").click()

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
