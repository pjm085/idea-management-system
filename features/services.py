"""Database-facing helpers for projects, ideas, taxonomy, notes and connections."""

from __future__ import annotations

from typing import Any

# ===== DATABASE QUERY HELPERS =====


def owned_project(connection, project_id: int, user_id: int):
    return connection.execute(
        "SELECT * FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()


def owned_idea(connection, idea_id: int, user_id: int):
    return connection.execute(
        "SELECT * FROM ideas WHERE id = ? AND user_id = ?",
        (idea_id, user_id),
    ).fetchone()


def list_tags_for_idea(connection, idea_id: int):
    return list_tags_for_ideas(connection, [idea_id]).get(idea_id, [])


def list_tags_for_ideas(connection, idea_ids):
    """Load tags for many ideas in one query instead of one query per idea."""
    grouped = {int(idea_id): [] for idea_id in idea_ids}
    if not grouped:
        return grouped

    ids = list(grouped.keys())
    chunk_size = 400
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start : start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"""SELECT it.idea_id, t.id, t.name FROM tags t
               JOIN idea_tags it ON it.tag_id = t.id
               WHERE it.idea_id IN ({placeholders})
               ORDER BY t.name COLLATE NOCASE""",
            chunk,
        ).fetchall()
        for row in rows:
            grouped[int(row["idea_id"])].append({"id": row["id"], "name": row["name"]})
    return grouped


def replace_idea_tags(connection, idea_id: int, user_id: int, raw_tags: str) -> None:
    if not owned_idea(connection, idea_id, user_id):
        raise ValueError("That idea does not belong to your account.")
    names = []
    seen = set()
    for item in (raw_tags or "").split(","):
        name = item.strip().lstrip("#")
        key = name.casefold()
        if name and key not in seen:
            names.append(name[:40])
            seen.add(key)
    connection.execute("DELETE FROM idea_tags WHERE idea_id = ?", (idea_id,))
    for name in names[:20]:
        connection.execute(
            "INSERT OR IGNORE INTO tags(user_id, name) VALUES (?, ?)",
            (user_id, name),
        )
        tag = connection.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ? COLLATE NOCASE",
            (user_id, name),
        ).fetchone()
        if tag:
            connection.execute(
                "INSERT OR IGNORE INTO idea_tags(idea_id, tag_id) VALUES (?, ?)",
                (idea_id, tag["id"]),
            )


def list_ideas(
    connection,
    user_id: int,
    *,
    project_id=None,
    unorganised=False,
    category_id=None,
    sort="newest",
    search=None,
):
    where = ["i.user_id = ?"]
    params: list[Any] = [user_id]
    if project_id is not None:
        where.append("i.project_id = ?")
        params.append(project_id)
    elif unorganised:
        where.append("i.project_id IS NULL")
    if category_id == "none":
        where.append("i.category_id IS NULL")
    elif category_id not in (None, "", "all"):
        try:
            where.append("i.category_id = ?")
            params.append(int(category_id))
        except (TypeError, ValueError):
            pass
    if search:

        query = search.strip()
        escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        needle = f"%{escaped}%"
        where.append("""(
            i.title LIKE ? ESCAPE '!'
            OR i.content LIKE ? ESCAPE '!'
            OR COALESCE(p.name, '') LIKE ? ESCAPE '!'
            OR EXISTS(
                SELECT 1 FROM idea_tags it JOIN tags t ON t.id = it.tag_id
                WHERE it.idea_id = i.id AND t.user_id = i.user_id
                  AND t.name LIKE ? ESCAPE '!'
            )
        )""")
        params.extend([needle, needle, needle, needle])
    order = "ASC" if sort == "oldest" else "DESC"
    rows = connection.execute(
        f"""SELECT i.*, p.name AS project_name, c.name AS category_name
            FROM ideas i
            LEFT JOIN projects p ON p.id = i.project_id AND p.user_id = i.user_id
            LEFT JOIN categories c ON c.id = i.category_id AND c.user_id = i.user_id
            WHERE {' AND '.join(where)}
            ORDER BY i.created_at {order}, i.id {order}""",
        params,
    ).fetchall()
    ideas = [dict(row) for row in rows]
    tags_by_idea = list_tags_for_ideas(connection, [item["id"] for item in ideas])
    for item in ideas:
        item["tags"] = tags_by_idea.get(item["id"], [])
    return ideas


def insert_idea(
    connection,
    user_id: int,
    project_id,
    title: str,
    content: str,
    category_id,
    tags: str,
    capture_method="project",
):
    cursor = connection.execute(
        """INSERT INTO ideas(user_id, project_id, category_id, title, content, capture_method)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, project_id, category_id, title, content, capture_method),
    )
    idea_id = cursor.lastrowid
    replace_idea_tags(connection, idea_id, user_id, tags)
    return idea_id


def user_counts(connection, user_id: int):
    return {
        "projects": connection.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id = ?", (user_id,)
        ).fetchone()[0],
        "ideas": connection.execute(
            "SELECT COUNT(*) FROM ideas WHERE user_id = ?", (user_id,)
        ).fetchone()[0],
        "unorganised": connection.execute(
            "SELECT COUNT(*) FROM ideas WHERE user_id = ? AND project_id IS NULL",
            (user_id,),
        ).fetchone()[0],
        "notes": connection.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ?", (user_id,)
        ).fetchone()[0],
    }


def list_projects(connection, user_id: int):
    return connection.execute(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM ideas i WHERE i.project_id = p.id AND i.user_id = p.user_id) AS idea_count
           FROM projects p WHERE p.user_id = ?
           ORDER BY p.created_at DESC, p.id DESC""",
        (user_id,),
    ).fetchall()
