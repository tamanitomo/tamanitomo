"""Synthetic owner, stranger, and background conversations for workspace previews."""

import contextlib
import sqlite3
from pathlib import Path

OWNER_TELEGRAM = "4242"
STRANGER_TELEGRAM = "9999"


class HermesStore:
    """A minimal Hermes-shaped SQLite store containing invented conversations."""

    def __init__(self, home):
        self.path = Path(home) / "state.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.next_platform_id = 1000
        with self.db() as database:
            database.executescript("""
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY, source TEXT, started_at REAL,
                    profile_name TEXT, user_id TEXT, chat_id TEXT, chat_type TEXT
                );
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                    role TEXT, content TEXT, timestamp REAL, platform_message_id TEXT,
                    display_kind TEXT, _compressed_summary INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0
                );
            """)

    @contextlib.contextmanager
    def db(self):
        with contextlib.closing(sqlite3.connect(self.path)) as database:
            with database:
                yield database

    def session(
        self,
        ident,
        source,
        *,
        profile="nova",
        user_id=None,
        chat_id=None,
        chat_type=None,
        started=1.0,
    ):
        with self.db() as database:
            database.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
                (ident, source, started, profile, user_id, chat_id, chat_type),
            )
        return ident

    def say(self, session, role, content, timestamp, **columns):
        with self.db() as database:
            source = database.execute(
                "SELECT source FROM sessions WHERE id=?", (session,)
            ).fetchone()
            if (
                role == "user"
                and source
                and source[0] == "telegram"
                and "platform_message_id" not in columns
            ):
                self.next_platform_id += 1
                columns["platform_message_id"] = str(self.next_platform_id)
            names = ["session_id", "role", "content", "timestamp", *columns]
            cursor = database.execute(
                f"INSERT INTO messages ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
                (session, role, content, timestamp, *columns.values()),
            )
            return cursor.lastrowid


def standard_sessions(store):
    store.session("web", "cli", started=1)
    store.session("term", "cli", started=2)
    store.session(
        "tg",
        "telegram",
        user_id=OWNER_TELEGRAM,
        chat_id=OWNER_TELEGRAM,
        chat_type="dm",
        started=3,
    )
    store.session(
        "stranger",
        "telegram",
        user_id=STRANGER_TELEGRAM,
        chat_id=STRANGER_TELEGRAM,
        chat_type="dm",
        started=4,
    )
    store.session(
        "group",
        "telegram",
        user_id=OWNER_TELEGRAM,
        chat_id="-100777",
        chat_type="group",
        started=5,
    )
    store.session("job", "cron", started=6)
    store.session(
        "rowan-tg",
        "telegram",
        profile="rowan",
        user_id=OWNER_TELEGRAM,
        chat_id=OWNER_TELEGRAM,
        chat_type="dm",
        started=7,
    )
