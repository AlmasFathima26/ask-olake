import sys
import types

import pytest

import rag


def test_chunk_text_uses_passed_source():
    chunks = rag._chunk_text("para one\n\npara two", "olake-docs://test.md")
    assert isinstance(chunks, list)
    assert len(chunks) >= 1
    for c in chunks:
        assert {"text", "source", "title", "section", "chunk_id"} <= set(c.keys())
        assert c["source"] == "olake-docs://test.md"


def test_chunk_text_empty_text():
    chunks = rag._chunk_text("", "olake-docs://empty.md")
    assert chunks == []


def test_chunks_retain_heading_provenance():
    chunks = rag._chunk_text(
        "# Installation\n\nIntro.\n\n## Docker\n\nRun the container.",
        "https://docs.example/install",
        title="Installation",
    )
    docker_chunk = next(chunk for chunk in chunks if "Run the container" in chunk["text"])
    assert docker_chunk["title"] == "Installation"
    assert docker_chunk["section"] == "Docker"


def test_context_and_sources_empty():
    context, sources, max_score, low = rag.context_and_sources([])
    assert context == ""
    assert sources == []
    assert max_score == 0.0
    assert low is True


def test_context_omits_invalid_source_urls():
    result = {
        "chunk": {
            "text": "evidence",
            "source": "javascript:alert(1)",
            "title": "Unsafe",
        },
        "score": 0.9,
    }
    _, sources, _, _ = rag.context_and_sources([result])
    assert sources == []


def test_context_and_sources_threshold_drops_low_scores():
    results = [
        {"chunk": {"text": "high", "source": "https://docs.example/a"}, "score": 0.9},
        {"chunk": {"text": "low", "source": "https://docs.example/b"}, "score": 0.1},
    ]
    context, sources, max_score, low = rag.context_and_sources(results)
    assert max_score == 0.9
    assert [source["url"] for source in sources] == ["https://docs.example/a"]
    assert low is False


def test_context_deduplicates_source_metadata():
    results = [
        {
            "chunk": {
                "text": "first excerpt",
                "source": "https://docs.example/a",
                "title": "Guide",
                "section": "Setup",
                "chunk_id": 0,
            },
            "score": 0.9,
        },
        {
            "chunk": {
                "text": "second excerpt",
                "source": "https://docs.example/a",
                "title": "Guide",
                "section": "FAQ",
                "chunk_id": 1,
            },
            "score": 0.8,
        },
    ]
    _, sources, _, _ = rag.context_and_sources(results)
    assert len(sources) == 1
    assert sources[0]["url"] == "https://docs.example/a"
    assert "Guide — Setup" in sources[0]["title"]
    assert "Guide — FAQ" in sources[0]["title"]
    assert "first excerpt" in sources[0]["excerpt"]
    assert "second excerpt" in sources[0]["excerpt"]


def test_retrieve_returns_empty_when_no_chunks(monkeypatch):
    monkeypatch.setattr(rag, "_index", {"chunks": [], "embeddings": None})
    assert rag.retrieve("anything") == []
