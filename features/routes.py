"""Flask routes for the fully functional manual V1 feature set."""

from __future__ import annotations

from functools import wraps
import sqlite3
from hmac import compare_digest

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database import NOTE_COLORS, get_db_connection, note_color_class
from .services import (
    insert_idea,
    list_ideas,
    list_projects,
    owned_idea,
    owned_project,
    replace_idea_tags,
)

features_bp = Blueprint("features", __name__)

# ===== FEATURE ROUTE HELPERS =====
# Provides shared access checks and form-processing helpers for feature pages.


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def require_csrf():
    token = request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    if not token or not expected or not compare_digest(token, expected):
        abort(400)


def uid():
    return int(session["user_id"])


def parse_category(connection, category_value, user_id):
    if not category_value:
        return None
    try:
        category_id = int(category_value)
    except (TypeError, ValueError):
        raise ValueError("Choose a valid category.")
    category = connection.execute(
        "SELECT id FROM categories WHERE id = ? AND user_id = ?",
        (category_id, user_id),
    ).fetchone()
    if not category:
        raise ValueError("That category does not belong to your account.")
    return category_id


def parse_project(connection, project_value, user_id, allow_empty=True):
    if not project_value:
        if allow_empty:
            return None
        raise ValueError("Choose a project.")
    try:
        project_id = int(project_value)
    except (TypeError, ValueError):
        raise ValueError("Choose a valid project.")
    project = connection.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not project:
        raise ValueError("That project does not belong to your account.")
    return project_id


def idea_form_values(connection, user_id):
    return {
        "projects": list_projects(connection, user_id),
        "categories": connection.execute(
            "SELECT * FROM categories WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (user_id,),
        ).fetchall(),
        "tags": connection.execute(
            "SELECT * FROM tags WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (user_id,),
        ).fetchall(),
    }


@features_bp.before_request
def require_login_for_feature_pages():
    if not session.get("user_id"):
        return redirect(url_for("login"))


# ===== PROJECT MANAGEMENT =====
# Handles project creation, renaming, deletion, and project detail views.


@features_bp.get("/projects")
@login_required
def projects():
    connection = get_db_connection()
    try:
        project_rows = list_projects(connection, uid())
        unorganised_count = connection.execute(
            "SELECT COUNT(*) FROM ideas WHERE user_id = ? AND project_id IS NULL",
            (uid(),),
        ).fetchone()[0]
        total_ideas = connection.execute(
            "SELECT COUNT(*) FROM ideas WHERE user_id = ?", (uid(),)
        ).fetchone()[0]
    finally:
        connection.close()
    return render_template(
        "projects.html",
        projects=project_rows,
        unorganised_count=unorganised_count,
        total_ideas=total_ideas,
    )


@features_bp.post("/projects/create")
@login_required
def create_project():
    require_csrf()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Project name is required.", "error")
        return redirect(url_for("features.projects"))
    if len(name) > 100:
        flash("Project names must be 100 characters or fewer.", "error")
        return redirect(url_for("features.projects"))
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO projects(user_id, name) VALUES (?, ?)", (uid(), name)
        )
        connection.commit()
        project_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("A project with that name already exists.", "error")
        return redirect(url_for("features.projects"))
    finally:
        connection.close()
    flash("Project created.", "success")
    return redirect(url_for("features.project_detail", project_id=project_id))


@features_bp.post("/projects/<int:project_id>/rename")
@login_required
def rename_project(project_id):
    require_csrf()
    name = request.form.get("name", "").strip()
    source = request.form.get("source", "detail")
    destination = (
        url_for("features.projects")
        if source == "list"
        else url_for("features.project_detail", project_id=project_id)
    )
    if not name:
        flash("Project name is required.", "error")
        return redirect(destination)
    if len(name) > 100:
        flash("Project names must be 100 characters or fewer.", "error")
        return redirect(destination)
    connection = get_db_connection()
    try:
        project = owned_project(connection, project_id, uid())
        if not project:
            abort(404)
        connection.execute(
            "UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (name, project_id, uid()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("A project with that name already exists.", "error")
        return redirect(destination)
    finally:
        connection.close()
    flash("Project renamed.", "success")
    return redirect(destination)


@features_bp.post("/projects/<int:project_id>/delete")
@login_required
def delete_project(project_id):
    require_csrf()
    source = request.form.get("source", "list")
    connection = get_db_connection()
    try:
        project = owned_project(connection, project_id, uid())
        if not project:
            abort(404)

        connection.execute(
            "UPDATE ideas SET project_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE project_id = ? AND user_id = ?",
            (project_id, uid()),
        )

        connection.execute(
            "DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, uid())
        )
        connection.commit()
    finally:
        connection.close()
    flash("Project deleted. Its ideas are now in Unorganised Ideas.", "success")
    if source == "detail":
        return redirect(url_for("features.projects"))
    return redirect(url_for("features.projects"))


@features_bp.get("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    sort = request.args.get("sort", "newest")
    if sort not in {"newest", "oldest"}:
        sort = "newest"
    category_filter = request.args.get("category", "all")
    tab = request.args.get("tab", "ideas")
    if tab not in {"ideas", "graph"}:
        tab = "ideas"
    connection = get_db_connection()
    try:
        project = owned_project(connection, project_id, uid())
        if not project:
            abort(404)
        all_ideas = list_ideas(connection, uid(), project_id=project_id, sort=sort)
        total_idea_count = len(all_ideas)
        ideas = list_ideas(
            connection,
            uid(),
            project_id=project_id,
            category_id=category_filter if tab == "ideas" else "all",
            sort=sort,
        )
        categories = connection.execute(
            "SELECT * FROM categories WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (uid(),),
        ).fetchall()
        graph_edges = [
            dict(row)
            for row in connection.execute(
                """SELECT c.id, c.idea_low_id, c.idea_high_id, c.description,
                      a.title AS title_a, b.title AS title_b
               FROM connections c
               JOIN ideas a ON a.id = c.idea_low_id AND a.user_id = c.user_id
               JOIN ideas b ON b.id = c.idea_high_id AND b.user_id = c.user_id
               WHERE c.project_id = ? AND c.user_id = ? ORDER BY c.id""",
                (project_id, uid()),
            ).fetchall()
        ]
        graph_nodes = [
            {
                "id": idea["id"],
                "title": idea["title"],
                "edit_url": url_for("features.edit_idea", idea_id=idea["id"]),
            }
            for idea in all_ideas
        ]
        form_values = idea_form_values(connection, uid())
    finally:
        connection.close()
    return render_template(
        "project_detail.html",
        project=project,
        ideas=ideas,
        sort=sort,
        category_filter=category_filter,
        tab=tab,
        graph_edges=graph_edges,
        graph_nodes=graph_nodes,
        all_ideas=all_ideas,
        total_idea_count=total_idea_count,
        **form_values,
    )


@features_bp.post("/projects/<int:project_id>/ideas/create")
@login_required
def add_project_idea(project_id):
    require_csrf()
    connection = get_db_connection()
    try:
        if not owned_project(connection, project_id, uid()):
            abort(404)
        idea_id = create_idea_from_form(
            connection, uid(), request.form, force_project=project_id, quick=False
        )
        connection.commit()
    except (ValueError, sqlite3.IntegrityError) as error:
        connection.rollback()
        flash(
            (
                str(error)
                if isinstance(error, ValueError)
                else "The idea could not be saved."
            ),
            "error",
        )
        return redirect(
            url_for("features.project_detail", project_id=project_id, tab="ideas")
        )
    finally:
        connection.close()
    flash("Idea added to the project.", "success")
    return redirect(
        url_for("features.project_detail", project_id=project_id, tab="ideas")
    )


# ===== IDEA MANAGEMENT =====
# Saves ideas, supports quick capture, and keeps project and category data consistent.


def create_idea_from_form(connection, user_id, form, force_project=None, quick=False):
    content = form.get("content", "").strip()
    title = form.get("title", "").strip()
    if quick:
        if not content:
            raise ValueError("Write your thought before saving it.")

        title = next(
            (line.strip() for line in content.splitlines() if line.strip()), ""
        )[:120]
    elif not title and content:
        title = next(
            (line.strip() for line in content.splitlines() if line.strip()), ""
        )[:120]
    if not title and not content:
        raise ValueError("Enter an idea title or its content.")
    if not title:
        title = "Untitled idea"
    if len(title) > 120:
        raise ValueError("Idea titles must be 120 characters or fewer.")
    if len(content) > 12000:
        raise ValueError("Idea content must be 12,000 characters or fewer.")
    project_id = (
        force_project
        if force_project is not None
        else parse_project(connection, form.get("project_id", ""), user_id)
    )
    category_id = parse_category(connection, form.get("category_id", ""), user_id)
    return insert_idea(
        connection,
        user_id,
        project_id,
        title,
        content,
        category_id,
        form.get("tags", ""),
        capture_method="quick" if quick else "project",
    )


@features_bp.route("/quick-idea", methods=["GET", "POST"])
@login_required
def quick_idea():
    if request.method == "POST":
        require_csrf()
        connection = get_db_connection()
        try:
            idea_id = create_idea_from_form(connection, uid(), request.form, quick=True)
            idea = connection.execute(
                "SELECT project_id FROM ideas WHERE id = ? AND user_id = ?",
                (idea_id, uid()),
            ).fetchone()
            connection.commit()
        except (ValueError, sqlite3.IntegrityError) as error:
            connection.rollback()
            flash(
                (
                    str(error)
                    if isinstance(error, ValueError)
                    else "The idea could not be saved."
                ),
                "error",
            )
            return redirect(url_for("features.quick_idea"))
        finally:
            connection.close()
        flash("Idea saved.", "success")
        if idea and idea["project_id"]:
            return redirect(
                url_for("features.project_detail", project_id=idea["project_id"])
            )
        return redirect(url_for("features.unorganised_ideas"))
    connection = get_db_connection()
    try:
        form_values = idea_form_values(connection, uid())
    finally:
        connection.close()
    return render_template("quick_idea.html", **form_values)


@features_bp.get("/unorganised-ideas")
@login_required
def unorganised_ideas():
    sort = request.args.get("sort", "newest")
    if sort not in {"newest", "oldest"}:
        sort = "newest"
    connection = get_db_connection()
    try:
        ideas = list_ideas(connection, uid(), unorganised=True, sort=sort)
    finally:
        connection.close()
    return render_template("unorganised_ideas.html", ideas=ideas, sort=sort)


@features_bp.route("/ideas/<int:idea_id>/edit", methods=["GET", "POST"])
@login_required
def edit_idea(idea_id):
    connection = get_db_connection()
    try:
        idea = owned_idea(connection, idea_id, uid())
        if not idea:
            abort(404)
        if request.method == "POST":
            require_csrf()
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            if not title and content:
                title = next(
                    (line.strip() for line in content.splitlines() if line.strip()), ""
                )[:120]
            if not title and not content:
                flash("Enter an idea title or its content.", "error")
                return redirect(url_for("features.edit_idea", idea_id=idea_id))
            if not title:
                title = "Untitled idea"
            if len(title) > 120 or len(content) > 12000:
                flash("Title or idea content exceeds the allowed length.", "error")
                return redirect(url_for("features.edit_idea", idea_id=idea_id))
            try:
                new_project_id = parse_project(
                    connection, request.form.get("project_id", ""), uid()
                )
                category_id = parse_category(
                    connection, request.form.get("category_id", ""), uid()
                )
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("features.edit_idea", idea_id=idea_id))
            old_project_id = idea["project_id"]
            connection.execute(
                """UPDATE ideas SET project_id = ?, category_id = ?, title = ?, content = ?,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?""",
                (new_project_id, category_id, title, content, idea_id, uid()),
            )
            replace_idea_tags(connection, idea_id, uid(), request.form.get("tags", ""))
            if old_project_id != new_project_id:
                connection.execute(
                    "DELETE FROM connections WHERE user_id = ? AND (idea_low_id = ? OR idea_high_id = ?)",
                    (uid(), idea_id, idea_id),
                )
            connection.commit()
            flash("Idea updated.", "success")
            if new_project_id:
                return redirect(
                    url_for("features.project_detail", project_id=new_project_id)
                )
            return redirect(url_for("features.unorganised_ideas"))
        form_values = idea_form_values(connection, uid())
        project_name_row = (
            connection.execute(
                "SELECT name FROM projects WHERE id = ? AND user_id = ?",
                (idea["project_id"], uid()),
            ).fetchone()
            if idea["project_id"]
            else None
        )
        tags = connection.execute(
            "SELECT t.name FROM tags t JOIN idea_tags it ON it.tag_id=t.id WHERE it.idea_id=? ORDER BY t.name COLLATE NOCASE",
            (idea_id,),
        ).fetchall()
        idea_dict = dict(idea)
        idea_dict["project_name"] = (
            project_name_row["name"] if project_name_row else None
        )
        idea_dict["tags_text"] = ", ".join(row["name"] for row in tags)
    finally:
        connection.close()
    return render_template("idea_edit.html", idea=idea_dict, **form_values)


@features_bp.post("/ideas/<int:idea_id>/delete")
@login_required
def delete_idea(idea_id):
    require_csrf()
    destination = request.form.get("next", "")
    connection = get_db_connection()
    try:
        idea = owned_idea(connection, idea_id, uid())
        if not idea:
            abort(404)
        connection.execute(
            "DELETE FROM ideas WHERE id = ? AND user_id = ?", (idea_id, uid())
        )
        connection.commit()
    finally:
        connection.close()
    flash("Idea permanently deleted.", "success")
    if destination == "search":
        return redirect(url_for("features.search"))
    if destination == "unorganised" or idea["project_id"] is None:
        return redirect(url_for("features.unorganised_ideas"))
    return redirect(url_for("features.project_detail", project_id=idea["project_id"]))


# ===== SEARCH AND TAXONOMY MANAGEMENT =====


@features_bp.get("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()[:200]
    sort = request.args.get("sort", "newest")
    if sort not in {"newest", "oldest"}:
        sort = "newest"
    idea_results = []
    project_results = []
    if query:
        connection = get_db_connection()
        try:
            idea_results = list_ideas(connection, uid(), sort=sort, search=query)
            escaped_query = (
                query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            )
            project_needle = f"%{escaped_query}%"
            direction = "ASC" if sort == "oldest" else "DESC"
            project_results = connection.execute(
                """SELECT p.*,
                   (SELECT COUNT(*) FROM ideas i WHERE i.project_id=p.id AND i.user_id=p.user_id) AS idea_count
                   FROM projects p WHERE p.user_id=? AND p.name LIKE ? ESCAPE '!'
                   ORDER BY p.created_at """ + direction + ", p.id " + direction,
                (uid(), project_needle),
            ).fetchall()
        finally:
            connection.close()
    return render_template(
        "search.html",
        query=query,
        sort=sort,
        ideas=idea_results,
        project_results=project_results,
    )


@features_bp.post("/profile/categories/create")
@login_required
def create_category():
    require_csrf()
    name = request.form.get("name", "").strip()
    if not name or len(name) > 60:
        flash("Category names must contain 1–60 characters.", "error")
        return redirect(url_for("profile") + "#categories-tags")
    connection = get_db_connection()
    try:
        connection.execute(
            "INSERT INTO categories(user_id, name) VALUES (?, ?)", (uid(), name)
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That category already exists.", "error")
    else:
        flash("Category created.", "success")
    finally:
        connection.close()
    return redirect(url_for("profile") + "#categories-tags")


@features_bp.post("/profile/categories/<int:category_id>/rename")
@login_required
def rename_category(category_id):
    require_csrf()
    name = request.form.get("name", "").strip()
    if not name or len(name) > 60:
        flash("Category names must contain 1–60 characters.", "error")
        return redirect(url_for("profile") + "#categories-tags")
    connection = get_db_connection()
    try:
        existing = connection.execute(
            "SELECT id FROM categories WHERE id=? AND user_id=?", (category_id, uid())
        ).fetchone()
        if not existing:
            abort(404)
        connection.execute(
            "UPDATE categories SET name=? WHERE id=? AND user_id=?",
            (name, category_id, uid()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That category already exists.", "error")
    else:
        flash("Category renamed.", "success")
    finally:
        connection.close()
    return redirect(url_for("profile") + "#categories-tags")


@features_bp.post("/profile/categories/<int:category_id>/delete")
@login_required
def delete_category(category_id):
    require_csrf()
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "DELETE FROM categories WHERE id=? AND user_id=?", (category_id, uid())
        )
        if cursor.rowcount == 0:
            abort(404)
        connection.commit()
    finally:
        connection.close()
    flash("Category deleted. Its ideas are now uncategorised.", "success")
    return redirect(url_for("profile") + "#categories-tags")


@features_bp.post("/profile/tags/create")
@login_required
def create_tag():
    require_csrf()
    name = request.form.get("name", "").strip().lstrip("#")
    if not name or len(name) > 40:
        flash("Tag names must contain 1–40 characters.", "error")
        return redirect(url_for("profile") + "#categories-tags")
    connection = get_db_connection()
    try:
        connection.execute(
            "INSERT INTO tags(user_id, name) VALUES (?, ?)", (uid(), name)
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That tag already exists.", "error")
    else:
        flash("Tag created.", "success")
    finally:
        connection.close()
    return redirect(url_for("profile") + "#categories-tags")


@features_bp.post("/profile/tags/<int:tag_id>/rename")
@login_required
def rename_tag(tag_id):
    require_csrf()
    name = request.form.get("name", "").strip().lstrip("#")
    if not name or len(name) > 40:
        flash("Tag names must contain 1–40 characters.", "error")
        return redirect(url_for("profile") + "#categories-tags")
    connection = get_db_connection()
    try:
        existing = connection.execute(
            "SELECT id FROM tags WHERE id=? AND user_id=?", (tag_id, uid())
        ).fetchone()
        if not existing:
            abort(404)
        connection.execute(
            "UPDATE tags SET name=? WHERE id=? AND user_id=?", (name, tag_id, uid())
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That tag already exists.", "error")
    else:
        flash("Tag renamed.", "success")
    finally:
        connection.close()
    return redirect(url_for("profile") + "#categories-tags")


@features_bp.post("/profile/tags/<int:tag_id>/delete")
@login_required
def delete_tag(tag_id):
    require_csrf()
    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "DELETE FROM tags WHERE id=? AND user_id=?", (tag_id, uid())
        )
        if cursor.rowcount == 0:
            abort(404)
        connection.commit()
    finally:
        connection.close()
    flash("Tag deleted.", "success")
    return redirect(url_for("profile") + "#categories-tags")


# ===== REMINDER NOTES =====


@features_bp.post("/notes/create")
@login_required
def create_note():
    """Create a reminder note; return JSON for the dashboard's AJAX flow."""
    require_csrf()
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )
    content = request.form.get("content", "").strip()
    if not content or len(content) > 1000:
        message = "Reminder notes must contain 1–1,000 characters."
        if wants_json:
            return jsonify(success=False, error=message), 400
        flash(message, "error")
        return redirect(url_for("dashboard"))

    connection = get_db_connection()
    try:
        note_count = connection.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ?", (uid(),)
        ).fetchone()[0]
        note_color = NOTE_COLORS[note_count % len(NOTE_COLORS)]
        cursor = connection.execute(
            "INSERT INTO notes(user_id, content, color) VALUES (?, ?, ?)",
            (uid(), content, note_color),
        )
        note_id = cursor.lastrowid
        note = connection.execute(
            "SELECT id, content, color, created_at FROM notes WHERE id=? AND user_id=?",
            (note_id, uid()),
        ).fetchone()
        connection.commit()
    finally:
        connection.close()

    if wants_json:
        created_at = str(note["created_at"] or "")
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            date_label = parsed.strftime("%d %b %Y").lstrip("0")
        except (TypeError, ValueError):
            date_label = created_at[:10]
        return (
            jsonify(
                success=True,
                message="Reminder note saved.",
                note={
                    "id": note["id"],
                    "content": note["content"],
                    "color": note["color"],
                    "color_class": note_color_class(note["color"]),
                    "created_at": created_at,
                    "date_label": date_label,
                },
            ),
            201,
        )

    flash("Reminder note saved.", "success")
    return redirect(url_for("dashboard"))


@features_bp.post("/notes/<int:note_id>/edit")
@login_required
def edit_note(note_id):
    require_csrf()
    content = request.form.get("content", "").strip()
    if not content or len(content) > 1000:
        flash("Reminder notes must contain 1–1,000 characters.", "error")
        return redirect(url_for("dashboard"))
    connection = get_db_connection()
    try:
        existing = connection.execute(
            "SELECT id FROM notes WHERE id=? AND user_id=?",
            (note_id, uid()),
        ).fetchone()
        if not existing:
            abort(404)
        connection.execute(
            "UPDATE notes SET content=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (content, note_id, uid()),
        )
        connection.commit()
    finally:
        connection.close()
    flash("Reminder note updated.", "success")
    return redirect(url_for("dashboard"))


@features_bp.post("/notes/<int:note_id>/delete")
@login_required
def delete_note(note_id):
    require_csrf()
    connection = get_db_connection()
    try:
        existing = connection.execute(
            "SELECT id FROM notes WHERE id=? AND user_id=?",
            (note_id, uid()),
        ).fetchone()
        if not existing:
            abort(404)
        connection.execute(
            "DELETE FROM notes WHERE id=? AND user_id=?", (note_id, uid())
        )
        connection.commit()
    finally:
        connection.close()
    flash("Reminder note deleted.", "success")
    return redirect(url_for("dashboard"))


# ===== IDEA CONNECTIONS =====


@features_bp.post("/projects/<int:project_id>/connections/create")
@login_required
def create_connection(project_id):
    require_csrf()
    first = request.form.get("idea_a", "")
    second = request.form.get("idea_b", "")
    description = request.form.get("description", "").strip()[:1000]
    connection = get_db_connection()
    try:
        project = owned_project(connection, project_id, uid())
        if not project:
            abort(404)
        try:
            first_id, second_id = int(first), int(second)
        except (TypeError, ValueError):
            flash("Choose two ideas to connect.", "error")
            return redirect(
                url_for("features.project_detail", project_id=project_id, tab="graph")
            )
        if first_id == second_id:
            flash("An idea cannot be connected to itself.", "error")
            return redirect(
                url_for("features.project_detail", project_id=project_id, tab="graph")
            )
        idea_ids = connection.execute(
            "SELECT id FROM ideas WHERE user_id=? AND project_id=? AND id IN (?, ?)",
            (uid(), project_id, first_id, second_id),
        ).fetchall()
        if len(idea_ids) != 2:
            flash("Both ideas must belong to this project.", "error")
            return redirect(
                url_for("features.project_detail", project_id=project_id, tab="graph")
            )
        low, high = sorted((first_id, second_id))
        connection.execute(
            "INSERT INTO connections(user_id, project_id, idea_low_id, idea_high_id, description) VALUES (?, ?, ?, ?, ?)",
            (uid(), project_id, low, high, description),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("Those ideas are already connected.", "error")
        return redirect(
            url_for("features.project_detail", project_id=project_id, tab="graph")
        )
    finally:
        connection.close()
    flash("Connection created.", "success")
    return redirect(
        url_for("features.project_detail", project_id=project_id, tab="graph")
    )


@features_bp.post("/connections/<int:connection_id>/edit")
@login_required
def edit_connection(connection_id):
    require_csrf()
    description = request.form.get("description", "").strip()[:1000]
    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT * FROM connections WHERE id=? AND user_id=?", (connection_id, uid())
        ).fetchone()
        if not row:
            abort(404)
        connection.execute(
            "UPDATE connections SET description=? WHERE id=? AND user_id=?",
            (description, connection_id, uid()),
        )
        connection.commit()
        project_id = row["project_id"]
    finally:
        connection.close()
    flash("Connection updated.", "success")
    return redirect(
        url_for("features.project_detail", project_id=project_id, tab="graph")
    )


@features_bp.post("/connections/<int:connection_id>/delete")
@login_required
def delete_connection(connection_id):
    require_csrf()
    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT project_id FROM connections WHERE id=? AND user_id=?",
            (connection_id, uid()),
        ).fetchone()
        if not row:
            abort(404)
        project_id = row["project_id"]
        connection.execute(
            "DELETE FROM connections WHERE id=? AND user_id=?", (connection_id, uid())
        )
        connection.commit()
    finally:
        connection.close()
    flash("Connection deleted.", "success")
    return redirect(
        url_for("features.project_detail", project_id=project_id, tab="graph")
    )


# ===== FEATURE HELP PAGE =====


@features_bp.get("/help")
@login_required
def help_page():
    return render_template("help.html")
