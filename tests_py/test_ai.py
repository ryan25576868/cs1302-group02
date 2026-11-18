"""Tests for AI settings validation without any network calls."""

from __future__ import annotations

import unittest

from python_app.ai import AIError, AISettings, PROVIDERS, complete


class AISettingsTests(unittest.TestCase):
    def test_provider_defaults(self) -> None:
        self.assertEqual(set(PROVIDERS), {"openai", "deepseek", "grok", "anthropic", "gemini"})
        for provider in PROVIDERS.values():
            self.assertTrue(provider["base"].startswith("https://"))
            self.assertTrue(provider["model"])
            self.assertTrue(provider["name"])

    def test_settings_require_a_url_and_model(self) -> None:
        settings = AISettings(provider="openai", base_url="", model="m")
        with self.assertRaises(AIError):
            complete(settings, "", [{"role": "user", "content": "hi"}])
        settings = AISettings(provider="openai", base_url="https://example.com", model="")
        with self.assertRaises(AIError):
            complete(settings, "", [{"role": "user", "content": "hi"}])

    def test_settings_reject_invalid_protocol(self) -> None:
        settings = AISettings(provider="openai", base_url="ftp://example.com", model="m")
        with self.assertRaises(AIError):
            complete(settings, "", [{"role": "user", "content": "hi"}])

    def test_settings_accepts_defaults(self) -> None:
        settings = AISettings()
        self.assertTrue(settings.configured)
        self.assertEqual(settings.provider_name(), "OpenAI / compatible")


if __name__ == "__main__":
    unittest.main()
