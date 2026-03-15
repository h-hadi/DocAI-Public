"""Authentication module for DocAI.

Provides user management, password hashing (bcrypt), and login verification
backed by SQLite. Thread-safe for use with Gradio's multi-threaded server.
"""

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import bcrypt

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docai_users.db")
_lock = threading.Lock()
_PASSWORD_EXPIRY_DAYS = 14


def _get_conn() -> sqlite3.Connection:
    """Return a new SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _user_dict_safe(row: sqlite3.Row | None) -> dict | None:
    """Convert row to dict without password_hash."""
    if row is None:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    return d


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create users table if it doesn't exist. Seed default admin if empty."""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    password_changed_at TEXT NOT NULL,
                    password_expiry_disabled INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            if row["cnt"] == 0:
                now = _now_iso()
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role, created_at, password_changed_at, password_expiry_disabled)
                    VALUES (?, ?, 'admin', ?, ?, 1)
                    """,
                    ("admin", _hash_password("admin"), now, now),
                )
            conn.commit()
        finally:
            conn.close()


def verify_login(username: str, password: str) -> dict | None:
    """Return user dict if credentials are valid, None otherwise."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    if not _check_password(password, row["password_hash"]):
        return None
    return dict(row)


def is_password_expired(user: dict) -> bool:
    """Check if a non-admin user's password has expired (14-day policy)."""
    if user.get("role") == "admin":
        return False
    if user.get("password_expiry_disabled"):
        return False
    changed_at = datetime.fromisoformat(user["password_changed_at"])
    return datetime.now(timezone.utc) - changed_at > timedelta(days=_PASSWORD_EXPIRY_DAYS)


def change_password(username: str, old_password: str, new_password: str) -> bool:
    """Change password after verifying old password. Returns success."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row is None or not _check_password(old_password, row["password_hash"]):
                return False
            conn.execute(
                "UPDATE users SET password_hash = ?, password_changed_at = ? WHERE username = ?",
                (_hash_password(new_password), _now_iso(), username),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def force_change_password(username: str, new_password: str) -> bool:
    """Admin-only: change password without requiring old password."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE users SET password_hash = ?, password_changed_at = ? WHERE username = ?",
                (_hash_password(new_password), _now_iso(), username),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def create_user(username: str, password: str, role: str = "user") -> bool:
    """Create a new user. Returns False if username already exists."""
    now = _now_iso()
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at, password_changed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, _hash_password(password), role, now, now),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


def delete_user(username: str) -> bool:
    """Delete a user. Cannot delete admin-role users."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT role FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row is None or row["role"] == "admin":
                return False
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            return True
        finally:
            conn.close()


def list_users() -> list[dict]:
    """Return all users without password_hash."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
            return [_user_dict_safe(r) for r in rows]
        finally:
            conn.close()


def toggle_expiry(username: str, disabled: bool) -> bool:
    """Set password_expiry_disabled for a user. Returns success."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "UPDATE users SET password_expiry_disabled = ? WHERE username = ?",
                (int(disabled), username),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def get_user(username: str) -> dict | None:
    """Return user dict without password_hash, or None."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return _user_dict_safe(row)
        finally:
            conn.close()


# Auto-initialize database on import
init_db()
