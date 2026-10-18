import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time

from config import BASE_DIR

DB_PATH = os.getenv(
    "ASK_OLAKE_DB", os.path.join(BASE_DIR, "data", "ask_olake.db")
)
_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def new_session_token():
    return secrets.token_urlsafe(32)


def _owner_hash(owner_token):
    if not owner_token:
        raise ValueError("An owner token is required")
    return hashlib.sha256(owner_token.encode("utf-8")).hexdigest()


def init_db():
    """Create or migrate the local SQLite schema."""
    directory = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(directory, exist_ok=True)
    with _lock:
        conn = _connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner_hash TEXT,
                    title TEXT NOT NULL DEFAULT 'New conversation',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    sources TEXT,
                    mode TEXT NOT NULL DEFAULT 'normal',
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at, id);
            """)
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "owner_hash" not in columns:
                conn.execute("ALTER TABLE conversations ADD COLUMN owner_hash TEXT")
            message_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "mode" not in message_columns:
                conn.execute(
                    "ALTER TABLE messages ADD COLUMN mode TEXT NOT NULL DEFAULT 'normal'"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated "
                "ON conversations(owner_hash, updated_at DESC)"
            )
            conn.commit()
        finally:
            conn.close()


def _new_id():
    return secrets.token_urlsafe(18)


def create_conversation(owner_token, title="New conversation"):
    now = time.time()
    cid = _new_id()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO conversations (id, owner_hash, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cid, _owner_hash(owner_token), title, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    return cid


def get_conversation(cid, owner_token):
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "WHERE id = ? AND owner_hash = ?",
                (cid, _owner_hash(owner_token)),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()


def list_conversations(owner_token, limit=20, search=None):
    owner_hash = _owner_hash(owner_token)
    with _lock:
        conn = _connect()
        try:
            if search:
                pattern = _like_pattern(search)
                rows = conn.execute(
                    """
                    SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.owner_hash = ? AND (c.title LIKE ? ESCAPE '\\'
                        OR m.content LIKE ? ESCAPE '\\')
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    (owner_hash, pattern, pattern, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, created_at, updated_at FROM conversations "
                    "WHERE owner_hash = ? ORDER BY updated_at DESC LIMIT ?",
                    (owner_hash, limit),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def _like_pattern(value):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def update_conversation_title(cid, owner_token, title):
    now = time.time()
    with _lock:
        conn = _connect()
        try:
            cursor = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? "
                "WHERE id = ? AND owner_hash = ?",
                (title, now, cid, _owner_hash(owner_token)),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()


def delete_conversation(cid, owner_token):
    with _lock:
        conn = _connect()
        try:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND owner_hash = ?",
                (cid, _owner_hash(owner_token)),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()


def add_exchange(cid, owner_token, question, answer, sources=None, mode="normal"):
    """Save a complete ask/answer pair in one transaction."""
    now = time.time()
    user_id, assistant_id = _new_id(), _new_id()
    sources_json = json.dumps(sources or [], separators=(",", ":"))
    with _lock:
        conn = _connect()
        try:
            conn.execute("BEGIN")
            owned = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND owner_hash = ?",
                (cid, _owner_hash(owner_token)),
            ).fetchone()
            if owned is None:
                conn.rollback()
                return None
            conn.executemany(
                "INSERT INTO messages "
                "(id, conversation_id, role, content, sources, mode, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (user_id, cid, "user", question, None, mode, now),
                    (assistant_id, cid, "assistant", answer, sources_json, mode, now + 0.000001),
                ],
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now + 0.000001, cid),
            )
            conn.commit()
            return user_id, assistant_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_messages(cid, owner_token):
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT m.id, m.role, m.content, m.sources, m.mode, m.created_at
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.id = ? AND c.owner_hash = ?
                ORDER BY m.created_at ASC, m.rowid ASC
                """,
                (cid, _owner_hash(owner_token)),
            ).fetchall()
            messages = []
            for row in rows:
                message = dict(row)
                try:
                    message["sources"] = json.loads(message["sources"]) if message["sources"] else []
                except (json.JSONDecodeError, TypeError):
                    message["sources"] = []
                messages.append(message)
            return messages
        finally:
            conn.close()


def search_conversations(owner_token, query, limit=20):
    pattern = _like_pattern(query)
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.owner_hash = ? AND (c.title LIKE ? ESCAPE '\\'
                    OR m.content LIKE ? ESCAPE '\\')
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (_owner_hash(owner_token), pattern, pattern, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
