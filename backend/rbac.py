"""
Role-Based Access Control (RBAC) for ATS.

Provides user/role management and permission enforcement.
Uses a simple SQLite backend for easy self-hosting.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import sqlite3
import hashlib

logger = logging.getLogger(__name__)

# Initialize SQLite for RBAC
RBAC_DB = "./data/rbac.db"


def _init_rbac_db():
    """Initialize RBAC database."""
    Path(RBAC_DB).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(RBAC_DB) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT,
                role TEXT DEFAULT 'recruiter',
                created_at TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                role_name TEXT UNIQUE NOT NULL,
                description TEXT,
                permissions_json TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_username ON users(username)
        """
        )
        conn.commit()

        # Create default roles
        _create_default_roles()
        logger.info(f"RBAC database initialized at {RBAC_DB}")


def _create_default_roles():
    """Create default roles if they don't exist."""
    default_roles = {
        "admin": {
            "description": "Full system access",
            "permissions": [
                "upload_cv",
                "search_cv",
                "parse_jd",
                "rank_candidates",
                "export_results",
                "view_analytics",
                "manage_users",
                "manage_settings",
            ],
        },
        "recruiter": {
            "description": "Recruit and search candidates",
            "permissions": [
                "upload_cv",
                "search_cv",
                "parse_jd",
                "rank_candidates",
                "export_results",
                "view_analytics",
            ],
        },
        "viewer": {
            "description": "Read-only access",
            "permissions": [
                "search_cv",
                "view_analytics",
            ],
        },
    }

    with sqlite3.connect(RBAC_DB) as conn:
        cursor = conn.cursor()
        for role_name, role_data in default_roles.items():
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO roles (role_id, role_name, description, permissions_json)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        role_name,
                        role_name,
                        role_data["description"],
                        json.dumps(role_data["permissions"]),
                    ),
                )
                conn.commit()
            except Exception as e:
                logger.debug(f"Role {role_name} may already exist: {e}")


# Initialize on import
_init_rbac_db()


def _hash_password(password: str) -> str:
    """Hash password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(
    username: str,
    email: str,
    password: str,
    role: str = "recruiter",
) -> Optional[str]:
    """Create a new user.

    Args:
        username: Unique username
        email: Email address
        password: Plain text password (will be hashed)
        role: 'admin', 'recruiter', or 'viewer'

    Returns:
        user_id if successful, None if failed
    """
    try:
        user_id = username
        password_hash = _hash_password(password)
        created_at = __import__("datetime").datetime.utcnow().isoformat()

        with sqlite3.connect(RBAC_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, username, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (user_id, username, email, password_hash, role, created_at),
            )
            conn.commit()
        logger.info(f"User {username} created with role {role}")
        return user_id
    except sqlite3.IntegrityError:
        logger.warning(f"User {username} already exists")
        return None
    except Exception as e:
        logger.error(f"Failed to create user {username}: {e}")
        return None


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user and return user info if successful.

    Args:
        username: Username
        password: Plain text password

    Returns:
        User dict {user_id, username, email, role} if successful, None otherwise
    """
    try:
        password_hash = _hash_password(password)

        with sqlite3.connect(RBAC_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, username, email, role, is_active
                FROM users WHERE username = ? AND password_hash = ?
            """,
                (username, password_hash),
            )
            row = cursor.fetchone()

        if not row:
            logger.warning(f"Authentication failed for {username}")
            return None

        user_id, username, email, role, is_active = row
        if not is_active:
            logger.warning(f"User {username} is inactive")
            return None

        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "role": role,
        }
    except Exception as e:
        logger.error(f"Authentication error for {username}: {e}")
        return None


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user info by ID."""
    try:
        with sqlite3.connect(RBAC_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, username, email, role, is_active
                FROM users WHERE user_id = ?
            """,
                (user_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        user_id, username, email, role, is_active = row
        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "role": role,
            "is_active": is_active,
        }
    except Exception as e:
        logger.error(f"Failed to get user {user_id}: {e}")
        return None


def get_user_permissions(user_id: str) -> List[str]:
    """Get list of permissions for a user."""
    try:
        user = get_user(user_id)
        if not user:
            return []

        with sqlite3.connect(RBAC_DB) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT permissions_json FROM roles WHERE role_name = ?
            """,
                (user["role"],),
            )
            row = cursor.fetchone()

        if not row:
            return []

        permissions_json = row[0]
        return json.loads(permissions_json)
    except Exception as e:
        logger.error(f"Failed to get permissions for {user_id}: {e}")
        return []


def has_permission(user_id: str, permission: str) -> bool:
    """Check if user has a specific permission."""
    permissions = get_user_permissions(user_id)
    return permission in permissions


def list_users(role: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """List users, optionally filtered by role."""
    try:
        with sqlite3.connect(RBAC_DB) as conn:
            cursor = conn.cursor()
            if role:
                cursor.execute(
                    """
                    SELECT user_id, username, email, role, is_active
                    FROM users WHERE role = ? LIMIT ?
                """,
                    (role, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT user_id, username, email, role, is_active
                    FROM users LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()

        users = []
        for user_id, username, email, role, is_active in rows:
            users.append(
                {
                    "user_id": user_id,
                    "username": username,
                    "email": email,
                    "role": role,
                    "is_active": is_active,
                }
            )
        return users
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        return []


def create_default_admin(username: str = "admin", password: str = "admin123") -> Optional[str]:
    """Create default admin user (use for initial setup only)."""
    existing = list_users(role="admin")
    if existing:
        logger.info("Admin user already exists")
        return existing[0]["user_id"]

    return create_user(username, f"{username}@localhost", password, role="admin")
