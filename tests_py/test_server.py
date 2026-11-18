"""Tests for the Python desktop server and AI proxy contract."""

from __future__ import annotations

import json
import shutil
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from python_app.server import start_server, stop_server


class PrismServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parent / "_fixture"
        shutil.rmtree(cls.root, ignore_errors=True)
        cls.root.mkdir(parents=True, exist_ok=True)
        root = cls.root
        (root / "index.html").write_text("<!doctype html><title>Prism test</title>", encoding="utf-8")
        (root / "js").mkdir()
        (root / "js" / "app.js").write_text("export const ok = true;", encoding="utf-8")
        (root / "assets").mkdir()
        (root / "assets" / "icon.svg").write_text("<svg/>", encoding="utf-8")
        cls.server, cls.url = start_server(root)

    @classmethod
    def tearDownClass(cls) -> None:
        stop_server(cls.server)
        shutil.rmtree(cls.root, ignore_errors=True)

    def request(self, path: str, data: dict | None = None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(
            self.url + path,
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
        )
        return urllib.request.urlopen(request, timeout=5)

    def test_health(self) -> None:
        with self.request("/api/health") as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["proxy"])

    def test_static_index_and_assets(self) -> None:
        with self.request("/") as response:
            self.assertIn("Prism test", response.read().decode())
            self.assertIn("text/html", response.headers["Content-Type"])
        with self.request("/js/app.js") as response:
            self.assertIn("javascript", response.headers["Content-Type"])
        with self.request("/assets/icon.svg") as response:
            self.assertEqual(response.status, 200)

    def test_unknown_api(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_ai_validation(self) -> None:
        cases = [
            ({"provider": "bogus"}, "Unsupported"),
            ({"provider": "openai"}, "model"),
            ({"provider": "openai", "model": "m"}, "base URL"),
            ({"provider": "openai", "model": "m", "baseUrl": "ftp://x", "messages": [{"role": "user", "content": "hi"}]}, "http"),
            ({"provider": "openai", "model": "m", "baseUrl": "https://example.com", "messages": []}, "message"),
        ]
        for payload, message in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    self.request("/api/ai", payload)
                body = json.loads(ctx.exception.read())
                self.assertIn(message.lower(), body["error"].lower())

    def test_python_analysis_route(self) -> None:
        with self.request("/api/analyze-python", {"source": "print(2 + 3)\n"}) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["trace"]["output"], "5\n")
        self.assertEqual(payload["analysis"]["languageId"], "python")

    def test_python_analysis_syntax_error(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/analyze-python", {"source": "def broken(:\n"})
        self.assertEqual(ctx.exception.code, 400)

    def test_ai_rejects_bad_json(self) -> None:
        request = urllib.request.Request(
            self.url + "/api/ai",
            data=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_path_traversal(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/../../outside.txt")
        self.assertIn(ctx.exception.code, {403, 404})


if __name__ == "__main__":
    unittest.main()
