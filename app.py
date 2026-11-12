import os
import re
import secrets
import sqlite3
from datetime import datetime
from hmac import compare_digest
from pathlib import Path

from flask import (
    Flask,
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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection, init_db, note_color_class
from features.services import user_counts

# ===== APPLICATION STARTUP =====
# Initialises the Flask app and prepares the local instance directory.

BASE_DIR = Path(__file__).resolve().parent

INSTANCE_DIR = Path(
    os.environ.get("JO_INSTANCE_DIR", str(BASE_DIR / "instance"))
).expanduser()
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY_FILE = INSTANCE_DIR / "secret.key"

# ===== SECURITY CONFIGURATION =====
# Creates and loads the app secret key used for session protection.


def load_secret_key():
    """
    Load the Flask secret key.

    Production:
        Uses the SECRET_KEY environment variable.

    Local development:
        Creates a random secret key once and stores it
        inside instance/secret.key.
    """
    environment_secret = os.environ.get("SECRET_KEY")
    app_environment = os.environ.get("APP_ENV", "development").strip().lower()

    if environment_secret:
        return environment_secret

    if app_environment == "production":
        raise RuntimeError(
            "SECRET_KEY must be set in the environment when APP_ENV=production."
        )

    if SECRET_KEY_FILE.exists():
        secret = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()

        if len(secret) >= 32:
            return secret

    secret = secrets.token_hex(32)

    SECRET_KEY_FILE.write_text(
        secret,
        encoding="utf-8",
    )

    return secret


app = Flask(__name__)


@app.template_filter("note_date")
def format_note_date(value):
    """Format a saved reminder date like the reference sticky-note cards."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d %b %Y").lstrip("0")
    except (TypeError, ValueError):
        return str(value)[:10]


@app.template_filter("note_color_class")
def format_note_color_class(value):
    """Map a stored note palette value to a strict-CSP-safe CSS class."""
    return note_color_class(value)


IS_PRODUCTION = os.environ.get("APP_ENV", "development").lower() == "production"

app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)

# ===== RATE LIMITING =====
# Protects login and registration routes from repeated automated requests.

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
    enabled=os.environ.get("APP_ENV", "development").lower() != "testing",
)

# ===== DATABASE INITIALISATION =====
# Ensures the required SQLite tables exist before the app starts handling requests.
init_db()

# ===== INPUT VALIDATION =====
# Defines the validation rules used for user details and passwords.

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

NAME_MAX_LENGTH = 24
EMAIL_MAX_LENGTH = 254


PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 128

# ===== CSRF PROTECTION =====
# Generates and validates a token to protect form submissions from tampering.


def get_csrf_token():
    """
    Return the current session's CSRF token.

    If no token exists, create a random token and store
    it in the Flask session.
    """

    token = session.get("_csrf_token")

    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token

    return token


@app.context_processor
def inject_csrf_token():
    """
    Make csrf_token available inside all Jinja templates.
    """

    return {
        "csrf_token": get_csrf_token(),
    }


def validate_csrf():
    """
    Validate the CSRF token submitted by a POST request.
    """

    submitted_token = request.form.get(
        "csrf_token",
        "",
    )

    session_token = session.get(
        "_csrf_token",
        "",
    )

    if (
        not submitted_token
        or not session_token
        or not compare_digest(
            submitted_token,
            session_token,
        )
    ):
        abort(400)


@app.context_processor
def inject_current_user():
    """
    Make the logged-in user's basic details available
    to all Jinja templates.
    """

    user = None
    user_id = session.get("user_id")

    if user_id:
        connection = get_db_connection()

        try:
            user = connection.execute(
                """
                SELECT id, name, email
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            recent_projects = connection.execute(
                """SELECT id, name, created_at FROM projects
                   WHERE user_id = ? ORDER BY created_at DESC, id DESC
                   LIMIT 8""",
                (user_id,),
            ).fetchall()
            sidebar_project_count = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
        except sqlite3.OperationalError:

            recent_projects = []
            sidebar_project_count = 0
        finally:
            connection.close()
    else:
        recent_projects = []
        sidebar_project_count = 0

    return {
        "current_user": user,
        "recent_projects": recent_projects,
        "sidebar_project_count": sidebar_project_count,
    }


DUMMY_PASSWORD_HASH = generate_password_hash("JO_HELPER_DUMMY_PASSWORD_FOR_TIMING")

# ===== RESPONSE SECURITY =====
# Adds protective HTTP headers to keep the app safer for browser-based use.


@app.after_request
def add_security_headers(response):
    """
    Add useful HTTP security headers to responses.
    """

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "img-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com "
        "https://cdn.jsdelivr.net; "
        "script-src 'self'; "
        "font-src 'self' https://fonts.gstatic.com "
        "https://cdn.jsdelivr.net"
    )

    if session.get("user_id") and not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"

    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


def wants_json_response():
    """Return True when the client asked for a JSON error payload."""
    accept_best = request.accept_mimetypes.best
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or accept_best == "application/json"
    )


def render_error_page(status_code, title, message):
    if wants_json_response():
        return jsonify(success=False, error=message), status_code
    return (
        render_template(
            "error.html",
            error_code=status_code,
            error_title=title,
            error_message=message,
        ),
        status_code,
    )


@app.errorhandler(400)
def bad_request(error):
    return render_error_page(
        400,
        "Invalid request",
        "Please refresh the page and try again.",
    )


@app.errorhandler(404)
def page_not_found(error):
    return render_error_page(
        404,
        "Page not found",
        "That page does not exist or you do not have access to it.",
    )


@app.errorhandler(429)
def too_many_requests(error):
    return render_error_page(
        429,
        "Too many attempts",
        "Please wait a minute and try again.",
    )


@app.errorhandler(500)
def internal_server_error(error):
    return render_error_page(
        500,
        "Something went wrong",
        "Please try again in a moment.",
    )


# ===== USER AUTHENTICATION =====
# This section handles login, registration, redirect rules, and access checks.


@app.route("/")
def home():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def login():

    if request.method == "GET" and "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        validate_csrf()

        email = (
            request.form.get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            "",
        )

        if (
            not email
            or len(email) > EMAIL_MAX_LENGTH
            or not EMAIL_RE.fullmatch(email)
            or len(password) > PASSWORD_MAX_LENGTH
        ):
            return (
                render_template(
                    "login.html",
                    error="Invalid email or password.",
                    email=email if EMAIL_RE.fullmatch(email) else "",
                ),
                400,
            )

        connection = get_db_connection()

        try:
            user = connection.execute(
                """
                SELECT *
                FROM users
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

        finally:
            connection.close()

        if user is None:
            check_password_hash(
                DUMMY_PASSWORD_HASH,
                password,
            )

            return (
                render_template(
                    "login.html",
                    error="Invalid email or password.",
                    email=email,
                ),
                401,
            )

        if not check_password_hash(
            user["password"],
            password,
        ):
            return (
                render_template(
                    "login.html",
                    error="Invalid email or password.",
                    email=email,
                ),
                401,
            )

        session.clear()

        session["user_id"] = user["id"]

        session["_csrf_token"] = secrets.token_urlsafe(32)

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def register():

    if request.method == "GET" and "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        validate_csrf()

        name = request.form.get(
            "name",
            "",
        ).strip()

        email = (
            request.form.get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            "",
        )

        if not name:
            return (
                render_template(
                    "register.html",
                    error="Name is required.",
                    name=name,
                    email=email,
                ),
                400,
            )

        if len(name) > NAME_MAX_LENGTH:
            return (
                render_template(
                    "register.html",
                    error=f"Your name must be {NAME_MAX_LENGTH} characters or fewer.",
                    name=name[:NAME_MAX_LENGTH],
                    email=email,
                ),
                400,
            )

        if not email:
            return (
                render_template(
                    "register.html",
                    error="Email is required.",
                    name=name,
                    email=email,
                ),
                400,
            )

        if len(email) > EMAIL_MAX_LENGTH:
            return (
                render_template(
                    "register.html",
                    error="Email is too long.",
                    name=name,
                    email="",
                ),
                400,
            )

        if not EMAIL_RE.fullmatch(email):
            return (
                render_template(
                    "register.html",
                    error="Please enter a valid email address.",
                    name=name,
                    email=email,
                ),
                400,
            )

        if len(password) < PASSWORD_MIN_LENGTH:
            return (
                render_template(
                    "register.html",
                    error=(
                        "Password must be at least "
                        f"{PASSWORD_MIN_LENGTH} characters."
                    ),
                    name=name,
                    email=email,
                ),
                400,
            )

        if len(password) > PASSWORD_MAX_LENGTH:
            return (
                render_template(
                    "register.html",
                    error="Password is too long.",
                    name=name,
                    email=email,
                ),
                400,
            )

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()

        try:
            connection.execute(
                """
                INSERT INTO users (
                    name,
                    email,
                    password
                )
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    email,
                    hashed_password,
                ),
            )

            connection.commit()

        except sqlite3.IntegrityError as error:
            connection.rollback()

            if "UNIQUE constraint failed: users.email" in str(error):
                return (
                    render_template(
                        "register.html",
                        error="This email is already registered.",
                        name=name,
                        email=email,
                    ),
                    409,
                )

            raise

        finally:
            connection.close()

        flash("Account created. You can log in now.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ===== USER PROFILE =====
# Manages profile viewing and account settings such as updates and password reset.


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    try:
        user = connection.execute(
            """
            SELECT id, name, email, created_at
            FROM users
            WHERE id = ?
            """,
            (session["user_id"],),
        ).fetchone()

    finally:
        connection.close()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    member_since = user["created_at"] or "Unknown"

    try:
        member_since = (
            datetime.fromisoformat(str(user["created_at"]))
            .strftime("%B %d, %Y")
            .replace(" 0", " ")
        )

    except (ValueError, TypeError):
        pass

    connection = get_db_connection()
    try:
        profile_counts = user_counts(connection, session["user_id"])
        categories = connection.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM ideas i WHERE i.category_id=c.id AND i.user_id=c.user_id) AS idea_count
               FROM categories c WHERE c.user_id=? ORDER BY c.name COLLATE NOCASE""",
            (session["user_id"],),
        ).fetchall()
        tags = connection.execute(
            """SELECT t.*, (SELECT COUNT(*) FROM idea_tags it JOIN ideas i ON i.id=it.idea_id WHERE it.tag_id=t.id AND i.user_id=t.user_id) AS idea_count
               FROM tags t WHERE t.user_id=? ORDER BY t.name COLLATE NOCASE""",
            (session["user_id"],),
        ).fetchall()
    finally:
        connection.close()

    return render_template(
        "profile.html",
        user=user,
        member_since=member_since,
        profile_counts=profile_counts,
        categories=categories,
        tags=tags,
    )


@app.route("/profile/update", methods=["POST"])
def update_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    validate_csrf()

    user_id = session["user_id"]

    name = request.form.get(
        "name",
        "",
    ).strip()

    email = (
        request.form.get(
            "email",
            "",
        )
        .strip()
        .lower()
    )

    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("profile", _anchor="profile-edit-panel"))

    if len(name) > NAME_MAX_LENGTH:
        flash(
            f"Your name must be {NAME_MAX_LENGTH} characters or fewer.",
            "error",
        )
        return redirect(url_for("profile", _anchor="profile-edit-panel"))

    if not email or len(email) > EMAIL_MAX_LENGTH or not EMAIL_RE.fullmatch(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("profile", _anchor="profile-edit-panel"))

    connection = get_db_connection()

    try:
        user = connection.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("login"))

        duplicate_email = connection.execute(
            """
            SELECT id
            FROM users
            WHERE email = ? AND id != ?
            """,
            (email, user_id),
        ).fetchone()

        if duplicate_email:
            flash(
                "This email address is already used by another account.",
                "error",
            )
            return redirect(url_for("profile", _anchor="profile-edit-panel"))

        connection.execute(
            """
            UPDATE users
            SET name = ?, email = ?
            WHERE id = ?
            """,
            (
                name,
                email,
                user_id,
            ),
        )

        connection.commit()

    except sqlite3.IntegrityError:
        connection.rollback()

        flash(
            "This email address is already registered.",
            "error",
        )

        return redirect(url_for("profile", _anchor="profile-edit-panel"))

    finally:
        connection.close()

    flash("Profile updated successfully.", "success")

    return redirect(url_for("profile"))


@app.route("/profile/password", methods=["POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("login"))

    validate_csrf()

    current_password = request.form.get(
        "current_password",
        "",
    )

    new_password = request.form.get(
        "new_password",
        "",
    )

    confirm_password = request.form.get(
        "confirm_password",
        "",
    )

    if not current_password:
        flash("Enter your current password.", "password_error")
        return redirect(url_for("profile", _anchor="change-password"))

    if new_password != confirm_password:
        flash("The new passwords do not match.", "password_error")
        return redirect(url_for("profile", _anchor="change-password"))

    if len(new_password) < PASSWORD_MIN_LENGTH:
        flash(
            "The new password must contain at least "
            f"{PASSWORD_MIN_LENGTH} characters.",
            "password_error",
        )
        return redirect(url_for("profile", _anchor="change-password"))

    if len(new_password) > PASSWORD_MAX_LENGTH:
        flash("The new password is too long.", "password_error")
        return redirect(url_for("profile", _anchor="change-password"))

    connection = get_db_connection()

    try:
        user = connection.execute(
            """
            SELECT password
            FROM users
            WHERE id = ?
            """,
            (session["user_id"],),
        ).fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("login"))

        if not check_password_hash(
            user["password"],
            current_password,
        ):
            flash(
                "Your current password is incorrect.",
                "password_error",
            )
            return redirect(url_for("profile", _anchor="change-password"))

        connection.execute(
            """
            UPDATE users
            SET password = ?
            WHERE id = ?
            """,
            (
                generate_password_hash(new_password),
                session["user_id"],
            ),
        )

        connection.commit()

    finally:
        connection.close()

    flash("Password changed successfully.", "success")

    return redirect(url_for("profile"))


@app.route("/profile/delete-account", methods=["POST"])
def delete_account():
    """Permanently remove the authenticated account and all owned data."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    validate_csrf()
    user_id = session["user_id"]
    current_password = request.form.get("current_password", "")
    confirmation = request.form.get("confirmation", "")

    if confirmation != "DELETE":
        flash("Type DELETE in capital letters to confirm account deletion.", "error")
        return redirect(url_for("profile"))

    if not current_password:
        flash("Enter your current password to delete your account.", "error")
        return redirect(url_for("profile"))

    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT password FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("login"))

        if not check_password_hash(user["password"], current_password):
            flash(
                "Your current password is incorrect. Your account was not deleted.",
                "error",
            )
            return redirect(url_for("profile"))

        cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cursor.rowcount != 1:
            connection.rollback()
            flash("The account could not be found. No data was deleted.", "error")
            return redirect(url_for("profile"))
        connection.commit()
    except Exception:
        connection.rollback()
        current_app.logger.exception("Account deletion failed for user_id=%s", user_id)
        flash(
            "Account deletion failed. Your data has not been intentionally removed; please try again.",
            "error",
        )
        return redirect(url_for("profile"))
    finally:
        connection.close()

    session.clear()
    flash(
        "Your account and associated workspace data have been permanently deleted.",
        "success",
    )
    return redirect(url_for("login"))


# ===== DASHBOARD =====
# Displays the main user dashboard after a successful login.


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    try:
        counts = user_counts(connection, session["user_id"])
        notes = connection.execute(
            "SELECT * FROM notes WHERE user_id=? ORDER BY created_at DESC, id DESC",
            (session["user_id"],),
        ).fetchall()
    finally:
        connection.close()

    return render_template("dashboard.html", counts=counts, notes=notes)


@app.route("/logout", methods=["POST"])
def logout():

    validate_csrf()

    session.clear()

    return redirect(url_for("login"))


from features import register_feature_routes

register_feature_routes(app)


if __name__ == "__main__":

    debug_enabled = os.environ.get("FLASK_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    app.run(
        debug=debug_enabled,
        port=int(os.environ.get("PORT", "5000")),
    )
