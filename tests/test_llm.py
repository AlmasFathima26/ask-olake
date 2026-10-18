import os
import sys
from unittest.mock import Mock

import llm
import pytest


def test_extractive_fallback_returns_context_when_no_provider(monkeypatch):
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm, "OLLAMA_BASE_URL", "http://localhost:1")
    # Force provider to none
    monkeypatch.setattr(llm, "LLM_PROVIDER", "none")

    out = llm.generate("q", "relevant passage text")
    assert "relevant passage text" in out


def test_extractive_fallback_says_dont_know_when_no_context(monkeypatch):
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm, "OLLAMA_BASE_URL", "http://localhost:1")
    monkeypatch.setattr(llm, "LLM_PROVIDER", "none")

    out = llm.generate("q", "")
    assert "don't know" in out.lower()


def test_troubleshooting_fallback_uses_requested_sections(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "none")
    answer = llm.generate("CDC stopped", "Replication slots are required.", mode="troubleshoot")
    for heading in ("## Problem", "## Likely causes", "## Checks", "## Solution", "## Verification"):
        assert heading in answer
    assert "Replication slots are required." not in answer


def test_llm_prompt_handles_conflicting_sources_and_forbids_fabrication():
    prompt = llm.SYSTEM.lower()
    assert "sources conflict" in prompt
    assert "do not invent" in prompt
    assert "do not append a sources" in prompt


def test_openrouter_authorization_header_and_troubleshooting_payload(monkeypatch):
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"content": "Grounded answer"}}]
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(llm, "OPENAI_MODEL", "z-ai/glm-4.7-flash")

    assert llm.generate("CDC failed", "documented evidence", mode="troubleshoot") == "Grounded answer"
    request = post.call_args.kwargs
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert "troubleshooting mode" in request["json"]["messages"][0]["content"].lower()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "rejected the API key"),
        (402, "insufficient credit"),
        (403, "denied access to the configured model"),
        (429, "rate-limited this request"),
        (502, "temporarily unavailable"),
        (503, "temporarily unavailable"),
    ],
)
def test_openrouter_http_errors_are_safe_and_actionable(monkeypatch, status, expected):
    response = Mock()
    response.status_code = status
    response.raise_for_status.side_effect = llm.requests.HTTPError(response=response)
    post = Mock(return_value=response)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr(llm, "OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    answer = llm.generate("question", "retrieved evidence")
    assert expected in answer
    assert "private-test-key" not in answer
    assert answer.startswith("(LLM error:")


def test_openai_provider_without_key_does_not_make_request(monkeypatch):
    post = Mock()
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "")

    answer = llm.generate("question", "retrieved evidence")
    assert "not configured" in answer
    post.assert_not_called()


def test_malformed_openrouter_response_is_reported(monkeypatch):
    response = Mock()
    response.json.return_value = {"choices": []}
    post = Mock(return_value=response)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "test-key")

    answer = llm.generate("question", "retrieved evidence")
    assert "invalid response" in answer


def test_openrouter_timeout_returns_safe_error(monkeypatch):
    post = Mock(side_effect=llm.requests.Timeout)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr(llm, "OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    answer = llm.generate("question", "retrieved evidence")
    assert "timed out" in answer
    assert "private-test-key" not in answer


def test_openrouter_error_fallback_preserves_complete_retrieved_context(monkeypatch):
    response = Mock()
    response.status_code = 401
    response.raise_for_status.side_effect = llm.requests.HTTPError(response=response)
    monkeypatch.setattr(llm.requests, "post", Mock(return_value=response))
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm, "OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr(llm, "OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    context = "retrieved evidence " * 120 + "LAST_REQUIRED_DETAIL"

    answer = llm.generate("question", context)
    assert answer.endswith(context)
    assert "private-test-key" not in answer
