import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import llm


class GenerateFallbackTests(unittest.TestCase):
    def setUp(self):
        self._provider = llm.LLM_PROVIDER
        self._api_key = llm.OPENAI_API_KEY

    def tearDown(self):
        llm.LLM_PROVIDER = self._provider
        llm.OPENAI_API_KEY = self._api_key

    def test_extractive_fallback_returns_context_when_no_provider(self):
        llm.LLM_PROVIDER = "none"
        llm.OPENAI_API_KEY = ""
        out = llm.generate("q", "relevant passage text")
        self.assertIn("relevant passage text", out)

    def test_extractive_fallback_says_dont_know_when_no_context(self):
        llm.LLM_PROVIDER = "none"
        llm.OPENAI_API_KEY = ""
        out = llm.generate("q", "")
        self.assertIn("don't know", out.lower())
