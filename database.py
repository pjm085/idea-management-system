import os
import sqlite3
from pathlib import Path

# ===== DATABASE CONFIGURATION =====
# Sets the project database path and the default note colour mapping.

BASE_DIR = Path(__file__).resolve().parent

DATABASE = Path(
    os.environ.get("JO_DATABASE_PATH", str(BASE_DIR / "jo_helper.db"))
).expanduser()

NOTE_COLOR_CLASSES = {
    "#F6E7A8": "note-color-yellow",
    "#DCE7CB": "note-color-sage",
    "#E7DCEF": "note-color-lavender",
    "#F3D5C5": "note-color-peach",
    "#CFE3E6": "note-color-blue",
}


def note_color_class(color):
    """Return a safe, allow-listed CSS class for a stored note color."""
    normalized = str(color or "").strip().upper()
    return NOTE_COLOR_CLASSES.get(normalized, "note-color-sage")


NOTE_COLORS = (
    "#F6E7A8",
    "#DCE7CB",
    "#E7DCEF",
    "#F3D5C5",
    "#CFE3E6",
)

# ===== DATABASE CONNECTION =====
# Creates a reliable SQLite connection with the correct foreign-key settings.


def get_db_connection():
    """
    Create and return a SQLite database connection.

    Features:
    - Uses JO_DATABASE_PATH when set, otherwise the database file beside this file.
    - Waits up to 10 seconds if the database is locked.
    - Allows columns to be accessed by name.
    - Enables foreign key constraints for each connection.
    """

    DATABASE.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        str(DATABASE),
        timeout=10,
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ===== DATABASE INITIALISATION =====
# Creates the main tables used by users, projects, ideas, notes, and related data.


def init_db():
    """
    Initialize the database and create required tables.

    Existing user records are preserved.

    Existing account records and legacy columns are preserved.
    """

    connection = get_db_connection()

    try:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        connection.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, name COLLATE NOCASE)
            );

            CREATE INDEX IF NOT EXISTS idx_projects_user_created
                ON projects(user_id, created_at DESC, id DESC);

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 60),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, name COLLATE NOCASE)
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 40),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, name COLLATE NOCASE)
            );

            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER,
                category_id INTEGER,
                title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
                content TEXT NOT NULL DEFAULT '',
                capture_method TEXT NOT NULL DEFAULT 'project',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ideas_user_created
                ON ideas(user_id, created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_ideas_project_created
                ON ideas(project_id, created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_ideas_category ON ideas(category_id);

            CREATE TABLE IF NOT EXISTS idea_tags (
                idea_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (idea_id, tag_id),
                FOREIGN KEY (idea_id) REFERENCES ideas(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                idea_low_id INTEGER NOT NULL,
                idea_high_id INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(idea_low_id < idea_high_id),
                UNIQUE(user_id, idea_low_id, idea_high_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (idea_low_id) REFERENCES ideas(id) ON DELETE CASCADE,
                FOREIGN KEY (idea_high_id) REFERENCES ideas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL CHECK(length(trim(content)) BETWEEN 1 AND 1000),
                color TEXT NOT NULL DEFAULT '#DCE7CB',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_notes_user_created
                ON notes(user_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_connections_project_user
                ON connections(project_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_idea_tags_tag
                ON idea_tags(tag_id);
            """)

        idea_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(ideas)").fetchall()
        }
        if "capture_method" not in idea_columns:
            connection.execute(
                "ALTER TABLE ideas ADD COLUMN capture_method TEXT NOT NULL DEFAULT 'project'"
            )

        note_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(notes)").fetchall()
        }
        if "color" not in note_columns:
            connection.execute(
                "ALTER TABLE notes ADD COLUMN color TEXT NOT NULL DEFAULT '#DCE7CB'"
            )
            existing_notes = connection.execute(
                "SELECT id, user_id FROM notes ORDER BY user_id, created_at, id"
            ).fetchall()
            user_note_counts = {}
            for note in existing_notes:
                color_index = user_note_counts.get(note["user_id"], 0) % len(
                    NOTE_COLORS
                )
                connection.execute(
                    "UPDATE notes SET color = ? WHERE id = ?",
                    (NOTE_COLORS[color_index], note["id"]),
                )
                user_note_counts[note["user_id"]] = (
                    user_note_counts.get(note["user_id"], 0) + 1
                )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()
