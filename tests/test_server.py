import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from function_pov.server import create_server


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_serves_bundled_ui_and_health_endpoint(self):
        html, content_type = self.get("/")
        self.assertIn(b"Function map", html)
        self.assertIn(b"Enter POV", html)
        self.assertTrue(content_type.startswith("text/html"))

        styles, styles_type = self.get("/static/styles.css")
        script, script_type = self.get("/static/app.js")
        self.assertIn(b"--bg: #101114", styles)
        self.assertIn(b"function-graph", script)
        self.assertTrue(styles_type.startswith("text/css"))
        self.assertTrue(script_type.startswith("text/javascript"))

        health, _ = self.get("/api/health")
        self.assertEqual(json.loads(health), {"status": "ok"})

    def test_analyzes_uploaded_source_without_executing_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            marker = Path(temporary_directory) / "should-not-exist"
            source = (
                "from pathlib import Path\n"
                "Path({!r}).write_text('executed')\n"
                "def outer(value: int = 2):\n"
                "    return inner(value)\n"
                "def inner(number):\n"
                "    return number + 1\n"
            ).format(str(marker))
            response = self.post(
                "/api/analyze",
                {"files": [{"path": "demo/main.py", "content": source}]},
            )

            self.assertEqual(len(response["functions"]), 2)
            outer = next(fn for fn in response["functions"] if fn["name"] == "outer")
            self.assertEqual(outer["parameters"][0]["name"], "value")
            self.assertEqual(
                [(edge["source"], edge["target"]) for edge in response["graph"]["edges"]],
                [("demo.main.outer", "demo.main.inner")],
            )
            self.assertFalse(marker.exists())

    def test_pov_api_checks_answers_and_reveals_hints_and_answers(self):
        source = (
            "def square(value):\n"
            "    result = value ** 2\n"
            "    return result\n"
        )
        session = self.post(
            "/api/pov/start",
            {
                "files": [{"path": "main.py", "content": source}],
                "function_id": "main.square",
                "arguments": {"value": 4},
            },
        )
        self.assertEqual(session["steps"][0]["variables"], {"value": 4})
        challenge = next(
            index for index, step in enumerate(session["steps"])
            if step["kind"] == "arithmetic"
        )
        step_payload = {"session_id": session["session_id"], "step": challenge}
        wrong = self.post(
            "/api/pov/check",
            dict(step_payload, answer=15),
        )
        correct = self.post(
            "/api/pov/check",
            dict(step_payload, answer=16),
        )
        hint = self.post("/api/pov/hint", step_payload)
        answer = self.post("/api/pov/answer", step_payload)

        self.assertFalse(wrong["correct"])
        self.assertTrue(correct["correct"])
        self.assertIn("operator order", hint["hint"])
        self.assertEqual(answer["answer"], 16)

    def test_pov_api_explains_unsupported_syntax(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(
                "/api/pov/start",
                {
                    "files": [
                        {
                            "path": "main.py",
                            "content": "def wait():\n    while True:\n        pass\n",
                        }
                    ],
                    "function_id": "main.wait",
                    "arguments": {},
                },
            )
        self.assertEqual(error.exception.code, 400)
        message = json.loads(error.exception.read().decode("utf-8"))["error"]
        self.assertIn("Supported statements", message)

    def test_reports_invalid_upload_paths(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/api/analyze", {"files": [{"path": "../escape.py", "content": "pass"}]})
        self.assertEqual(error.exception.code, 400)
        message = json.loads(error.exception.read().decode("utf-8"))["error"]
        self.assertIn("relative", message)

    def test_returns_not_found_for_unknown_routes(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get("/unknown")
        self.assertEqual(error.exception.code, 404)

    def get(self, route):
        with urllib.request.urlopen(self.base_url + route) as response:
            return response.read(), response.headers["Content-Type"]

    def post(self, route, payload):
        request = urllib.request.Request(
            self.base_url + route,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
