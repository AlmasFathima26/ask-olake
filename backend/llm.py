import os
import requests
from config import (
    LLM_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    OPENROUTER_FALLBACK_MODELS, OLLAMA_BASE_URL, OLLAMA_MODEL,
)

SYSTEM = (
    "You are Ask OLake, a helpful assistant for the OLake documentation. "
    "Answer the user's question using ONLY the provided context. "
    "Every factual claim or configuration instruction must be supported by the context. "
    "Do not invent API behavior, commands, configuration settings, citations, or source URLs. "
    "If the retrieved context does not contain enough evidence to answer, say clearly that "
    "the answer cannot be verified from the available documentation and suggest where to look. "
    "Distinguish documented facts from reasonable inferences. "
    "If retrieved sources conflict, explain the conflict instead of silently choosing one. "
    "Do not append a Sources or References section or repeat source URLs; "
    "the application presents verified source links separately. Be concise and accurate."
)

TROUBLESHOOTING_SYSTEM = (
    "You are Ask OLake in troubleshooting mode. "
    "Answer the user's question using ONLY the provided context. "
    "Structure your response into these sections: "
    "1. Problem: restate the issue. "
    "2. Likely causes: causes supported by the available evidence. "
    "3. Checks: safe diagnostic steps. "
    "4. Solution: step-by-step instructions grounded in documentation. "
    "5. Verification: how to confirm whether the issue is fixed. "
    "The app displays source links separately as a sixth section. "
    "Every factual claim must be supported by the context. "
    "Do not invent API behavior, commands, configuration settings, citations, or source URLs. "
    "If the context does not contain enough evidence, say so clearly and ask for missing "
    "diagnostic details instead of guessing. "
    "Do not claim a command was executed or a problem was fixed unless that action actually occurred. "
    "Do not append a Sources or References section or repeat source URLs."
)


def _provider():
    if LLM_PROVIDER != "auto":
        return LLM_PROVIDER
    if OPENAI_API_KEY:
        return "openai"
    # try ollama
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if r.ok:
            return "ollama"
    except Exception:
        pass
    return "none"


def generate(question, context, mode="normal"):
    provider = _provider()
    system = TROUBLESHOOTING_SYSTEM if mode == "troubleshoot" else SYSTEM
    user_msg = (
        f"Context:\n{context}\n\nQuestion: {question}\n\n"
        "Answer using the provided context. Do not add a Sources section."
    )
    if provider == "openai":
        if not OPENAI_API_KEY:
            return (
                "(LLM error: OPENROUTER_API_KEY or OPENAI_API_KEY is not configured.)"
                f"\n\nBased on retrieved context:\n{context}"
            )
        try:
            payload = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            }
            if "openrouter.ai" in OPENAI_BASE_URL.lower():
                payload["models"] = [
                    model for model in OPENROUTER_FALLBACK_MODELS
                    if model != OPENAI_MODEL
                ]
                payload["reasoning"] = {"effort": "none"}
            r = requests.post(
                f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            r.raise_for_status()
            try:
                content = r.json()["choices"][0]["message"]["content"]
            except (IndexError, KeyError, TypeError, ValueError):
                content = None
            if not isinstance(content, str) or not content.strip():
                return (
                    "(LLM error: the provider returned an invalid response.)"
                    f"\n\nBased on retrieved context:\n{context}"
                )
            return content.strip()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if "openrouter.ai" in OPENAI_BASE_URL.lower():
                messages = {
                    401: "OpenRouter rejected the API key (401). Check the key configured locally.",
                    402: "OpenRouter reports that this key has insufficient credit (402).",
                    403: "OpenRouter denied access to the configured model (403).",
                    429: "OpenRouter rate-limited this request (429). Wait and try again.",
                    502: "The configured model provider is temporarily unavailable (502).",
                    503: "The configured model provider is temporarily unavailable (503).",
                }
            else:
                messages = {
                    401: "The configured LLM provider rejected the API key (401).",
                    402: "The configured LLM provider reports insufficient credit (402).",
                    403: "The configured LLM provider denied access to the model (403).",
                    429: "The configured LLM provider rate-limited this request (429).",
                    502: "The configured model provider is temporarily unavailable (502).",
                    503: "The configured model provider is temporarily unavailable (503).",
                }
            status_suffix = f" ({status})" if status else ""
            message = messages.get(
                status,
                f"The LLM provider returned an HTTP error{status_suffix}.",
            )
            return f"(LLM error: {message})\n\nBased on retrieved context:\n{context}"
        except requests.Timeout:
            return (
                "(LLM error: the provider request timed out.)"
                f"\n\nBased on retrieved context:\n{context}"
            )
        except requests.RequestException as exc:
            return (
                f"(LLM error: provider request failed ({type(exc).__name__}).)"
                f"\n\nBased on retrieved context:\n{context}"
            )
    if provider == "ollama":
        try:
            r = requests.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": system + "\n\n" + user_msg,
                      "stream": False},
                timeout=120,
            )
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except Exception as e:
            return f"(LLM error: {e})\n\nBased on retrieved context:\n{context}"
    # none: extractive fallback
    if not context.strip():
        return "I don't know based on the available documentation."
    if mode == "troubleshoot":
        return (
            f"## Problem\n{question}\n\n"
            "## Likely causes\n"
            "The available documentation excerpts do not establish a specific cause.\n\n"
            "## Checks\n"
            "Review the supporting OLake documentation linked below and compare it "
            "with the observed behavior.\n\n"
            "## Solution\n"
            "I cannot provide verified fix steps without a configured language model "
            "and sufficient diagnostic details.\n\n"
            "## Verification\n"
            "After following the applicable documented steps, rerun the affected "
            "operation and check its logs."
        )
    return ("I don't have an LLM configured, but here are the most relevant passages:\n\n"
            + context)
