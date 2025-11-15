"""
Chat session management for RAG conversations.

Stores and retrieves conversation history, maintains session state,
and provides session utilities for multi-turn conversations.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import sqlite3
import uuid

logger = logging.getLogger(__name__)

# Initialize SQLite for persistent session storage
SESSIONS_DB = "./data/chat_sessions.db"


def _init_sessions_db():
    """Initialize chat sessions database."""
    Path(SESSIONS_DB).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SESSIONS_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                title TEXT,
                metadata_json TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                sources_json TEXT,
                created_at TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id ON chat_messages(session_id)
        """)
        conn.commit()
        logger.info(f"Chat sessions database initialized at {SESSIONS_DB}")


# Initialize on import
_init_sessions_db()


class ChatSession:
    """Represents a single conversation session."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id or "anonymous"
        self.title = title or f"Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        self.created_at = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow().isoformat()
        self.messages: List[Dict[str, Any]] = []

    def add_message(
        self,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Add a message to the session.

        Args:
            role: 'user' or 'assistant'
            content: Message text
            sources: Optional list of source citations

        Returns:
            Message ID
        """
        message_id = str(uuid.uuid4())
        message = {
            "message_id": message_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "created_at": datetime.utcnow().isoformat(),
        }
        self.messages.append(message)
        self.updated_at = datetime.utcnow().isoformat()

        # Persist to DB
        with sqlite3.connect(SESSIONS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chat_messages (message_id, session_id, role, content, sources_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    message_id,
                    self.session_id,
                    role,
                    content,
                    json.dumps(sources or []),
                    message["created_at"],
                ),
            )
            conn.commit()

        return message_id

    def save(self):
        """Persist session to database."""
        with sqlite3.connect(SESSIONS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO chat_sessions 
                (session_id, user_id, created_at, updated_at, title, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    self.session_id,
                    self.user_id,
                    self.created_at,
                    self.updated_at,
                    self.title,
                    "{}",
                ),
            )
            conn.commit()
        logger.info(f"Session {self.session_id} saved")

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
            "messages": self.messages,
        }


def create_session(user_id: Optional[str] = None, title: Optional[str] = None) -> ChatSession:
    """Create a new chat session."""
    session = ChatSession(user_id=user_id, title=title)
    session.save()
    return session


def get_session(session_id: str) -> Optional[ChatSession]:
    """Retrieve a session by ID."""
    try:
        with sqlite3.connect(SESSIONS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, user_id, created_at, updated_at, title
                FROM chat_sessions WHERE session_id = ?
            """,
                (session_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        session_id, user_id, created_at, updated_at, title = row
        session = ChatSession(session_id=session_id, user_id=user_id, title=title)
        session.created_at = created_at
        session.updated_at = updated_at

        # Load messages
        with sqlite3.connect(SESSIONS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT message_id, role, content, sources_json, created_at
                FROM chat_messages WHERE session_id = ?
                ORDER BY created_at ASC
            """,
                (session_id,),
            )
            rows = cursor.fetchall()

        for msg_id, role, content, sources_json, created_at in rows:
            message = {
                "message_id": msg_id,
                "role": role,
                "content": content,
                "sources": json.loads(sources_json),
                "created_at": created_at,
            }
            session.messages.append(message)

        return session
    except Exception as e:
        logger.error(f"Failed to retrieve session {session_id}: {e}")
        return None


def list_sessions(user_id: Optional[str] = None, limit: int = 50) -> List[ChatSession]:
    """List sessions, optionally filtered by user."""
    try:
        with sqlite3.connect(SESSIONS_DB) as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    """
                    SELECT session_id, user_id, created_at, updated_at, title
                    FROM chat_sessions WHERE user_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                """,
                    (user_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT session_id, user_id, created_at, updated_at, title
                    FROM chat_sessions ORDER BY updated_at DESC LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()

        sessions = []
        for session_id, user_id, created_at, updated_at, title in rows:
            session = ChatSession(session_id=session_id, user_id=user_id, title=title)
            session.created_at = created_at
            session.updated_at = updated_at
            sessions.append(session)

        return sessions
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return []
