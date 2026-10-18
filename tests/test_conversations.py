import pytest
from fastapi.testclient import TestClient

import database
import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database, "DB_PATH", str(tmp_path / "ask-olake-test.sqlite3")
    )
    monkeypatch.setattr(main, "CACHE_TTL_SECONDS", 0)
    monkeypatch.setattr(
        main,
        "retrieve",
        lambda question: [{"chunk": {"text": "evidence"}, "score": 0.9}],
    )
    source_details = [
        {
            "title": "OLake Guide",
            "url": "https://olake.io/docs/guide",
            "excerpt": "verified source excerpt",
            "score": 0.9,
            "chunk_id": 0,
        }
    ]
    monkeypatch.setattr(
        main,
        "context_and_sources",
        lambda results: ("verified context", source_details, 0.9, False),
    )
    generated_modes = []

    def generate(question, context, mode="normal"):
        generated_modes.append(mode)
        return "Grounded " + mode + " answer."

    monkeypatch.setattr(main, "generate", generate)
    with TestClient(main.app) as test_client:
        test_client.generated_modes = generated_modes
        yield test_client


def create_session(client):
    response = client.post("/session")
    assert response.status_code == 200
    token = response.json()["session_token"]
    assert len(token) >= 40
    return {"X-Ask-Olake-Session": token}


def test_session_and_conversation_routes_are_owner_scoped(client):
    owner_headers = create_session(client)
    other_headers = create_session(client)

    assert client.get("/conversations").status_code == 401
    created = client.post(
        "/conversations",
        headers=owner_headers,
        json={"title": "Postgres CDC"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    answer = client.post(
        "/ask",
        headers=owner_headers,
        json={
            "question": "How do I configure Postgres CDC?",
            "conversation_id": conversation_id,
            "mode": "troubleshoot",
        },
    )
    assert answer.status_code == 200
    body = answer.json()
    assert body["answer"] == "Grounded troubleshoot answer."
    assert body["sources"] == ["https://olake.io/docs/guide"]
    assert body["source_details"][0]["excerpt"] == "verified source excerpt"
    assert body["conversation_id"] == conversation_id
    assert body["message_id"]
    assert client.generated_modes == ["troubleshoot"]

    messages = client.get(
        f"/conversations/{conversation_id}/messages",
        headers=owner_headers,
    )
    assert messages.status_code == 200
    assert [message["role"] for message in messages.json()] == ["user", "assistant"]
    assert messages.json()[1]["sources"][0]["url"] == "https://olake.io/docs/guide"
    assert messages.json()[1]["mode"] == "troubleshoot"

    assert client.get(
        f"/conversations/{conversation_id}",
        headers=other_headers,
    ).status_code == 404
    assert client.get(
        "/conversations",
        headers=other_headers,
    ).json() == []
    assert client.patch(
        f"/conversations/{conversation_id}",
        headers=other_headers,
        json={"title": "stolen"},
    ).status_code == 404
    assert client.delete(
        f"/conversations/{conversation_id}",
        headers=other_headers,
    ).status_code == 404


def test_conversation_search_rename_delete(client):
    headers = create_session(client)
    created = client.post(
        "/conversations", headers=headers, json={"title": "Initial title"}
    ).json()
    conversation_id = created["id"]
    answer = client.post(
        "/ask",
        headers=headers,
        json={"question": "Find the unique search phrase", "conversation_id": conversation_id},
    )
    assert answer.status_code == 200

    search = client.get(
        "/conversations/search",
        headers=headers,
        params={"q": "unique search phrase"},
    )
    assert search.status_code == 200
    assert [item["id"] for item in search.json()] == [conversation_id]

    renamed = client.patch(
        f"/conversations/{conversation_id}",
        headers=headers,
        json={"title": "Renamed chat"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed chat"

    removed = client.delete(
        f"/conversations/{conversation_id}", headers=headers
    )
    assert removed.status_code == 204
    assert client.get(
        f"/conversations/{conversation_id}/messages", headers=headers
    ).status_code == 404


def test_legacy_ask_contract_remains_available_without_session(client):
    response = client.post("/ask", json={"question": "A supported question"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Grounded normal answer."
    assert body["sources"] == ["https://olake.io/docs/guide"]


def test_invalid_requests_and_unknown_sessions_are_rejected(client):
    headers = create_session(client)
    assert client.post("/ask", json={"question": ""}).status_code == 400
    assert client.post(
        "/ask", json={"question": "x" * 4001}
    ).status_code == 422
    assert client.post(
        "/ask",
        headers=headers,
        json={"question": "supported", "mode": "invented"},
    ).status_code == 422
    assert client.get(
        "/conversations/not-a-valid-id", headers=headers
    ).status_code == 422
    assert client.get(
        "/conversations/search", headers=headers, params={"q": "   "}
    ).status_code == 400


def test_irrelevant_questions_return_dont_know_without_citations(client, monkeypatch):
    monkeypatch.setattr(main, "retrieve", lambda question: [])
    response = client.post("/ask", json={"question": "What is the moon made of?"})
    assert response.status_code == 200
    assert "don't know" in response.json()["answer"].lower()
    assert response.json()["sources"] == []
    assert response.json()["source_details"] == []


def test_below_threshold_results_return_dont_know_without_citations(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "retrieve",
        lambda question: [
            {
                "chunk": {"text": "weak evidence"},
                "score": main.SIM_THRESHOLD - 0.01,
            }
        ],
    )
    monkeypatch.setattr(
        main,
        "context_and_sources",
        lambda results: (
            "weak evidence",
            [{
                "title": "Weak match",
                "url": "https://olake.io/docs/weak-match",
                "excerpt": "weak evidence",
                "score": main.SIM_THRESHOLD - 0.01,
            }],
            main.SIM_THRESHOLD - 0.01,
            True,
        ),
    )
    response = client.post("/ask", json={"question": "Unsupported question"})
    assert response.status_code == 200
    assert "don't know" in response.json()["answer"].lower()
    assert response.json()["sources"] == []
    assert response.json()["source_details"] == []


def test_invalid_retrieved_citation_is_not_returned(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "context_and_sources",
        lambda results: (
            "untrusted context",
            [{
                "title": "Unsafe",
                "url": "javascript:alert(1)",
                "excerpt": "untrusted",
                "score": 0.9,
            }],
            0.9,
            False,
        ),
    )
    response = client.post("/ask", json={"question": "A supported question"})
    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["source_details"] == []


def test_legacy_database_is_migrated(tmp_path, monkeypatch):
    import sqlite3

    legacy_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(legacy_path)
    conn.executescript("""
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources TEXT,
            created_at REAL NOT NULL
        );
    """)
    conn.close()
    monkeypatch.setattr(database, "DB_PATH", str(legacy_path))
    database.init_db()
    with sqlite3.connect(legacy_path) as migrated:
        conversation_columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(conversations)")
        }
        message_columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(messages)")
        }
    assert "owner_hash" in conversation_columns
    assert "mode" in message_columns
