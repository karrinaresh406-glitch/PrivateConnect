from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
import secrets
import base64
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)

# =========================================================
# APPLICATION SECURITY
# =========================================================

app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# =========================================================
# REAL-TIME CHAT
# =========================================================

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

# user_id -> number of active Socket.IO connections
active_users = {}

# =========================================================
# DATABASE
# =========================================================

DATABASE = os.path.join(BASE_DIR, "users.db")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov"}
PROFILE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def now_string():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def allowed_profile_picture(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in PROFILE_EXTENSIONS
    )


def sync_relationships(conn):
    """Repair/synchronize connection records from accepted requests and legacy friends."""
    cursor = conn.cursor()

    # Accepted connection requests must create a canonical connection row.
    accepted = cursor.execute("""
        SELECT sender_id, receiver_id
        FROM connection_requests
        WHERE status = 'accepted'
    """).fetchall()
    for row in accepted:
        a, b = sorted((int(row["sender_id"]), int(row["receiver_id"])))
        cursor.execute("""
            INSERT OR IGNORE INTO connections (user1_id, user2_id)
            VALUES (?, ?)
        """, (a, b))
        cursor.execute("""
            INSERT OR IGNORE INTO friends (user_id, friend_id)
            VALUES (?, ?)
        """, (a, b))
        cursor.execute("""
            INSERT OR IGNORE INTO friends (user_id, friend_id)
            VALUES (?, ?)
        """, (b, a))

    # Legacy friends rows also create canonical connections.
    friends = cursor.execute("SELECT user_id, friend_id FROM friends").fetchall()
    for row in friends:
        a, b = sorted((int(row["user_id"]), int(row["friend_id"])))
        if a != b:
            cursor.execute("""
                INSERT OR IGNORE INTO connections (user1_id, user2_id)
                VALUES (?, ?)
            """, (a, b))

    conn.commit()


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            profile_picture TEXT,
            bio TEXT DEFAULT '',
            last_seen TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            caption TEXT,
            media TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            UNIQUE(user_id, post_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            UNIQUE(user_id, friend_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connection_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sender_id, receiver_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user1_id, user2_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message TEXT,
            image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TEXT,
            read_at TEXT,
            status TEXT DEFAULT 'sent'
        )
    """)

    # Migrate older databases safely.
    migrations = [
        ("users", "profile_picture", "TEXT"),
        ("users", "bio", "TEXT DEFAULT ''"),
        ("users", "last_seen", "TEXT"),
        ("messages", "image", "TEXT"),
        ("messages", "delivered_at", "TEXT"),
        ("messages", "read_at", "TEXT"),
        ("messages", "status", "TEXT DEFAULT 'sent'"),
    ]

    for table, column, definition in migrations:
        try:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )
        except sqlite3.OperationalError:
            pass

    # Make old messages have a valid status.
    cursor.execute("""
        UPDATE messages
        SET status = CASE
            WHEN read_at IS NOT NULL THEN 'read'
            WHEN delivered_at IS NOT NULL THEN 'delivered'
            ELSE 'sent'
        END
        WHERE status IS NULL OR status = ''
    """)

    conn.commit()
    conn.close()


# =========================================================
# COMPLETE FEATURE SCHEMA
# =========================================================

def ensure_feature_schema():
    """Create all optional-feature tables/columns for fresh and older databases."""
    conn = get_db()
    cursor = conn.cursor()

    statements = [
        """CREATE TABLE IF NOT EXISTS blocked_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocker_id INTEGER NOT NULL,
            blocked_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(blocker_id, blocked_id)
        )""",
        """CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            group_picture TEXT,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT,
            file_path TEXT,
            file_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS highlights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            image TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sender_id INTEGER,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS profile_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            viewer_id INTEGER NOT NULL,
            viewed_user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS match_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            liked_user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, liked_user_id)
        )"""
    ]

    for sql in statements:
        cursor.execute(sql)

    for column, definition in [
        ("notifications_enabled", "INTEGER DEFAULT 1"),
        ("profile_visibility", "TEXT DEFAULT 'everyone'"),
        ("posts_visibility", "TEXT DEFAULT 'everyone'"),
        ("profile_views_enabled", "INTEGER DEFAULT 1"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# =========================================================
# AUTH HELPERS
# =========================================================

def login_required():
    return "user_id" in session


def are_connected(user1, user2, cursor):
    cursor.execute("""
        SELECT id
        FROM connections
        WHERE
            (user1_id = ? AND user2_id = ?)
            OR
            (user1_id = ? AND user2_id = ?)
        LIMIT 1
    """, (user1, user2, user2, user1))
    return cursor.fetchone() is not None


# =========================================================
# ONLINE / PRESENCE
# =========================================================

def set_user_online(user_id):
    if not user_id:
        return
    active_users[user_id] = active_users.get(user_id, 0) + 1

    conn = get_db()
    conn.execute(
        "UPDATE users SET last_seen = ? WHERE id = ?",
        (now_string(), user_id)
    )
    conn.commit()
    conn.close()

    socketio.emit(
        "presence",
        {"user_id": user_id, "online": True},
        broadcast=True
    )


def set_user_offline(user_id):
    if not user_id:
        return

    count = active_users.get(user_id, 0)

    if count > 1:
        active_users[user_id] = count - 1
        return

    active_users.pop(user_id, None)

    conn = get_db()
    conn.execute(
        "UPDATE users SET last_seen = ? WHERE id = ?",
        (now_string(), user_id)
    )
    conn.commit()
    conn.close()

    socketio.emit(
        "presence",
        {"user_id": user_id, "online": False},
        broadcast=True
    )


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    if not login_required():
        return jsonify({"success": False}), 401

    user_id = session["user_id"]

    conn = get_db()
    conn.execute(
        "UPDATE users SET last_seen = ? WHERE id = ?",
        (now_string(), user_id)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "online": user_id in active_users
    })


@app.route("/user-status/<int:user_id>")
def user_status(user_id):
    if user_id in active_users:
        return jsonify({"online": True})

    conn = get_db()
    row = conn.execute(
        "SELECT last_seen FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    if not row or not row["last_seen"]:
        return jsonify({"online": False, "last_seen": None})

    try:
        last_seen = datetime.strptime(
            row["last_seen"], "%Y-%m-%d %H:%M:%S"
        )
        online = datetime.now() - last_seen < timedelta(seconds=15)
    except Exception:
        online = False

    return jsonify({
        "online": online,
        "last_seen": row["last_seen"]
    })


# =========================================================
# HOME / SIGNUP / LOGIN / LOGOUT
# =========================================================

@app.route("/")
def home():
    if login_required():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return "All fields are required.", 400

        if len(password) < 6:
            return "Password must contain at least 6 characters.", 400

        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO users (name, email, password, bio)
                VALUES (?, ?, ?, '')
            """, (name, email, generate_password_hash(password)))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered!", 400

        conn.close()
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if user is None:
            conn.close()
            return "Invalid email or password!", 401

        stored_password = user["password"]
        valid = False

        try:
            valid = check_password_hash(stored_password, password)
        except Exception:
            valid = False

        # Upgrade an old plain-text password once.
        if not valid and stored_password == password:
            valid = True
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (generate_password_hash(password), user["id"])
            )
            conn.commit()

        conn.close()

        if not valid:
            return "Invalid email or password!", 401

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    session.clear()
    if user_id:
        set_user_offline(user_id)
    return redirect(url_for("home"))


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    users = cursor.execute("""
        SELECT id, name, profile_picture, bio, last_seen
        FROM users
        WHERE id != ?
        ORDER BY id DESC
    """, (current_user,)).fetchall()

    posts_data = cursor.execute("""
        SELECT
            posts.id,
            posts.user_id,
            posts.caption,
            posts.media,
            posts.created_at,
            users.name,
            users.profile_picture,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count,
            (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) AS comment_count,
            (SELECT COUNT(*) FROM shares WHERE shares.post_id = posts.id) AS share_count,
            EXISTS(
                SELECT 1 FROM likes
                WHERE likes.post_id = posts.id AND likes.user_id = ?
            ) AS user_liked
        FROM posts
        JOIN users ON users.id = posts.user_id
        ORDER BY posts.created_at DESC
    """, (current_user,)).fetchall()

    posts = []

    for post in posts_data:
        comments = cursor.execute("""
            SELECT comments.id, comments.comment,
                   comments.created_at, users.name
            FROM comments
            JOIN users ON users.id = comments.user_id
            WHERE comments.post_id = ?
            ORDER BY comments.created_at ASC
        """, (post["id"],)).fetchall()

        item = dict(post)
        item["comments"] = comments
        posts.append(item)

    conn.close()

    return render_template(
        "dashboard.html",
        users=users,
        posts=posts
    )


# =========================================================
# POSTS
# =========================================================

def save_uploaded_file(file):
    """Validate and save an uploaded media file safely."""

    if not file or not file.filename:
        return None

    original = secure_filename(file.filename)

    if not original:
        raise ValueError("Invalid filename.")

    if not allowed_file(original):
        raise ValueError(
            "Unsupported file type. "
            "Use PNG, JPG, JPEG, GIF, WEBP, MP4, WEBM or MOV."
        )

    extension = os.path.splitext(original)[1].lower()

    filename = f"{secrets.token_hex(16)}{extension}"

    os.makedirs(
        app.config["UPLOAD_FOLDER"],
        exist_ok=True
    )

    destination = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    try:

        file.save(destination)

    except Exception as exc:

        app.logger.exception(
            "Upload save failed"
        )

        raise ValueError(
            "Could not save the uploaded file."
        ) from exc

    if (
        not os.path.isfile(destination)
        or os.path.getsize(destination) == 0
    ):

        try:
            os.remove(destination)
        except OSError:
            pass

        raise ValueError(
            "The uploaded file was empty or could not be saved."
        )

    return filename


# =========================================================
# CREATE POST
# =========================================================

@app.route("/create-post", methods=["POST"])
def create_post():

    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    caption = request.form.get(
        "caption",
        ""
    ).strip()

    file = request.files.get("media")

    try:

        filename = save_uploaded_file(file)

    except ValueError as exc:

        return str(exc), 400

    # Prevent completely empty posts
    if not caption and not filename:

        return (
            "Please add a caption or photo/video.",
            400
        )

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO posts
            (
                user_id,
                caption,
                media
            )
            VALUES (?, ?, ?)
            """,
            (
                current_user,
                caption,
                filename
            )
        )

        conn.commit()

    except Exception:

        conn.rollback()

        # Remove uploaded file if database insert failed
        if filename:

            path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            if os.path.exists(path):

                try:
                    os.remove(path)
                except OSError:
                    pass

        raise

    finally:

        conn.close()

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# UPLOAD REEL
# =========================================================

@app.route("/upload-reel", methods=["POST"])
def upload_reel():

    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    caption = request.form.get(
        "caption",
        ""
    ).strip()

    file = request.files.get("reel")

    if not file or not file.filename:

        return (
            "Please select a video.",
            400
        )

    original = secure_filename(
        file.filename
    )

    if not original:

        return (
            "Invalid video filename.",
            400
        )

    extension = os.path.splitext(
        original
    )[1].lower()

    if extension not in {
        ".mp4",
        ".webm",
        ".mov"
    }:

        return (
            "Only MP4, WEBM and MOV videos are allowed.",
            400
        )

    try:

        filename = save_uploaded_file(
            file
        )

    except ValueError as exc:

        return str(exc), 400

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO posts
            (
                user_id,
                caption,
                media
            )
            VALUES (?, ?, ?)
            """,
            (
                current_user,
                caption,
                filename
            )
        )

        conn.commit()

    except Exception:

        conn.rollback()

        if filename:

            path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            if os.path.exists(path):

                try:
                    os.remove(path)
                except OSError:
                    pass

        raise

    finally:

        conn.close()

    return redirect(
        url_for("reels")
    )


# =========================================================
# DELETE POST
# =========================================================

@app.route(
    "/delete-post/<int:post_id>",
    methods=["POST"]
)
def delete_post(post_id):

    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # STEP 1: Find the post by ID only
    # -----------------------------------------------------

    post = cursor.execute(
        """
        SELECT
            id,
            user_id,
            media
        FROM posts
        WHERE id = ?
        """,
        (post_id,)
    ).fetchone()

    if not post:

        conn.close()

        return (
            "Post not found.",
            404
        )

    # -----------------------------------------------------
    # STEP 2: Check ownership separately
    # -----------------------------------------------------

    try:

        post_owner = int(
            post["user_id"]
        )

        logged_user = int(
            current_user
        )

    except (TypeError, ValueError):

        conn.close()

        return (
            "Invalid user information.",
            400
        )

    if post_owner != logged_user:

        conn.close()

        return (
            "You can delete only your own posts.",
            403
        )

    media = post["media"]

    # -----------------------------------------------------
    # STEP 3: Delete related records
    # -----------------------------------------------------

    try:

        cursor.execute(
            "DELETE FROM likes WHERE post_id = ?",
            (post_id,)
        )

        cursor.execute(
            "DELETE FROM comments WHERE post_id = ?",
            (post_id,)
        )

        cursor.execute(
            "DELETE FROM shares WHERE post_id = ?",
            (post_id,)
        )

        # -------------------------------------------------
        # STEP 4: Delete post
        # -------------------------------------------------

        cursor.execute(
            "DELETE FROM posts WHERE id = ?",
            (post_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()

        conn.close()

        raise

    conn.close()

    # -----------------------------------------------------
    # STEP 5: Delete uploaded media file
    # -----------------------------------------------------

    if media:

        media_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            media
        )

        if os.path.exists(media_path):

            try:

                os.remove(media_path)

            except OSError:

                app.logger.warning(
                    "Could not delete media file: %s",
                    media_path
                )

    # -----------------------------------------------------
    # STEP 6: Return to dashboard
    # -----------------------------------------------------

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# DELETE REEL
# =========================================================

@app.route(
    "/delete-reel/<int:post_id>",
    methods=["POST"]
)
def delete_reel(post_id):

    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # Find reel
    # -----------------------------------------------------

    reel = cursor.execute(
        """
        SELECT
            id,
            user_id,
            media
        FROM posts
        WHERE id = ?
        """,
        (post_id,)
    ).fetchone()

    if not reel:

        conn.close()

        return (
            "Reel not found.",
            404
        )

    # -----------------------------------------------------
    # Check ownership
    # -----------------------------------------------------

    try:

        reel_owner = int(
            reel["user_id"]
        )

        logged_user = int(
            current_user
        )

    except (TypeError, ValueError):

        conn.close()

        return (
            "Invalid user information.",
            400
        )

    if reel_owner != logged_user:

        conn.close()

        return (
            "You can delete only your own reels.",
            403
        )

    media = reel["media"] or ""

    extension = os.path.splitext(
        media
    )[1].lower()

    # -----------------------------------------------------
    # Confirm this is actually a video
    # -----------------------------------------------------

    if extension not in {
        ".mp4",
        ".webm",
        ".mov"
    }:

        conn.close()

        return (
            "This post is not a reel.",
            400
        )

    # -----------------------------------------------------
    # Delete related records
    # -----------------------------------------------------

    try:

        cursor.execute(
            "DELETE FROM likes WHERE post_id = ?",
            (post_id,)
        )

        cursor.execute(
            "DELETE FROM comments WHERE post_id = ?",
            (post_id,)
        )

        cursor.execute(
            "DELETE FROM shares WHERE post_id = ?",
            (post_id,)
        )

        cursor.execute(
            "DELETE FROM posts WHERE id = ?",
            (post_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()

        conn.close()

        raise

    conn.close()

    # -----------------------------------------------------
    # Delete video file
    # -----------------------------------------------------

    if media:

        media_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            media
        )

        if os.path.exists(media_path):

            try:

                os.remove(media_path)

            except OSError:

                app.logger.warning(
                    "Could not delete reel file: %s",
                    media_path
                )

    return redirect(
        url_for("reels")
    )


# =========================================================
# REELS
# =========================================================

@app.route("/reels")
def reels():

    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    rows = cursor.execute(
        """
        SELECT
            posts.id,
            posts.user_id,
            posts.caption,
            posts.media,
            posts.created_at,
            users.name,
            users.profile_picture,

            (
                SELECT COUNT(*)
                FROM likes
                WHERE likes.post_id = posts.id
            ) AS like_count,

            (
                SELECT COUNT(*)
                FROM comments
                WHERE comments.post_id = posts.id
            ) AS comment_count,

            (
                SELECT COUNT(*)
                FROM shares
                WHERE shares.post_id = posts.id
            ) AS share_count,

            EXISTS(
                SELECT 1
                FROM likes
                WHERE likes.post_id = posts.id
                AND likes.user_id = ?
            ) AS user_liked

        FROM posts

        JOIN users
        ON users.id = posts.user_id

        WHERE
            LOWER(posts.media) LIKE '%.mp4'
            OR LOWER(posts.media) LIKE '%.webm'
            OR LOWER(posts.media) LIKE '%.mov'

        ORDER BY posts.created_at DESC
        """,
        (current_user,)
    ).fetchall()

    reels_list = []

    for row in rows:

        item = dict(row)

        item["comments"] = cursor.execute(
            """
            SELECT
                comments.id,
                comments.comment,
                comments.created_at,
                users.name

            FROM comments

            JOIN users
            ON users.id = comments.user_id

            WHERE comments.post_id = ?

            ORDER BY comments.created_at ASC
            """,
            (row["id"],)
        ).fetchall()

        reels_list.append(
            item
        )

    conn.close()

    return render_template(
        "reels.html",
        reels=reels_list
    )


@app.route("/like/<int:post_id>", methods=["POST"])
def like(post_id):
    if not login_required():
        return jsonify({"success": False, "error": "Please login first."}), 401

    conn = get_db()
    cursor = conn.cursor()

    if not cursor.execute(
        "SELECT id FROM posts WHERE id = ?", (post_id,)
    ).fetchone():
        conn.close()
        return jsonify({"success": False, "error": "Post not found."}), 404

    existing = cursor.execute("""
        SELECT id FROM likes
        WHERE user_id = ? AND post_id = ?
    """, (session["user_id"], post_id)).fetchone()

    if existing:
        cursor.execute(
            "DELETE FROM likes WHERE user_id = ? AND post_id = ?",
            (session["user_id"], post_id)
        )
        liked = False
    else:
        cursor.execute(
            "INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?, ?)",
            (session["user_id"], post_id)
        )
        liked = True

    count = cursor.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id = ?",
        (post_id,)
    ).fetchone()[0]

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "liked": liked,
        "like_count": count
    })


@app.route("/comment/<int:post_id>", methods=["POST"])
def comment(post_id):
    if not login_required():
        return jsonify({"success": False, "error": "Please login first."}), 401

    text = request.form.get("comment", "").strip()

    if not text:
        return jsonify({"success": False, "error": "Comment cannot be empty."}), 400

    if len(text) > 500:
        return jsonify({"success": False, "error": "Comment is too long."}), 400

    conn = get_db()
    cursor = conn.cursor()

    if not cursor.execute(
        "SELECT id FROM posts WHERE id = ?", (post_id,)
    ).fetchone():
        conn.close()
        return jsonify({"success": False, "error": "Post not found."}), 404

    cursor.execute("""
        INSERT INTO comments (user_id, post_id, comment)
        VALUES (?, ?, ?)
    """, (session["user_id"], post_id, text))

    count = cursor.execute(
        "SELECT COUNT(*) FROM comments WHERE post_id = ?",
        (post_id,)
    ).fetchone()[0]

    name = cursor.execute(
        "SELECT name FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()["name"]

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "name": name,
        "comment": text,
        "comment_count": count
    })


@app.route("/share/<int:post_id>", methods=["POST"])
def share(post_id):
    if not login_required():
        return jsonify({"success": False, "error": "Please login first."}), 401

    conn = get_db()
    cursor = conn.cursor()

    if not cursor.execute(
        "SELECT id FROM posts WHERE id = ?", (post_id,)
    ).fetchone():
        conn.close()
        return jsonify({"success": False, "error": "Post not found."}), 404

    cursor.execute(
        "INSERT INTO shares (user_id, post_id) VALUES (?, ?)",
        (session["user_id"], post_id)
    )
    count = cursor.execute(
        "SELECT COUNT(*) FROM shares WHERE post_id = ?",
        (post_id,)
    ).fetchone()[0]

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "count": count,
        "url": request.host_url.rstrip("/") + "/dashboard#post-" + str(post_id)
    })


# =========================================================
# PROFILES
# =========================================================

def profile_common(profile_id):
    current_user = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    person = cursor.execute("""
        SELECT id, name, email, profile_picture, bio, last_seen,
               profile_visibility, posts_visibility, profile_views_enabled
        FROM users
        WHERE id = ?
    """, (profile_id,)).fetchone()

    if not person:
        conn.close()
        return None

    # Respect profile visibility settings for other users.
    if profile_id != current_user:
        visibility = person["profile_visibility"] or "everyone"
        if visibility == "only_me":
            conn.close()
            return {"person": person, "posts": [], "friends": [],
                    "highlights": [], "is_own_profile": False,
                    "relationship_status": "none", "pending_request_id": None,
                    "private_profile": True}

    if profile_id != current_user and (person["profile_views_enabled"] or 0):
        cursor.execute("""
            INSERT INTO profile_views (viewer_id, viewed_user_id)
            VALUES (?, ?)
        """, (current_user, profile_id))

    posts = cursor.execute("""
        SELECT
            posts.id, posts.user_id, posts.caption,
            posts.media, posts.created_at,
            COUNT(likes.id) AS like_count
        FROM posts
        LEFT JOIN likes ON likes.post_id = posts.id
        WHERE posts.user_id = ?
        GROUP BY posts.id, posts.user_id, posts.caption, posts.media, posts.created_at
        ORDER BY posts.created_at DESC
    """, (profile_id,)).fetchall()

    relationship_status = "own" if profile_id == current_user else "none"
    pending_request_id = None

    if profile_id != current_user:
        if are_connected(current_user, profile_id, cursor):
            relationship_status = "friends"
        else:
            outgoing = cursor.execute("""
                SELECT id FROM connection_requests
                WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
            """, (current_user, profile_id)).fetchone()

            if outgoing:
                relationship_status = "sent"
                pending_request_id = outgoing["id"]
            else:
                incoming = cursor.execute("""
                    SELECT id FROM connection_requests
                    WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
                """, (profile_id, current_user)).fetchone()

                if incoming:
                    relationship_status = "received"
                    pending_request_id = incoming["id"]

    friends = cursor.execute("""
        SELECT users.id, users.name, users.profile_picture
        FROM connections
        JOIN users ON users.id =
            CASE
                WHEN connections.user1_id = ? THEN connections.user2_id
                ELSE connections.user1_id
            END
        WHERE connections.user1_id = ? OR connections.user2_id = ?
        ORDER BY connections.created_at DESC
    """, (profile_id, profile_id, profile_id)).fetchall()

    highlights = cursor.execute("""
        SELECT id, name, image, created_at
        FROM highlights
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (profile_id,)).fetchall()

    conn.commit()
    conn.close()

    return {
        "person": person,
        "posts": posts,
        "friends": friends,
        "highlights": highlights,
        "private_profile": False,
        "is_own_profile": profile_id == current_user,
        "relationship_status": relationship_status,
        "pending_request_id": pending_request_id
    }


@app.route("/profile")
def profile():
    if not login_required():
        return redirect(url_for("login"))

    profile_id = request.args.get("user_id", type=int)
    if profile_id is None:
        profile_id = session["user_id"]

    data = profile_common(profile_id)
    if not data:
        return "User not found.", 404

    return render_template("profile.html", **data)


@app.route("/profile/<int:user_id>")
def user_profile(user_id):
    if not login_required():
        return redirect(url_for("login"))

    if user_id == session["user_id"]:
        return redirect(url_for("profile"))

    data = profile_common(user_id)
    if not data:
        return "Person not found.", 404

    return render_template("profile.html", **data)


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if not login_required():
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        bio = request.form.get("bio", "").strip()

        if not name:
            conn.close()
            return "Name is required.", 400

        conn.execute(
            "UPDATE users SET name = ?, bio = ? WHERE id = ?",
            (name, bio, user_id)
        )
        conn.commit()
        conn.close()

        session["user_name"] = name
        return redirect(url_for("profile"))

    person = conn.execute(
        "SELECT id, name, bio FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    if not person:
        return "User not found.", 404

    return render_template("edit_profile.html", person=person)


@app.route("/upload-profile-picture", methods=["POST"])
def upload_profile_picture():
    if not login_required():
        return redirect(url_for("login"))

    user_id = session["user_id"]
    cropped_image = request.form.get("cropped_image", "").strip()
    file = request.files.get("profile_picture")

    # Cropped images are already encoded as JPEG data.
    if cropped_image:
        try:
            encoded = cropped_image.split(",", 1)[1] if "," in cropped_image else cropped_image
            image_data = base64.b64decode(encoded, validate=True)
            if not image_data:
                raise ValueError
            filename = f"profile_{user_id}.jpg"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            with open(filepath, "wb") as f:
                f.write(image_data)
        except Exception:
            return "Could not save cropped image.", 400
    elif file and file.filename:
        original = secure_filename(file.filename)
        if not original or not allowed_profile_picture(original):
            return "Only JPG, JPEG, PNG, GIF and WEBP images are allowed.", 400

        extension = os.path.splitext(original)[1].lower()
        filename = f"profile_{user_id}{extension}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        try:
            file.save(filepath)
        except Exception:
            app.logger.exception("Profile image save failed")
            return "Could not save profile picture.", 500
    else:
        return "Please select a profile picture.", 400

    # Remove older profile variants.
    for ext in PROFILE_EXTENSIONS:
        old_path = os.path.join(app.config["UPLOAD_FOLDER"], f"profile_{user_id}.{ext}")
        if os.path.basename(old_path) != filename:
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except OSError:
                pass

    conn = get_db()
    conn.execute(
        "UPDATE users SET profile_picture = ? WHERE id = ?",
        (filename, user_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("profile"))



# =========================================================
# FIND PEOPLE / CONNECTIONS
# =========================================================

@app.route("/find-people")
def find_people():
    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]
    search = request.args.get("q", "").strip()

    conn = get_db()
    cursor = conn.cursor()

    if search:
        people = cursor.execute("""
            SELECT id, name, email, profile_picture
            FROM users
            WHERE (name LIKE ? OR email LIKE ?) AND id != ?
            ORDER BY name
        """, (f"%{search}%", f"%{search}%", current_user)).fetchall()
    else:
        people = cursor.execute("""
            SELECT id, name, email, profile_picture
            FROM users WHERE id != ?
            ORDER BY name
        """, (current_user,)).fetchall()

    result = []

    for row in people:
        item = dict(row)
        pid = item["id"]

        if are_connected(current_user, pid, cursor):
            item["relationship_status"] = "friends"
        elif cursor.execute("""
            SELECT id FROM connection_requests
            WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
        """, (current_user, pid)).fetchone():
            item["relationship_status"] = "sent"
        elif cursor.execute("""
            SELECT id FROM connection_requests
            WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
        """, (pid, current_user)).fetchone():
            item["relationship_status"] = "received"
        else:
            item["relationship_status"] = "none"

        result.append(item)

    conn.close()

    return render_template(
        "find_people.html",
        people=result,
        search=search
    )


@app.route("/send-request/<int:user_id>", methods=["POST"])
def send_request(user_id):
    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    if current_user == user_id:
        return "You cannot connect with yourself.", 400

    conn = get_db()
    cursor = conn.cursor()

    if not cursor.execute(
        "SELECT id FROM users WHERE id = ?", (user_id,)
    ).fetchone():
        conn.close()
        return "User not found.", 404

    if are_connected(current_user, user_id, cursor):
        conn.close()
        return redirect(url_for("find_people", sent=user_id))

    existing = cursor.execute("""
        SELECT id, sender_id, receiver_id, status
        FROM connection_requests
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY id DESC LIMIT 1
    """, (current_user, user_id, user_id, current_user)).fetchone()

    if existing:
        if existing["status"] == "pending":
            conn.close()
            return redirect(url_for("find_people", sent=user_id))
        if existing["status"] == "accepted":
            a, b = sorted((current_user, user_id))
            cursor.execute("INSERT OR IGNORE INTO connections (user1_id, user2_id) VALUES (?, ?)", (a, b))
            conn.commit()
            conn.close()
            return redirect(url_for("find_people", sent=user_id))
        # Rejected requests can be sent again.
        cursor.execute("""
            DELETE FROM connection_requests
            WHERE (sender_id = ? AND receiver_id = ?)
               OR (sender_id = ? AND receiver_id = ?)
        """, (current_user, user_id, user_id, current_user))

    cursor.execute("""
        INSERT INTO connection_requests
        (sender_id, receiver_id, status)
        VALUES (?, ?, 'pending')
    """, (current_user, user_id))

    sender = cursor.execute(
        "SELECT name FROM users WHERE id = ?",
        (current_user,)
    ).fetchone()
    if sender:
        add_notification(
            cursor,
            user_id,
            current_user,
            "connection_request",
            f"{sender['name']} sent you a connection request 🤝"
        )

    conn.commit()
    conn.close()

    return redirect(url_for("find_people"))


@app.route("/requests")
def requests():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    rows = conn.execute("""
        SELECT
            connection_requests.id,
            connection_requests.sender_id,
            connection_requests.created_at,
            users.name, users.email, users.profile_picture
        FROM connection_requests
        JOIN users ON users.id = connection_requests.sender_id
        WHERE connection_requests.receiver_id = ?
          AND connection_requests.status = 'pending'
        ORDER BY connection_requests.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    return render_template("requests.html", requests=rows)


@app.route("/accept-request/<int:request_id>", methods=["POST"])
def accept_request(request_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    req = cursor.execute("""
        SELECT id, sender_id, receiver_id, status
        FROM connection_requests
        WHERE id = ? AND receiver_id = ?
    """, (request_id, session["user_id"])).fetchone()

    if not req:
        conn.close()
        return "Request not found.", 404

    if req["status"] != "pending":
        conn.close()
        return redirect(url_for("requests"))

    sender_id = req["sender_id"]
    receiver_id = req["receiver_id"]

    cursor.execute("""
        UPDATE connection_requests
        SET status = 'accepted'
        WHERE id = ?
    """, (request_id,))

    user1 = min(sender_id, receiver_id)
    user2 = max(sender_id, receiver_id)

    cursor.execute("""
        INSERT OR IGNORE INTO connections (user1_id, user2_id)
        VALUES (?, ?)
    """, (user1, user2))

    # Keep the old friends table in sync too.
    cursor.execute("""
        INSERT OR IGNORE INTO friends (user_id, friend_id)
        VALUES (?, ?)
    """, (sender_id, receiver_id))
    cursor.execute("""
        INSERT OR IGNORE INTO friends (user_id, friend_id)
        VALUES (?, ?)
    """, (receiver_id, sender_id))

    receiver = cursor.execute(
        "SELECT name FROM users WHERE id = ?",
        (receiver_id,)
    ).fetchone()
    if receiver:
        add_notification(
            cursor,
            sender_id,
            receiver_id,
            "connection_accepted",
            f"{receiver['name']} accepted your connection request."
        )

    conn.commit()
    conn.close()

    return redirect(url_for("requests"))


@app.route("/reject-request/<int:request_id>", methods=["POST"])
def reject_request(request_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("""
        UPDATE connection_requests
        SET status = 'rejected'
        WHERE id = ?
          AND receiver_id = ?
          AND status = 'pending'
    """, (request_id, session["user_id"]))
    conn.commit()
    conn.close()

    return redirect(url_for("requests"))


@app.route("/connections")
def connections():
    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]
    conn = get_db()

    people = conn.execute("""
        SELECT users.id, users.name, users.email, users.profile_picture
        FROM connections
        JOIN users ON users.id =
            CASE
                WHEN connections.user1_id = ? THEN connections.user2_id
                ELSE connections.user1_id
            END
        WHERE connections.user1_id = ? OR connections.user2_id = ?
        ORDER BY users.name
    """, (current_user, current_user, current_user)).fetchall()

    conn.close()

    return render_template("connections.html", people=people)


# =========================================================
# MESSAGES LIST
# =========================================================

@app.route("/messages")
def messages():
    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]
    selected_user = request.args.get("user_id", type=int)

    conn = get_db()
    cursor = conn.cursor()

    people = cursor.execute("""
        SELECT
            u.id, u.name, u.email, u.profile_picture,
            (SELECT m.message FROM messages m
             WHERE (m.sender_id = ? AND m.receiver_id = u.id)
                OR (m.sender_id = u.id AND m.receiver_id = ?)
             ORDER BY m.id DESC LIMIT 1) AS last_message,
            (SELECT m.created_at FROM messages m
             WHERE (m.sender_id = ? AND m.receiver_id = u.id)
                OR (m.sender_id = u.id AND m.receiver_id = ?)
             ORDER BY m.id DESC LIMIT 1) AS last_time,
            (SELECT COUNT(*) FROM messages m
             WHERE m.sender_id = u.id AND m.receiver_id = ? AND m.read_at IS NULL) AS unread_count
        FROM users u
        WHERE u.id != ?
          AND (
              EXISTS (SELECT 1 FROM connections c
                     WHERE (c.user1_id = ? AND c.user2_id = u.id)
                        OR (c.user1_id = u.id AND c.user2_id = ?))
              OR EXISTS (SELECT 1 FROM messages m
                         WHERE (m.sender_id = ? AND m.receiver_id = u.id)
                            OR (m.sender_id = u.id AND m.receiver_id = ?))
          )
        ORDER BY last_time IS NULL, last_time DESC, u.name COLLATE NOCASE
    """, (
        current_user, current_user, current_user, current_user,
        current_user, current_user, current_user, current_user,
        current_user, current_user
    )).fetchall()

    selected_person = None

    if selected_user:
        selected_person = cursor.execute("""
            SELECT id, name, email, profile_picture
            FROM users WHERE id = ?
        """, (selected_user,)).fetchone()

    conn.close()

    return render_template(
        "messages.html",
        people=people,
        selected_person=selected_person
    )


# =========================================================
# CONVERSATION
# =========================================================

@app.route("/messages/<int:user_id>", methods=["GET", "POST"])
def conversation(user_id):
    if not login_required():
        return redirect(url_for("login"))

    current_user = session["user_id"]

    if current_user == user_id:
        return "You cannot message yourself.", 400

    conn = get_db()
    cursor = conn.cursor()

    user_row = cursor.execute("""
        SELECT id, name, email, profile_picture
        FROM users WHERE id = ?
    """, (user_id,)).fetchone()

    if not user_row:
        conn.close()
        return "User not found.", 404

    if not are_connected(current_user, user_id, cursor):
        conn.close()
        return "You are not connected with this user.", 403

    user = dict(user_row)

    if request.method == "POST":
        message = request.form.get("message", "").strip()[:1000]
        image_file = request.files.get("image")
        image_name = None

        if image_file and image_file.filename:
            if not allowed_profile_picture(image_file.filename):
                conn.close()
                return jsonify({"success": False, "error": "Only JPG, JPEG, PNG, GIF and WEBP images are allowed."}), 400
            safe = secure_filename(image_file.filename)
            ext = safe.rsplit(".", 1)[1].lower()
            image_name = f"msg_{current_user}_{user_id}_{secrets.token_hex(10)}.{ext}"
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_name))

        if not message and not image_name:
            conn.close()
            return jsonify({"success": False, "error": "Message or image is required."}), 400

        cursor.execute("""
            INSERT INTO messages
            (sender_id, receiver_id, message, image, status)
            VALUES (?, ?, ?, ?, 'sent')
        """, (current_user, user_id, message, image_name))

        message_id = cursor.lastrowid
        created_at = now_string()
        conn.commit()
        conn.close()

        payload = {
            "id": message_id,
            "sender_id": current_user,
            "receiver_id": user_id,
            "message": message,
            "image": image_name,
            "created_at": created_at,
            "status": "sent"
        }
        socketio.emit("new_message", payload, to=f"user_{user_id}")
        return jsonify({"success": True, "message": payload})

    # Opening a conversation means incoming messages are read.
    timestamp = now_string()
    cursor.execute("""
        UPDATE messages
        SET status = 'read',
            read_at = ?,
            delivered_at = COALESCE(delivered_at, ?)
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (timestamp, timestamp, user_id, current_user))
    conn.commit()

    rows = cursor.execute("""
        SELECT id, sender_id, receiver_id, message, image,
               created_at, delivered_at, read_at, status
        FROM messages
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY id ASC
    """, (current_user, user_id, user_id, current_user)).fetchall()

    conn.close()

    return render_template(
        "conversation.html",
        user=user,
        messages=rows
    )


# =========================================================
# AJAX MESSAGE DATA
# This endpoint is also a reliable fallback if Socket.IO fails.
# It marks incoming messages delivered when the browser actually
# retrieves them.
# =========================================================

@app.route("/messages/<int:user_id>/data")
def message_data(user_id):
    if not login_required():
        return jsonify({"error": "Not logged in"}), 401

    current_user = session["user_id"]

    if current_user == user_id:
        return jsonify({"error": "Invalid user"}), 400

    conn = get_db()
    cursor = conn.cursor()

    if not are_connected(current_user, user_id, cursor):
        conn.close()
        return jsonify({"error": "Not connected"}), 403

    timestamp = now_string()

    # Browser retrieved the messages => they are delivered.
    cursor.execute("""
        UPDATE messages
        SET status = CASE WHEN read_at IS NULL THEN 'delivered' ELSE 'read' END,
            delivered_at = COALESCE(delivered_at, ?)
        WHERE sender_id = ?
          AND receiver_id = ?
          AND delivered_at IS NULL
    """, (timestamp, user_id, current_user))

    cursor.execute("""
        SELECT
            id, message, image, created_at,
            sender_id, receiver_id,
            delivered_at, read_at, status
        FROM messages
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY id ASC
    """, (current_user, user_id, user_id, current_user))

    rows = cursor.fetchall()
    conn.commit()
    conn.close()

    # Tell the sender that the messages were delivered.
    delivered_ids = [
        row["id"] for row in rows
        if row["sender_id"] == user_id and row["delivered_at"] is not None
    ]

    if delivered_ids:
        socketio.emit("message_status", {
            "message_ids": delivered_ids,
            "status": "delivered"
        }, to=f"user_{user_id}")

    return jsonify({
        "success": True,
        "user": {
            "id": user_id,
            "online": user_id in active_users
        },
        "messages": [
            {
                "id": row["id"],
                "message": row["message"],
                "image": row["image"],
                "created_at": row["created_at"],
                "sender_id": row["sender_id"],
                "receiver_id": row["receiver_id"],
                "delivered_at": row["delivered_at"],
                "read_at": row["read_at"],
                "status": row["status"]
            }
            for row in rows
        ]
    })


@app.route("/messages/<int:user_id>/read", methods=["POST"])
def mark_messages_read(user_id):
    if not login_required():
        return jsonify({"success": False}), 401

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    if not are_connected(current_user, user_id, cursor):
        conn.close()
        return jsonify({"success": False, "error": "Not connected"}), 403

    timestamp = now_string()

    rows = cursor.execute("""
        SELECT id
        FROM messages
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (user_id, current_user)).fetchall()

    cursor.execute("""
        UPDATE messages
        SET status = 'read',
            read_at = ?,
            delivered_at = COALESCE(delivered_at, ?)
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (timestamp, timestamp, user_id, current_user))

    conn.commit()
    conn.close()

    ids = [row["id"] for row in rows]

    if ids:
        socketio.emit("message_status", {
            "message_ids": ids,
            "status": "read"
        }, to=f"user_{user_id}")

    return jsonify({"success": True, "message_ids": ids})


@app.route("/messages/unsend/<int:message_id>", methods=["POST"])
def unsend_message(message_id):
    if not login_required():
        return jsonify({"success": False, "error": "Not logged in"}), 401

    conn = get_db()
    row = conn.execute("SELECT id, sender_id, image FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row or row["sender_id"] != session["user_id"]:
        conn.close()
        return jsonify({"success": False, "error": "Message not found or not yours."}), 404

    if row["image"]:
        try:
            os.remove(os.path.join(app.config["UPLOAD_FOLDER"], row["image"]))
        except OSError:
            pass
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# =========================================================
# SOCKET.IO EVENTS
# =========================================================

@socketio.on("connect")
def socket_connect():
    user_id = session.get("user_id")

    if not user_id:
        return

    join_room(f"user_{user_id}")
    set_user_online(user_id)

    emit("connected", {
        "user_id": user_id,
        "online": True
    })


@socketio.on("disconnect")
def socket_disconnect():
    user_id = session.get("user_id")
    if user_id:
        set_user_offline(user_id)


@socketio.on("join_chat")
def socket_join_chat(data):
    user_id = session.get("user_id")
    other_id = data.get("user_id") if isinstance(data, dict) else None

    if not user_id or not other_id:
        return

    room = f"chat_{min(user_id, int(other_id))}_{max(user_id, int(other_id))}"
    join_room(room)

    # Joining the conversation means incoming messages are read.
    timestamp = now_string()
    conn = get_db()

    rows = conn.execute("""
        SELECT id
        FROM messages
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (int(other_id), user_id)).fetchall()

    conn.execute("""
        UPDATE messages
        SET status = 'read',
            read_at = ?,
            delivered_at = COALESCE(delivered_at, ?)
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (timestamp, timestamp, int(other_id), user_id))

    conn.commit()
    conn.close()

    ids = [row["id"] for row in rows]

    if ids:
        socketio.emit("message_status", {
            "message_ids": ids,
            "status": "read"
        }, to=f"user_{int(other_id)}")


@socketio.on("send_message")
def socket_send_message(data):
    user_id = session.get("user_id")

    if not user_id or not isinstance(data, dict):
        return

    try:
        receiver_id = int(data.get("receiver_id"))
    except (TypeError, ValueError):
        return

    message = str(data.get("message", "")).strip()[:1000]

    if not message or receiver_id == user_id:
        return

    conn = get_db()
    cursor = conn.cursor()

    if not are_connected(user_id, receiver_id, cursor):
        conn.close()
        emit("send_error", {"error": "You are not connected with this user."})
        return

    cursor.execute("""
        INSERT INTO messages
        (sender_id, receiver_id, message, status)
        VALUES (?, ?, ?, 'sent')
    """, (user_id, receiver_id, message))

    message_id = cursor.lastrowid
    created_at = now_string()

    conn.commit()
    conn.close()

    payload = {
        "id": message_id,
        "sender_id": user_id,
        "receiver_id": receiver_id,
        "message": message,
        "created_at": created_at,
        "status": "sent"
    }

    # Sender sees the saved message immediately.
    emit("message_sent", payload)

    # Receiver gets it only through their real active socket.
    socketio.emit("new_message", payload, to=f"user_{receiver_id}")


@socketio.on("message_delivered")
def socket_message_delivered(data):
    user_id = session.get("user_id")

    if not user_id or not isinstance(data, dict):
        return

    try:
        message_id = int(data.get("message_id"))
    except (TypeError, ValueError):
        return

    conn = get_db()
    row = conn.execute("""
        SELECT id, sender_id, receiver_id, delivered_at
        FROM messages
        WHERE id = ? AND receiver_id = ?
    """, (message_id, user_id)).fetchone()

    if not row:
        conn.close()
        return

    if row["delivered_at"] is None:
        conn.execute("""
            UPDATE messages
            SET delivered_at = ?, status = 'delivered'
            WHERE id = ?
        """, (now_string(), message_id))
        conn.commit()

    sender_id = row["sender_id"]
    conn.close()

    socketio.emit("message_status", {
        "message_ids": [message_id],
        "status": "delivered"
    }, to=f"user_{sender_id}")


@socketio.on("chat_open")
def socket_chat_open(data):
    user_id = session.get("user_id")

    if not user_id or not isinstance(data, dict):
        return

    try:
        other_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return

    timestamp = now_string()
    conn = get_db()

    rows = conn.execute("""
        SELECT id
        FROM messages
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (other_id, user_id)).fetchall()

    conn.execute("""
        UPDATE messages
        SET status = 'read',
            read_at = ?,
            delivered_at = COALESCE(delivered_at, ?)
        WHERE sender_id = ?
          AND receiver_id = ?
          AND read_at IS NULL
    """, (timestamp, timestamp, other_id, user_id))

    conn.commit()
    conn.close()

    ids = [row["id"] for row in rows]

    if ids:
        socketio.emit("message_status", {
            "message_ids": ids,
            "status": "read"
        }, to=f"user_{other_id}")


@socketio.on("typing")
def socket_typing(data):
    user_id = session.get("user_id")

    if not user_id or not isinstance(data, dict):
        return

    try:
        receiver_id = int(data.get("receiver_id"))
    except (TypeError, ValueError):
        return

    socketio.emit("typing", {
        "user_id": user_id,
        "typing": bool(data.get("typing"))
    }, to=f"user_{receiver_id}")



# =========================================================
# SETTINGS / ACCOUNT / SOCIAL FEATURES
# =========================================================

def add_notification(cursor, user_id, sender_id, kind, message):
    cursor.execute("""
        INSERT INTO notifications
        (user_id, sender_id, type, message, is_read)
        SELECT ?, ?, ?, ?, 0
        WHERE EXISTS (
            SELECT 1 FROM users
            WHERE id = ? AND COALESCE(notifications_enabled, 1) = 1
        )
    """, (user_id, sender_id, kind, message, user_id))


@app.route("/settings")
def settings():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    user = conn.execute("""
        SELECT id, name, email, profile_picture, bio
        FROM users WHERE id = ?
    """, (session["user_id"],)).fetchone()
    conn.close()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    return render_template("settings.html", user=user)


@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not current or not new or not confirm:
            return render_template("change_password.html",
                                   error="Please fill all fields.")
        if new != confirm:
            return render_template("change_password.html",
                                   error="New passwords do not match.")
        if len(new) < 6:
            return render_template("change_password.html",
                                   error="Password must be at least 6 characters.")

        conn = get_db()
        user = conn.execute(
            "SELECT password FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        valid = False
        if user:
            try:
                valid = check_password_hash(user["password"], current)
            except Exception:
                valid = False
            if not valid and user["password"] == current:
                valid = True

        if not valid:
            conn.close()
            return render_template("change_password.html",
                                   error="Current password is incorrect.")

        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(new), session["user_id"])
        )
        conn.commit()
        conn.close()
        return render_template(
            "change_password.html",
            success="Password changed successfully."
        )

    return render_template("change_password.html")


@app.route("/notification-settings", methods=["GET", "POST"])
def notification_settings():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    if request.method == "POST":
        value = 1 if request.form.get("notifications_enabled") == "1" else 0
        conn.execute(
            "UPDATE users SET notifications_enabled = ? WHERE id = ?",
            (value, session["user_id"])
        )
        conn.commit()

    user = conn.execute(
        "SELECT notifications_enabled FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()
    return render_template("notification_settings.html", user=user)


@app.route("/privacy-settings", methods=["GET", "POST"])
def privacy_settings():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    if request.method == "POST":
        profile_visibility = request.form.get("profile_visibility", "everyone")
        posts_visibility = request.form.get("posts_visibility", "everyone")
        views_enabled = 1 if request.form.get("profile_views_enabled") == "1" else 0

        if profile_visibility not in {"everyone", "friends", "only_me"}:
            profile_visibility = "everyone"
        if posts_visibility not in {"everyone", "friends"}:
            posts_visibility = "everyone"

        conn.execute("""
            UPDATE users
            SET profile_visibility = ?,
                posts_visibility = ?,
                profile_views_enabled = ?
            WHERE id = ?
        """, (
            profile_visibility, posts_visibility, views_enabled,
            session["user_id"]
        ))
        conn.commit()

    user = conn.execute("""
        SELECT profile_visibility, posts_visibility, profile_views_enabled
        FROM users WHERE id = ?
    """, (session["user_id"],)).fetchone()
    conn.close()
    return render_template("privacy_settings.html", user=user)


@app.route("/blocked-users")
def blocked_users():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    blocked = conn.execute("""
        SELECT b.id, b.blocked_id, u.name, u.profile_picture
        FROM blocked_users b
        JOIN users u ON u.id = b.blocked_id
        WHERE b.blocker_id = ?
        ORDER BY b.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("blocked_users.html", blocked=blocked)


@app.route("/block-user/<int:user_id>", methods=["POST"])
def block_user(user_id):
    if not login_required():
        return redirect(url_for("login"))
    current = session["user_id"]
    if current == user_id:
        return redirect(url_for("profile"))

    conn = get_db()
    exists = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not exists:
        conn.close()
        return "User not found.", 404

    conn.execute("""
        INSERT OR IGNORE INTO blocked_users (blocker_id, blocked_id)
        VALUES (?, ?)
    """, (current, user_id))
    conn.execute("""
        DELETE FROM connections
        WHERE (user1_id = ? AND user2_id = ?)
           OR (user1_id = ? AND user2_id = ?)
    """, (current, user_id, user_id, current))
    conn.execute("""
        DELETE FROM connection_requests
        WHERE (sender_id = ? AND receiver_id = ?)
           OR (sender_id = ? AND receiver_id = ?)
    """, (current, user_id, user_id, current))
    conn.commit()
    conn.close()
    return redirect(url_for("profile"))


@app.route("/unblock-user/<int:user_id>", methods=["POST"])
def unblock_user(user_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute("""
        DELETE FROM blocked_users
        WHERE blocker_id = ? AND blocked_id = ?
    """, (session["user_id"], user_id))
    conn.commit()
    conn.close()
    return redirect(url_for("blocked_users"))


@app.route("/unfriend/<int:user_id>", methods=["POST"])
def unfriend(user_id):
    if not login_required():
        return redirect(url_for("login"))
    current = session["user_id"]
    conn = get_db()
    conn.execute("""
        DELETE FROM connections
        WHERE (user1_id = ? AND user2_id = ?)
           OR (user1_id = ? AND user2_id = ?)
    """, (current, user_id, user_id, current))
    conn.execute("""
        DELETE FROM friends
        WHERE (user_id = ? AND friend_id = ?)
           OR (user_id = ? AND friend_id = ?)
    """, (current, user_id, user_id, current))
    conn.commit()
    conn.close()
    return redirect(url_for("user_profile", user_id=user_id))


@app.route("/cancel-request/<int:user_id>", methods=["POST"])
def cancel_request(user_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute("""
        DELETE FROM connection_requests
        WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
    """, (session["user_id"], user_id))
    conn.commit()
    conn.close()
    return redirect(url_for("user_profile", user_id=user_id))


@app.route("/profile-views")
def profile_views():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    views = conn.execute("""
        SELECT pv.id, pv.viewer_id, pv.created_at,
               u.name, u.profile_picture
        FROM profile_views pv
        JOIN users u ON u.id = pv.viewer_id
        WHERE pv.viewed_user_id = ?
        ORDER BY pv.created_at DESC
        LIMIT 100
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("profile_views.html", views=views)


@app.route("/notifications")
def notifications():
    if not login_required():
        return jsonify({"notifications": []})

    conn = get_db()
    rows = conn.execute("""
        SELECT n.id, n.type, n.message, n.is_read, n.created_at,
               n.sender_id, u.name AS sender_name,
               u.profile_picture AS sender_picture
        FROM notifications n
        LEFT JOIN users u ON u.id = n.sender_id
        WHERE n.user_id = ?
        ORDER BY n.created_at DESC
        LIMIT 50
    """, (session["user_id"],)).fetchall()
    conn.close()

    result = []
    for row in rows:
        item = dict(row)
        if item["type"] == "message":
            item["url"] = url_for("messages")
        elif item["type"] in {"match", "match_like"}:
            item["url"] = url_for("match")
        elif item["type"] == "connection_request":
            item["url"] = url_for("requests")
        elif item["sender_id"]:
            item["url"] = url_for("user_profile", user_id=item["sender_id"])
        else:
            item["url"] = url_for("dashboard")
        result.append(item)

    return jsonify({"notifications": result})


@app.route("/notification-count")
def notification_count():
    if not login_required():
        return jsonify({"count": 0})
    conn = get_db()
    count = conn.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id = ? AND is_read = 0
    """, (session["user_id"],)).fetchone()[0]
    conn.close()
    return jsonify({"count": count})


@app.route("/notifications/read", methods=["POST"])
def mark_notifications_read():
    if not login_required():
        return jsonify({"success": False}), 401
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
        (session["user_id"],)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/create-highlight", methods=["POST"])
def create_highlight():
    if not login_required():
        return jsonify({"success": False, "message": "Please login first."}), 401

    name = request.form.get("name", "").strip()[:100]
    image = request.files.get("image")

    if not name:
        return jsonify({"success": False, "message": "Please enter a highlight name."}), 400
    if not image or not image.filename:
        return jsonify({"success": False, "message": "Please select an image."}), 400

    original = secure_filename(image.filename)
    if not original or not allowed_profile_picture(original):
        return jsonify({
            "success": False,
            "message": "Only PNG, JPG, JPEG, GIF and WEBP images are allowed."
        }), 400

    ext = os.path.splitext(original)[1].lower()
    filename = f"highlight_{session['user_id']}_{secrets.token_hex(12)}{ext}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    try:
        image.save(path)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise OSError("empty file")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO highlights (user_id, name, image)
            VALUES (?, ?, ?)
        """, (session["user_id"], name, filename))
        highlight_id = cursor.lastrowid
        conn.commit()
        conn.close()
    except Exception:
        app.logger.exception("Highlight upload failed")
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return jsonify({
            "success": False,
            "message": "Could not save the highlight."
        }), 500

    return jsonify({
        "success": True,
        "message": "Highlight created successfully.",
        "highlight": {"id": highlight_id, "name": name, "image": filename}
    })


@app.route("/groups")
def groups():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT g.id, g.name, g.description, g.group_picture,
               g.created_by, g.created_at
        FROM groups g
        JOIN group_members gm ON gm.group_id = g.id
        WHERE gm.user_id = ?
        ORDER BY g.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("groups.html", groups=rows)


@app.route("/create-group", methods=["POST"])
def create_group():
    if not login_required():
        return redirect(url_for("login"))
    name = request.form.get("name", "").strip()[:100]
    description = request.form.get("description", "").strip()[:500]
    if not name:
        return "Group name is required.", 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO groups (name, description, created_by)
        VALUES (?, ?, ?)
    """, (name, description, session["user_id"]))
    group_id = cur.lastrowid
    cur.execute("""
        INSERT OR IGNORE INTO group_members (group_id, user_id, role)
        VALUES (?, ?, 'admin')
    """, (group_id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("groups"))


@app.route("/group/<int:group_id>")
def group_chat(group_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    group = conn.execute("""
        SELECT g.id, g.name, g.description, g.group_picture
        FROM groups g
        JOIN group_members gm ON gm.group_id = g.id
        WHERE g.id = ? AND gm.user_id = ?
    """, (group_id, session["user_id"])).fetchone()

    if not group:
        conn.close()
        return "Group not found or you are not a member.", 404

    messages = conn.execute("""
        SELECT gm.id, gm.group_id, gm.sender_id, gm.message,
               gm.file_path, gm.file_type, gm.created_at,
               u.name AS sender_name
        FROM group_messages gm
        JOIN users u ON u.id = gm.sender_id
        WHERE gm.group_id = ?
        ORDER BY gm.created_at ASC
    """, (group_id,)).fetchall()
    conn.close()
    return render_template("group_chat.html", group=group, messages=messages)


@app.route("/group/<int:group_id>/members")
def group_members(group_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    group = conn.execute("""
        SELECT g.id, g.name
        FROM groups g
        JOIN group_members gm ON gm.group_id = g.id
        WHERE g.id = ? AND gm.user_id = ?
    """, (group_id, session["user_id"])).fetchone()
    if not group:
        conn.close()
        return "Group not found or you are not a member.", 404

    members = conn.execute("""
        SELECT u.id, u.name, u.profile_picture,
               gm.role, gm.joined_at
        FROM group_members gm
        JOIN users u ON u.id = gm.user_id
        WHERE gm.group_id = ?
        ORDER BY CASE WHEN gm.role = 'admin' THEN 0 ELSE 1 END, u.name
    """, (group_id,)).fetchall()
    conn.close()
    return render_template("group_members.html", group=group, members=members)


@app.route("/group/<int:group_id>/send", methods=["POST"])
def send_group_message(group_id):
    if not login_required():
        return redirect(url_for("login"))
    message = request.form.get("message", "").strip()[:1000]
    if not message:
        return redirect(url_for("group_chat", group_id=group_id))

    conn = get_db()
    member = conn.execute("""
        SELECT id FROM group_members
        WHERE group_id = ? AND user_id = ?
    """, (group_id, session["user_id"])).fetchone()
    if not member:
        conn.close()
        return "You are not a member of this group.", 403

    conn.execute("""
        INSERT INTO group_messages (group_id, sender_id, message)
        VALUES (?, ?, ?)
    """, (group_id, session["user_id"], message))
    conn.commit()
    conn.close()
    return redirect(url_for("group_chat", group_id=group_id))


@app.route("/match")
def match():
    if not login_required():
        return redirect(url_for("login"))
    current = session["user_id"]
    conn = get_db()
    user = conn.execute("""
        SELECT id, name, profile_picture, bio
        FROM users
        WHERE id != ?
          AND id NOT IN (
              SELECT liked_user_id FROM match_likes WHERE user_id = ?
          )
          AND id NOT IN (
              SELECT blocked_id FROM blocked_users WHERE blocker_id = ?
          )
          AND id NOT IN (
              SELECT blocker_id FROM blocked_users WHERE blocked_id = ?
          )
        ORDER BY RANDOM()
        LIMIT 1
    """, (current, current, current, current)).fetchone()
    conn.close()
    return render_template("match.html", user=user)


@app.route("/profile-like/<int:user_id>", methods=["POST"])
def profile_like(user_id):
    if not login_required():
        return jsonify({"success": False, "error": "Please login first."}), 401
    current = session["user_id"]
    if current == user_id:
        return jsonify({"success": False, "error": "You cannot like yourself."}), 400

    conn = get_db()
    target = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target:
        conn.close()
        return jsonify({"success": False, "error": "User not found."}), 404

    existing = conn.execute("""
        SELECT id FROM match_likes
        WHERE user_id = ? AND liked_user_id = ?
    """, (current, user_id)).fetchone()

    is_match = False
    if not existing:
        conn.execute("""
            INSERT OR IGNORE INTO match_likes (user_id, liked_user_id)
            VALUES (?, ?)
        """, (current, user_id))
        reciprocal = conn.execute("""
            SELECT id FROM match_likes
            WHERE user_id = ? AND liked_user_id = ?
        """, (user_id, current)).fetchone()
        sender = conn.execute(
            "SELECT name FROM users WHERE id = ?", (current,)
        ).fetchone()
        if sender:
            add_notification(
                conn.cursor(), user_id, current, "match_like",
                f"{sender['name']} liked you 💙"
            )
        if reciprocal:
            is_match = True
        conn.commit()

    conn.close()
    return jsonify({"success": True, "match": is_match})


@app.route("/profile-skip/<int:user_id>", methods=["POST"])
def profile_skip(user_id):
    if not login_required():
        return jsonify({"success": False, "error": "Please login first."}), 401
    conn = get_db()
    if not conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone():
        conn.close()
        return jsonify({"success": False, "error": "User not found."}), 404
    # Treat skip as a consumed candidate without creating a social notification.
    conn.execute("""
        INSERT OR IGNORE INTO match_likes (user_id, liked_user_id)
        VALUES (?, ?)
    """, (session["user_id"], user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            return render_template("forgot_password.html",
                                   message="Please enter your email address.")
        conn = get_db()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if not user:
            return render_template("forgot_password.html",
                                   message="No account found with this email.")
        # This is a local/demo reset flow. A production email token service is required
        # before treating this as a secure password-recovery system.
        session["reset_email"] = email
        return redirect(url_for("reset_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not password or not confirm:
            return render_template("reset_password.html",
                                   message="Please enter both passwords.")
        if password != confirm:
            return render_template("reset_password.html",
                                   message="Passwords do not match.")
        if len(password) < 6:
            return render_template("reset_password.html",
                                   message="Password must be at least 6 characters.")
        conn = get_db()
        conn.execute(
            "UPDATE users SET password = ? WHERE email = ?",
            (generate_password_hash(password), email)
        )
        conn.commit()
        conn.close()
        session.pop("reset_email", None)
        return redirect(url_for("login"))

    return render_template("reset_password.html")


# Informational pages.
@app.route("/help-support")
def help_support():
    return render_template("help_support.html")


@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


@app.route("/terms-of-service")
def terms_of_service():
    return render_template("terms_of_service.html")

# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def file_too_large(error):
    return (
        "File is too large. Maximum upload size is 100 MB.",
        413
    )


@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception("Unhandled server error")
    return "Something went wrong on the server. Please try again.", 500


# =========================================================
# START APPLICATION
# =========================================================

init_db()
ensure_feature_schema()

# Repair legacy relationship data on every startup.
_startup_conn = get_db()
sync_relationships(_startup_conn)
_startup_conn.close()

if __name__ == "__main__":
    # IMPORTANT: use socketio.run(), not app.run().
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    )
