from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
import secrets
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)


# =========================================================
# APPLICATION SECURITY
# =========================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "privateconnect-development-secret-key"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["UPLOAD_FOLDER"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static",
    "uploads"
)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


os.makedirs(
    app.config["UPLOAD_FOLDER"],
    exist_ok=True
)


# =========================================================
# DATABASE PATH
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATABASE = os.path.join(
    BASE_DIR,
    "users.db"
)


# =========================================================
# ALLOWED FILE TYPES
# =========================================================

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif",
    "mp4", "webm"
}

PROFILE_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp"
}





# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn

# =========================================================
# NOTIFICATION HELPER
# =========================================================

def add_notification(
    cursor,
    user_id,
    sender_id,
    notification_type,
    message
):

    cursor.execute("""
        INSERT INTO notifications
        (
            user_id,
            sender_id,
            type,
            message
        )
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        sender_id,
        notification_type,
        message
    ))


# =========================================================
# CHECK FILE TYPES
# =========================================================

def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def allowed_profile_picture(filename):

    return (
        "." in filename
        and
        filename.rsplit(".", 1)[1].lower()
        in PROFILE_EXTENSIONS
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    conn = get_db()
    cursor = conn.cursor()

    # =====================================================
    # USERS
    # =====================================================

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

    # USERS - notifications
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN notifications_enabled INTEGER DEFAULT 1
        """)
    except sqlite3.OperationalError:
        pass

    # USERS - profile visibility
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN profile_visibility TEXT DEFAULT 'everyone'
        """)
    except sqlite3.OperationalError:
        pass

    # USERS - posts visibility
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN posts_visibility TEXT DEFAULT 'everyone'
        """)
    except sqlite3.OperationalError:
        pass

    # USERS - profile views
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN profile_views_enabled INTEGER DEFAULT 1
        """)
    except sqlite3.OperationalError:
        pass

    # =====================================================
    # POSTS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            caption TEXT,
            media TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # COMMENTS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # LIKES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            UNIQUE(user_id, post_id)
        )
    """)

    # =====================================================
    # MATCH LIKES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            liked_user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, liked_user_id)
        )
    """)

    # =====================================================
    # SHARES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # FRIENDS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            UNIQUE(user_id, friend_id)
        )
    """)

    # =====================================================
    # CONNECTION REQUESTS
    # =====================================================

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

    # =====================================================
    # CONNECTIONS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user1_id, user2_id)
        )
    """)

    # =====================================================
    # MESSAGES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message TEXT,
            image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TEXT,
            read_at TEXT
        )
    """)

    # =====================================================
    # GROUPS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            group_picture TEXT,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # =====================================================
    # GROUP MEMBERS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, user_id),
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # =====================================================
    # GROUP MESSAGES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT,
            file_path TEXT,
            file_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # DATABASE MIGRATION
    # =====================================================

    # USERS - profile_picture
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN profile_picture TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # USERS - bio
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN bio TEXT DEFAULT ''
        """)
    except sqlite3.OperationalError:
        pass

    # USERS - last_seen
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN last_seen TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # MESSAGES - image
    try:
        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN image TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # MESSAGES - delivered_at
    try:
        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN delivered_at TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # MESSAGES - read_at
    try:
        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN read_at TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sender_id INTEGER,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # PROFILE VIEWS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            viewer_id INTEGER NOT NULL,
            viewed_user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

# =====================================================
# BLOCKED USERS
# =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocker_id INTEGER NOT NULL,
            blocked_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(blocker_id, blocked_id)
        )
    """)

    # =====================================================
    # SAVE DATABASE
    # =====================================================

    conn.commit()
    conn.close()

# =========================================================
# ONLINE HEARTBEAT
# =========================================================

@app.route("/heartbeat", methods=["POST"])
def heartbeat():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "online": False
        }), 401

    current_user = session["user_id"]

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # UPDATE CURRENT USER LAST SEEN
    # -----------------------------------------------------

    cursor.execute("""
        UPDATE users
        SET last_seen = ?
        WHERE id = ?
    """, (
        now,
        current_user
    ))

    # -----------------------------------------------------
    # MARK RECEIVED MESSAGES AS DELIVERED
    # -----------------------------------------------------

    cursor.execute("""
        UPDATE messages
        SET delivered_at = ?
        WHERE receiver_id = ?
        AND delivered_at IS NULL
    """, (
        now,
        current_user
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "online": True,
        "last_seen": now
    })


# =========================================================
# CHECK USER ONLINE STATUS
# =========================================================

@app.route("/user-status/<int:user_id>")
def user_status(user_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT last_seen
        FROM users
        WHERE id = ?
    """, (user_id,))

    user = cursor.fetchone()

    conn.close()

    if not user or not user["last_seen"]:
        return jsonify({"online": False})

    try:

        last_seen = datetime.strptime(
            user["last_seen"],
            "%Y-%m-%d %H:%M:%S"
        )

        online = (
    datetime.now() - last_seen
    <= timedelta(seconds=15)
)

        return jsonify({
            "online": online
        })

    except Exception:

        return jsonify({
            "online": False
        })

# =========================================================
# UPLOAD REEL
# =========================================================

@app.route(
    "/upload-reel",
    methods=["POST"]
)
def upload_reel():

    # -----------------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------------

    if "user_id" not in session:
        return redirect(url_for("login"))


    # -----------------------------------------------------
    # GET CAPTION
    # -----------------------------------------------------

    caption = request.form.get(
        "caption",
        ""
    ).strip()


    # -----------------------------------------------------
    # GET VIDEO
    # -----------------------------------------------------

    file = request.files.get(
        "reel"
    )


    if not file or not file.filename:

        return (
            "Please select a video.",
            400
        )


    # -----------------------------------------------------
    # SECURE FILENAME
    # -----------------------------------------------------

    original_filename = secure_filename(
        file.filename
    )


    if not original_filename:

        return (
            "Invalid video filename.",
            400
        )


    # -----------------------------------------------------
    # ALLOWED REEL FORMATS
    # -----------------------------------------------------

    allowed_reel_extensions = (
        ".mp4",
        ".webm",
        ".mov"
    )


    extension = os.path.splitext(
        original_filename
    )[1].lower()


    if extension not in allowed_reel_extensions:

        return (
            "Only MP4, WEBM and MOV videos are allowed.",
            400
        )


    # -----------------------------------------------------
    # CREATE UNIQUE FILENAME
    # -----------------------------------------------------

    base, extension = os.path.splitext(
        original_filename
    )


    filename = original_filename

    counter = 1


    while os.path.exists(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )
    ):

        filename = (
            f"{base}_{counter}"
            f"{extension}"
        )

        counter += 1


    # -----------------------------------------------------
    # SAVE VIDEO
    # -----------------------------------------------------

    file.save(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )
    )


    # -----------------------------------------------------
    # SAVE REEL AS VIDEO POST
    # -----------------------------------------------------

    conn = get_db()
    cursor = conn.cursor()


    cursor.execute("""
        INSERT INTO posts
        (
            user_id,
            caption,
            media
        )

        VALUES (?, ?, ?)
    """, (
        session["user_id"],
        caption,
        filename
    ))


    conn.commit()
    conn.close()


    # -----------------------------------------------------
    # GO TO REELS
    # -----------------------------------------------------

    return redirect(
        url_for("reels")
    )

# =========================================================
# REELS
# =========================================================

@app.route("/reels")
def reels():

    # -----------------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------------

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # GET ONLY VIDEO POSTS
    # -----------------------------------------------------

    cursor.execute("""
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

            EXISTS (
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

        ORDER BY posts.created_at DESC

    """, (
        session["user_id"],
    ))

    reels_data = cursor.fetchall()

    reels = []

    # -----------------------------------------------------
    # GET COMMENTS
    # -----------------------------------------------------

    for reel in reels_data:

        cursor.execute("""
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

        """, (
            reel["id"],
        ))

        comments = cursor.fetchall()

        reel_dict = dict(reel)

        reel_dict["comments"] = comments

        reels.append(reel_dict)

    conn.close()

    # -----------------------------------------------------
    # SEND REELS TO PAGE
    # -----------------------------------------------------

    return render_template(
        "reels.html",
        reels=reels
    )

# =========================================================
# GROUPS PAGE
# =========================================================

@app.route("/groups")
def groups():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            groups.id,
            groups.name,
            groups.description,
            groups.group_picture,
            groups.created_by,
            groups.created_at
        FROM groups
        JOIN group_members
            ON group_members.group_id = groups.id
        WHERE group_members.user_id = ?
        ORDER BY groups.created_at DESC
    """, (session["user_id"],))

    groups_data = cursor.fetchall()

    conn.close()

    return render_template(
        "groups.html",
        groups=groups_data
    )


# =========================================================
# CREATE GROUP
# =========================================================

@app.route("/create-group", methods=["POST"])
def create_group():

    if "user_id" not in session:
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        return "Group name is required.", 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO groups
        (name, description, created_by)
        VALUES (?, ?, ?)
    """, (
        name,
        description,
        session["user_id"]
    ))

    group_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO group_members
        (group_id, user_id, role)
        VALUES (?, ?, ?)
    """, (
        group_id,
        session["user_id"],
        "admin"
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("groups"))


# =========================================================
# GROUP CHAT
# =========================================================

@app.route("/group/<int:group_id>", methods=["GET"])
def group_chat(group_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    # Check that the logged-in user belongs to this group
    cursor.execute("""
        SELECT
            groups.id,
            groups.name,
            groups.description,
            groups.group_picture
        FROM groups
        JOIN group_members
            ON group_members.group_id = groups.id
        WHERE
            groups.id = ?
            AND group_members.user_id = ?
    """, (
        group_id,
        session["user_id"]
    ))

    group = cursor.fetchone()

    if not group:
        conn.close()
        return "Group not found or you are not a member.", 404

    # Get group messages
    cursor.execute("""
        SELECT
            group_messages.id,
            group_messages.group_id,
            group_messages.sender_id,
            group_messages.message,
            group_messages.file_path,
            group_messages.file_type,
            group_messages.created_at,
            users.name AS sender_name
        FROM group_messages
        JOIN users
            ON users.id = group_messages.sender_id
        WHERE group_messages.group_id = ?
        ORDER BY group_messages.created_at ASC
    """, (group_id,))

    messages = cursor.fetchall()

    conn.close()

    return render_template(
        "group_chat.html",
        group=group,
        messages=messages
    )

# =========================================================
# GROUP MEMBERS
# =========================================================

@app.route("/group/<int:group_id>/members")
def group_members(group_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    # Check that the logged-in user is a member
    cursor.execute("""
        SELECT
            groups.id,
            groups.name
        FROM groups
        JOIN group_members
            ON group_members.group_id = groups.id
        WHERE
            groups.id = ?
            AND group_members.user_id = ?
    """, (
        group_id,
        session["user_id"]
    ))

    group = cursor.fetchone()

    if not group:
        conn.close()
        return "Group not found or you are not a member.", 404

    # Get all group members
    cursor.execute("""
        SELECT
            users.id,
            users.name,
            users.profile_picture,
            group_members.role,
            group_members.joined_at
        FROM group_members
        JOIN users
            ON users.id = group_members.user_id
        WHERE group_members.group_id = ?
        ORDER BY
            CASE
                WHEN group_members.role = 'admin' THEN 0
                ELSE 1
            END,
            users.name ASC
    """, (group_id,))

    members = cursor.fetchall()

    conn.close()

    return render_template(
        "group_members.html",
        group=group,
        members=members
    )


# =========================================================
# SEND GROUP MESSAGE
# =========================================================

@app.route("/group/<int:group_id>/send", methods=["POST"])
def send_group_message(group_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    message = request.form.get("message", "").strip()

    if not message:
        return redirect(url_for(
            "group_chat",
            group_id=group_id
        ))

    conn = get_db()
    cursor = conn.cursor()

    # Check membership
    cursor.execute("""
        SELECT id
        FROM group_members
        WHERE group_id = ?
        AND user_id = ?
    """, (
        group_id,
        session["user_id"]
    ))

    member = cursor.fetchone()

    if not member:
        conn.close()
        return "You are not a member of this group.", 403

    # Save message
    cursor.execute("""
        INSERT INTO group_messages
        (
            group_id,
            sender_id,
            message
        )
        VALUES (?, ?, ?)
    """, (
        group_id,
        session["user_id"],
        message
    ))

    conn.commit()
    conn.close()

    return redirect(url_for(
        "group_chat",
        group_id=group_id
    ))


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    # If user is already logged in
    if "user_id" in session:

        return redirect(
            url_for("dashboard")
        )

    # If user is not logged in
    return redirect(
        url_for("login")
    )


# =========================================================
# SIGN UP
# =========================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:

            return (
                "All fields are required.",
                400
            )

        if len(password) < 6:

            return (
                "Password must contain at least 6 characters.",
                400
            )

        # Hash password before storing
        hashed_password = generate_password_hash(
            password
        )

        conn = get_db()
        cursor = conn.cursor()

        try:

            cursor.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password
                )
                VALUES (?, ?, ?)
            """, (
                name,
                email,
                hashed_password
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return (
                "Email already registered!",
                400
            )

        conn.close()

        return "Sign Up Successful!"

    return render_template(
        "signup.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:

            return (
                "Email and password are required.",
                400
            )

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                name,
                email,
                password
            FROM users
            WHERE email = ?
        """, (
            email,
        ))

        user = cursor.fetchone()

        conn.close()

        # User not found
        if not user:

            return (
                "Invalid email or password.",
                401
            )

        # Check password
        if not check_password_hash(
            user["password"],
            password
        ):

            return (
                "Invalid email or password.",
                401
            )

        # -------------------------------------------------
        # CREATE SESSION
        # -------------------------------------------------

        session["user_id"] = user["id"]

        session["user_name"] = user["name"]

        session["user_email"] = user["email"]

        # -------------------------------------------------
        # UPDATE LAST SEEN
        # -------------------------------------------------

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users
            SET last_seen = ?
            WHERE id = ?
        """, (
            now,
            user["id"]
        ))

        conn.commit()
        conn.close()

        # -------------------------------------------------
        # GO TO DASHBOARD
        # -------------------------------------------------

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        if not email:
            return render_template(
                "forgot_password.html",
                message="Please enter your email address."
            )

        conn = get_db()

        user = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if not user:
            return render_template(
                "forgot_password.html",
                message="No account found with this email."
            )

        # Store the email temporarily for the reset page
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
        confirm_password = request.form.get("confirm_password", "")

        if not password or not confirm_password:
            return render_template(
                "reset_password.html",
                message="Please enter both passwords."
            )

        if password != confirm_password:
            return render_template(
                "reset_password.html",
                message="Passwords do not match."
            )

        if len(password) < 6:
            return render_template(
                "reset_password.html",
                message="Password must be at least 6 characters."
            )

        hashed_password = generate_password_hash(password)

        conn = get_db()

        conn.execute(
            """
            UPDATE users
            SET password = ?
            WHERE email = ?
            """,
            (hashed_password, email)
        )

        conn.commit()
        conn.close()

        session.pop("reset_email", None)

        return redirect(url_for("login"))

    return render_template("reset_password.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    conn = get_db()
    cursor = conn.cursor()



    # =====================================================
    # GET OTHER USERS
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            name,
            profile_picture,
            bio,
            last_seen
        FROM users
        WHERE id != ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    ))

    users = cursor.fetchall()

    # =====================================================
    # GET POSTS
    # =====================================================

    cursor.execute("""
        SELECT

            posts.id,

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

            EXISTS (
                SELECT 1
                FROM likes

                WHERE likes.post_id = posts.id

                AND likes.user_id = ?
            ) AS user_liked

        FROM posts

        JOIN users
        ON users.id = posts.user_id

        ORDER BY posts.created_at DESC

    """, (
        session["user_id"],
    ))

    posts_data = cursor.fetchall()

    posts = []

    # =====================================================
    # GET COMMENTS
    # =====================================================

    for post in posts_data:

        cursor.execute("""
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

        """, (
            post["id"],
        ))

        comments = cursor.fetchall()

        post_dict = dict(post)

        post_dict["comments"] = comments

        posts.append(post_dict)

    conn.close()

    # =====================================================
    # SEND USERS + POSTS TO DASHBOARD
    # =====================================================

    return render_template(
        "dashboard.html",
        users=users,
        posts=posts
    )

# =========================================================
# NOTIFICATION COUNT
# =========================================================

@app.route("/notification-count")
def notification_count():

    if "user_id" not in session:
        return jsonify({
            "count": 0
        })

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE user_id = ?
        AND is_read = 0
    """, (
        session["user_id"],
    ))

    count = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "count": count
    })

# =========================================================
# NOTIFICATIONS LIST
# =========================================================

@app.route("/notifications")
def notifications():

    if "user_id" not in session:
        return jsonify({
            "notifications": []
        })

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            notifications.id,
            notifications.type,
            notifications.message,
            notifications.is_read,
            notifications.created_at,
            notifications.sender_id,
            users.name AS sender_name,
            users.profile_picture AS sender_picture
        FROM notifications
        LEFT JOIN users
            ON users.id = notifications.sender_id
        WHERE notifications.user_id = ?
        ORDER BY notifications.created_at DESC
        LIMIT 50
    """, (
        session["user_id"],
    ))

    rows = cursor.fetchall()

    conn.close()

    notification_list = []

    for row in rows:

        notification = dict(row)

        # Decide where notification should open
        if notification["type"] == "message":

            notification["url"] = url_for(
                "messages"
            )

        elif notification["type"] == "match":

            notification["url"] = url_for(
                "match"
            )

        elif notification["type"] == "connection_request":

            notification["url"] = url_for(
                "requests"
            )

        elif notification["sender_id"]:

            notification["url"] = url_for(
                "profile",
                user_id=notification["sender_id"]
            )

        else:

            notification["url"] = url_for(
                "dashboard"
            )

        notification_list.append(
            notification
        )

    return jsonify({
        "notifications": notification_list
    })

# =========================================================
# MARK NOTIFICATIONS READ
# =========================================================

@app.route("/notifications/read", methods=["POST"])
def mark_notifications_read():

    if "user_id" not in session:
        return jsonify({
            "success": False
        }), 401

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE user_id = ?
        AND is_read = 0
    """, (
        session["user_id"],
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })

# =========================================================
# MATCH PAGE
# =========================================================

@app.route("/match")
def match():

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            users.id,
            users.name,
            users.profile_picture,
            users.bio
        FROM users
        WHERE users.id != ?
        AND users.id NOT IN (
            SELECT liked_user_id
            FROM match_likes
            WHERE user_id = ?
        )
        ORDER BY RANDOM()
        LIMIT 1
    """, (
        current_user,
        current_user
    ))

    user = cursor.fetchone()

    conn.close()

    return render_template(
        "match.html",
        user=user
    )



# =========================================================
# MATCH LIKE
# =========================================================

@app.route(
    "/profile-like/<int:user_id>",
    methods=["POST"]
)
def profile_like(user_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please login first."
        }), 401

    current_user = session["user_id"]

    # Cannot like yourself
    if current_user == user_id:
        return jsonify({
            "success": False,
            "error": "You cannot like yourself."
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    # =====================================================
    # CHECK TARGET USER
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    target_user = cursor.fetchone()

    if target_user is None:

        conn.close()

        return jsonify({
            "success": False,
            "error": "User not found."
        }), 404

    # =====================================================
    # CHECK IF ALREADY LIKED
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM match_likes
        WHERE user_id = ?
        AND liked_user_id = ?
    """, (
        current_user,
        user_id
    ))

    existing_like = cursor.fetchone()

    # =====================================================
    # SAVE NEW LIKE
    # =====================================================

    if not existing_like:

        cursor.execute("""
            INSERT INTO match_likes
            (
                user_id,
                liked_user_id
            )
            VALUES (?, ?)
        """, (
            current_user,
            user_id
        ))

        # =================================================
        # GET SENDER NAME
        # =================================================

        cursor.execute("""
            SELECT name
            FROM users
            WHERE id = ?
        """, (
            current_user,
        ))

        sender = cursor.fetchone()

        # =================================================
        # SEND LIKE NOTIFICATION
        # =================================================

        if sender:

            add_notification(
                cursor,
                user_id,
                current_user,
                "match_like",
                f"{sender['name']} liked you 💙"
            )

    # =====================================================
    # CHECK MUTUAL LIKE
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM match_likes
        WHERE user_id = ?
        AND liked_user_id = ?
    """, (
        user_id,
        current_user
    ))

    mutual_like = cursor.fetchone()

    # =====================================================
    # SEND MATCH NOTIFICATION
    # =====================================================

    if mutual_like:

        cursor.execute("""
            SELECT name
            FROM users
            WHERE id = ?
        """, (
            current_user,
        ))

        sender = cursor.fetchone()

        if sender:

            add_notification(
                cursor,
                user_id,
                current_user,
                "match",
                f"It's a Match with {sender['name']}! 💙"
            )

    # =====================================================
    # SAVE DATABASE
    # =====================================================

    conn.commit()
    conn.close()

    # =====================================================
    # RETURN RESULT
    # =====================================================

    if mutual_like:

        return jsonify({
            "success": True,
            "match": True,
            "message": "It's a Match! 💙"
        })

    return jsonify({
        "success": True,
        "match": False,
        "message": "Like sent 💙"
    })


# =========================================================
# CREATE POST
# =========================================================

@app.route(
    "/create-post",
    methods=["POST"]
)
def create_post():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    caption = request.form.get(
        "caption",
        ""
    ).strip()


    file = request.files.get(
        "media"
    )


    filename = None


    if file and file.filename:

        original_filename = secure_filename(
            file.filename
        )


        if not original_filename:

            return (
                "Invalid filename.",
                400
            )


        if not allowed_file(
            original_filename
        ):

            return (
                "File type not allowed.",
                400
            )


        base, extension = os.path.splitext(
            original_filename
        )


        filename = original_filename

        counter = 1


        while os.path.exists(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
        ):

            filename = (
                f"{base}_{counter}"
                f"{extension}"
            )

            counter += 1


        file.save(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
        )


    if not caption and not filename:

        return (
            "Please add a caption or photo/video.",
            400
        )


    conn = get_db()

    cursor = conn.cursor()


    cursor.execute("""
        INSERT INTO posts
        (
            user_id,
            caption,
            media
        )

        VALUES (?, ?, ?)

    """, (
        session["user_id"],
        caption,
        filename
    ))


    conn.commit()

    conn.close()


    return redirect(
        url_for("dashboard")
    )

# =========================================================
# DELETE POST
# =========================================================

@app.route("/delete-post/<int:post_id>", methods=["POST"])
def delete_post(post_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    # Check that this post belongs to the logged-in user
    cursor.execute("""
        SELECT media
        FROM posts
        WHERE id = ?
        AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    ))

    post = cursor.fetchone()

    if post is None:
        conn.close()
        return "Post not found or you don't have permission to delete it.", 404

    # Delete likes for this post
    cursor.execute("""
        DELETE FROM likes
        WHERE post_id = ?
    """, (post_id,))

    # Delete the post
    cursor.execute("""
        DELETE FROM posts
        WHERE id = ?
        AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("profile"))

# =========================================================
# DELETE REEL
# =========================================================

@app.route("/delete-reel/<int:post_id>", methods=["POST"])
def delete_reel(post_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT media
        FROM posts
        WHERE id = ?
        AND user_id = ?
        AND (
            LOWER(media) LIKE '%.mp4'
            OR LOWER(media) LIKE '%.webm'
            OR LOWER(media) LIKE '%.mov'
        )
    """, (
        post_id,
        session["user_id"]
    ))

    reel = cursor.fetchone()

    if not reel:
        conn.close()
        return "You cannot delete this reel.", 403

    if reel["media"]:

        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            reel["media"]
        )

        if os.path.exists(file_path):
            os.remove(file_path)

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
    conn.close()

    return redirect(url_for("reels"))


# =========================================================
# LIKE / UNLIKE
# =========================================================

@app.route(
    "/like/<int:post_id>",
    methods=["POST"]
)
def like(post_id):

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "error": "Please login first."
        }), 401


    conn = get_db()

    cursor = conn.cursor()


    # =====================================================
    # CHECK POST
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM posts
        WHERE id = ?
    """, (
        post_id,
    ))

    post = cursor.fetchone()


    if post is None:

        conn.close()

        return jsonify({
            "success": False,
            "error": "Post not found."
        }), 404


    # =====================================================
    # CHECK EXISTING LIKE
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM likes
        WHERE user_id = ?
        AND post_id = ?
    """, (
        session["user_id"],
        post_id
    ))

    existing_like = cursor.fetchone()


    # =====================================================
    # UNLIKE
    # =====================================================

    if existing_like:

        cursor.execute("""
            DELETE FROM likes
            WHERE user_id = ?
            AND post_id = ?
        """, (
            session["user_id"],
            post_id
        ))

        liked = False


    # =====================================================
    # LIKE
    # =====================================================

    else:

        cursor.execute("""
            INSERT INTO likes
            (
                user_id,
                post_id
            )
            VALUES (?, ?)
        """, (
            session["user_id"],
            post_id
        ))

        liked = True

        # =================================================
        # SEND LIKE NOTIFICATION
        # =================================================

        cursor.execute("""
            SELECT user_id
            FROM posts
            WHERE id = ?
        """, (
            post_id,
        ))

        post_owner = cursor.fetchone()

        if post_owner and post_owner["user_id"] != session["user_id"]:

            cursor.execute("""
                SELECT name
                FROM users
                WHERE id = ?
            """, (
                session["user_id"],
            ))

            sender = cursor.fetchone()

            if sender:

                add_notification(
                    cursor,
                    post_owner["user_id"],
                    session["user_id"],
                    "post_like",
                    f"{sender['name']} liked your post ❤️"
                )


    # =====================================================
    # GET NEW LIKE COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM likes
        WHERE post_id = ?
    """, (
        post_id,
    ))

    like_count = cursor.fetchone()[0]


    conn.commit()

    conn.close()


    # =====================================================
    # RETURN JSON
    # =====================================================

    return jsonify({

        "success": True,

        "liked": liked,

        "like_count": like_count

    })


# =========================================================
# ADD COMMENT
# =========================================================

@app.route(
    "/comment/<int:post_id>",
    methods=["POST"]
)
def comment(post_id):

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "error": "Please login first."
        }), 401


    # =====================================================
    # GET COMMENT TEXT
    # =====================================================

    comment_text = request.form.get(
        "comment",
        ""
    ).strip()


    # =====================================================
    # EMPTY COMMENT
    # =====================================================

    if not comment_text:

        return jsonify({
            "success": False,
            "error": "Comment cannot be empty."
        }), 400


    # =====================================================
    # COMMENT LENGTH
    # =====================================================

    if len(comment_text) > 500:

        return jsonify({
            "success": False,
            "error": "Comment is too long."
        }), 400


    conn = get_db()

    cursor = conn.cursor()


    # =====================================================
    # CHECK POST
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM posts
        WHERE id = ?
    """, (
        post_id,
    ))

    post = cursor.fetchone()


    if not post:

        conn.close()

        return jsonify({
            "success": False,
            "error": "Post not found."
        }), 404


    # =====================================================
    # INSERT COMMENT
    # =====================================================

    cursor.execute("""
        INSERT INTO comments
        (
            user_id,
            post_id,
            comment
        )
        VALUES (?, ?, ?)
    """, (
        session["user_id"],
        post_id,
        comment_text
    ))

    
    # =====================================================
    # GET USER NAME
    # =====================================================

    cursor.execute("""
        SELECT name
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    ))

    user = cursor.fetchone()


    user_name = user["name"] if user else "User"

# =====================================================
    # GET POST OWNER
    # =====================================================

    cursor.execute("""
        SELECT user_id
        FROM posts
        WHERE id = ?
    """, (
        post_id,
    ))

    post_owner = cursor.fetchone()


    # =====================================================
    # SEND COMMENT NOTIFICATION
    # =====================================================

    if post_owner:

        if post_owner["user_id"] != session["user_id"]:

            add_notification(
                cursor,
                post_owner["user_id"],
                session["user_id"],
                "comment",
                f"{user_name} commented on your post 💬"
            )


    # =====================================================
    # GET COMMENT COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM comments
        WHERE post_id = ?
    """, (
        post_id,
    ))

    comment_count = cursor.fetchone()[0]


    conn.commit()

    conn.close()


    # =====================================================
    # RETURN JSON
    # =====================================================

    return jsonify({

        "success": True,

        "name": user_name,

        "comment": comment_text,

        "comment_count": comment_count

    })

# =========================================================
# SHARE POST
# =========================================================

@app.route(
    "/share/<int:post_id>",
    methods=["POST"]
)
def share(post_id):

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "error": "Please login first."
        }), 401

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # CHECK POST
    # -----------------------------------------------------

    cursor.execute("""
        SELECT id, user_id
        FROM posts
        WHERE id = ?
    """, (
        post_id,
    ))

    post = cursor.fetchone()

    if post is None:

        conn.close()

        return jsonify({
            "success": False,
            "error": "Post not found."
        }), 404

    # -----------------------------------------------------
    # SAVE SHARE
    # -----------------------------------------------------

    cursor.execute("""
        INSERT INTO shares
        (
            user_id,
            post_id
        )
        VALUES (?, ?)
    """, (
        session["user_id"],
        post_id
    ))

    # -----------------------------------------------------
    # SEND SHARE NOTIFICATION
    # -----------------------------------------------------

    post_owner_id = post["user_id"]

    if post_owner_id != session["user_id"]:

        cursor.execute("""
            SELECT name
            FROM users
            WHERE id = ?
        """, (
            session["user_id"],
        ))

        sender = cursor.fetchone()

        if sender:

            add_notification(
                cursor,
                post_owner_id,
                session["user_id"],
                "share",
                f"{sender['name']} shared your post 🔄"
            )

    # -----------------------------------------------------
    # SAVE DATABASE
    # -----------------------------------------------------

    conn.commit()
    conn.close()

    # -----------------------------------------------------
    # SHARE URL
    # -----------------------------------------------------

    share_url = (
        request.host_url.rstrip("/")
        + "/dashboard#post-"
        + str(post_id)
    )

    return jsonify({
        "success": True,
        "url": share_url
    })

# =====================================================
# SETTINGS
# =====================================================

@app.route("/settings")
def settings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            profile_picture,
            bio
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    ))

    user = cursor.fetchone()

    conn.close()

    if user is None:
        return redirect(url_for("login"))

    return render_template(
        "settings.html",
        user=user
    )

@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_password or not new_password or not confirm_password:
            return render_template(
                "change_password.html",
                error="Please fill all fields."
            )

        if new_password != confirm_password:
            return render_template(
                "change_password.html",
                error="New passwords do not match."
            )

        if len(new_password) < 6:
            return render_template(
                "change_password.html",
                error="Password must be at least 6 characters."
            )

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT password
            FROM users
            WHERE id = ?
        """, (
            session["user_id"],
        ))

        user = cursor.fetchone()

        if not user:
            conn.close()
            return redirect(url_for("login"))

        if not check_password_hash(
            user["password"],
            current_password
        ):
            conn.close()

            return render_template(
                "change_password.html",
                error="Current password is incorrect."
            )

        new_password_hash = generate_password_hash(
            new_password
        )

        cursor.execute("""
            UPDATE users
            SET password = ?
            WHERE id = ?
        """, (
            new_password_hash,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return render_template(
            "change_password.html",
            success="Password changed successfully."
        )

    return render_template(
        "change_password.html"
    )

# =========================================================
# NOTIFICATION SETTINGS
# =========================================================

@app.route(
    "/notification-settings",
    methods=["GET", "POST"]
)
def notification_settings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":

        enabled = request.form.get(
            "notifications_enabled"
        )

        if enabled == "1":
            value = 1
        else:
            value = 0

        cursor.execute("""
            UPDATE users
            SET notifications_enabled = ?
            WHERE id = ?
        """, (
            value,
            session["user_id"]
        ))

        conn.commit()

    cursor.execute("""
        SELECT notifications_enabled
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    ))

    user = cursor.fetchone()

    conn.close()

    if user is None:
        return redirect(url_for("login"))

    return render_template(
        "notification_settings.html",
        user=user
    )

@app.route(
    "/privacy-settings",
    methods=["GET", "POST"]
)
def privacy_settings():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":

        profile_visibility = request.form.get(
            "profile_visibility",
            "everyone"
        )

        posts_visibility = request.form.get(
            "posts_visibility",
            "everyone"
        )

        profile_views_enabled = request.form.get(
            "profile_views_enabled"
        )

        if profile_visibility not in [
            "everyone",
            "friends",
            "only_me"
        ]:
            profile_visibility = "everyone"

        if posts_visibility not in [
            "everyone",
            "friends"
        ]:
            posts_visibility = "everyone"

        if profile_views_enabled == "1":
            views_value = 1
        else:
            views_value = 0

        cursor.execute("""
            UPDATE users
            SET
                profile_visibility = ?,
                posts_visibility = ?,
                profile_views_enabled = ?
            WHERE id = ?
        """, (
            profile_visibility,
            posts_visibility,
            views_value,
            session["user_id"]
        ))

        conn.commit()

    cursor.execute("""
        SELECT
            profile_visibility,
            posts_visibility,
            profile_views_enabled
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    ))

    user = cursor.fetchone()

    conn.close()

    if user is None:
        return redirect(url_for("login"))

    return render_template(
        "privacy_settings.html",
        user=user
    )

# =========================================================
# BLOCK USER
# =========================================================

@app.route(
    "/block-user/<int:user_id>",
    methods=["POST"]
)
def block_user(user_id):

    # Check login
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # Cannot block yourself
    if current_user == user_id:
        return redirect(
            url_for(
                "profile",
                user_id=user_id
            )
        )

    conn = get_db()
    cursor = conn.cursor()

    # Check whether the user exists
    cursor.execute("""
        SELECT id
        FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    user = cursor.fetchone()

    if user is None:
        conn.close()
        return "User not found.", 404

    # Add blocked user
    cursor.execute("""
        INSERT OR IGNORE INTO blocked_users
        (
            blocker_id,
            blocked_id
        )
        VALUES (?, ?)
    """, (
        current_user,
        user_id
    ))

    # Remove friendship
    cursor.execute("""
        DELETE FROM connections
        WHERE
            (user1_id = ? AND user2_id = ?)
            OR
            (user1_id = ? AND user2_id = ?)
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    # Remove pending friend requests
    cursor.execute("""
        DELETE FROM connection_requests
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "profile",
            user_id=user_id
        )
    )
# =========================================================
# BLOCKED USERS
# =========================================================

@app.route("/blocked-users")
def blocked_users():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            blocked_users.id,
            blocked_users.blocked_id,
            users.name,
            users.profile_picture

        FROM blocked_users

        JOIN users
        ON users.id = blocked_users.blocked_id

        WHERE blocked_users.blocker_id = ?

        ORDER BY blocked_users.created_at DESC
    """, (
        session["user_id"],
    ))

    blocked = cursor.fetchall()

    conn.close()

    return render_template(
        "blocked_users.html",
        blocked=blocked
    )

# =========================================================
# UNBLOCK USER
# =========================================================

@app.route(
    "/unblock-user/<int:user_id>",
    methods=["POST"]
)
def unblock_user(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM blocked_users
        WHERE
            blocker_id = ?
            AND blocked_id = ?
    """, (
        current_user,
        user_id
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for("blocked_users")
    )
# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
@app.route("/profile/<int:user_id>")
def profile(user_id=None):

    # =====================================================
    # LOGIN CHECK
    # =====================================================

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    current_user = session["user_id"]

    # =====================================================
    # GET PROFILE USER ID
    # =====================================================

    # Supports:
    # /profile
    # /profile?user_id=5
    # /profile/5

    profile_id = user_id

    if profile_id is None:

        profile_id = request.args.get(
            "user_id",
            type=int
        )

    # If no user ID was provided,
    # show the logged-in user's profile.

    if profile_id is None:
        profile_id = current_user

    # =====================================================
    # GET PROFILE
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            profile_picture,
            bio,
            last_seen,
            profile_visibility,
            posts_visibility,
            profile_views_enabled
        FROM users
        WHERE id = ?
    """, (profile_id,))

    person = cursor.fetchone()

    # =====================================================
    # USER NOT FOUND
    # =====================================================

    if person is None:

        conn.close()

        return """
        <!DOCTYPE html>
        <html lang="en">

        <head>

            <meta charset="UTF-8">

            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            >

            <title>User Not Found - PrivateConnect</title>

            <style>

                * {
                    box-sizing: border-box;
                }

                body {
                    margin: 0;
                    min-height: 100vh;

                    display: flex;
                    align-items: center;
                    justify-content: center;

                    font-family: Arial, sans-serif;

                    background:
                        radial-gradient(
                            circle at top,
                            #172554,
                            #020617 55%
                        );

                    color: white;

                    padding: 20px;
                }

                .box {
                    width: 100%;
                    max-width: 420px;

                    text-align: center;

                    padding: 40px 25px;

                    border-radius: 24px;

                    background:
                        rgba(15, 23, 42, 0.95);

                    border:
                        1px solid
                        rgba(255,255,255,0.10);

                    box-shadow:
                        0 20px 50px
                        rgba(0,0,0,0.35);
                }

                .icon {
                    width: 80px;
                    height: 80px;

                    margin: 0 auto 20px;

                    display: flex;
                    align-items: center;
                    justify-content: center;

                    border-radius: 50%;

                    font-size: 36px;

                    background:
                        linear-gradient(
                            135deg,
                            #1d4ed8,
                            #334155
                        );
                }

                h2 {
                    margin: 0 0 10px;

                    font-size: 25px;
                }

                p {
                    margin: 0;

                    color: #94a3b8;

                    line-height: 1.6;
                }

                .buttons {
                    display: flex;

                    gap: 10px;

                    margin-top: 25px;
                }

                a {
                    flex: 1;

                    padding: 13px 16px;

                    border-radius: 12px;

                    text-decoration: none;

                    color: white;

                    font-weight: 700;

                    background:
                        linear-gradient(
                            135deg,
                            #2563eb,
                            #1d4ed8
                        );
                }

                a.secondary {
                    background:
                        #334155;
                }

                @media (max-width: 480px) {

                    .buttons {
                        flex-direction: column;
                    }

                }

            </style>

        </head>

        <body>

            <div class="box">

                <div class="icon">
                    👤
                </div>

                <h2>
                    User Not Found
                </h2>

                <p>
                    This profile may no longer exist
                    or the profile link is invalid.
                </p>

                <div class="buttons">

                    <a href="/find-people">
                        Find People
                    </a>

                    <a
                        href="/dashboard"
                        class="secondary"
                    >
                        Dashboard
                    </a>

                </div>

            </div>

        </body>

        </html>
        """, 404

    # =====================================================
    # CHECK OWN PROFILE
    # =====================================================

    is_own_profile = (
        profile_id == current_user
    )

    # =====================================================
    # CHECK FRIENDSHIP
    # =====================================================

    is_friend = False
    connection = None

    if not is_own_profile:

        cursor.execute("""
            SELECT id
            FROM connections
            WHERE
                (
                    user1_id = ?
                    AND user2_id = ?
                )
                OR
                (
                    user1_id = ?
                    AND user2_id = ?
                )
            LIMIT 1
        """, (
            current_user,
            profile_id,
            profile_id,
            current_user
        ))

        connection = cursor.fetchone()

        is_friend = (
            connection is not None
        )

    # =====================================================
    # PROFILE PRIVACY
    # =====================================================

    profile_visibility = person["profile_visibility"]

    if profile_visibility is None:
        profile_visibility = "everyone"

    # =====================================================
    # CHECK BLOCK STATUS
    # =====================================================

    if not is_own_profile:

        cursor.execute("""
            SELECT id
            FROM blocked_users
            WHERE
                (
                    blocker_id = ?
                    AND blocked_id = ?
                )
                OR
                (
                    blocker_id = ?
                    AND blocked_id = ?
                )
            LIMIT 1
        """, (
            current_user,
            profile_id,
            profile_id,
            current_user
        ))

        blocked_record = cursor.fetchone()

        if blocked_record:

            conn.close()

            return """
            <!DOCTYPE html>

            <html lang="en">

            <head>

                <meta charset="UTF-8">

                <meta
                    name="viewport"
                    content="width=device-width, initial-scale=1.0"
                >

                <title>
                    Profile Unavailable - PrivateConnect
                </title>

                <style>

                    * {
                        box-sizing: border-box;
                    }

                    body {
                        margin: 0;

                        min-height: 100vh;

                        display: flex;
                        align-items: center;
                        justify-content: center;

                        padding: 20px;

                        font-family: Arial, sans-serif;

                        background: #020617;

                        color: white;
                    }

                    .box {
                        width: 100%;
                        max-width: 420px;

                        text-align: center;

                        padding: 40px 25px;

                        border-radius: 24px;

                        background: #0f172a;

                        border:
                            1px solid
                            rgba(255,255,255,0.10);

                        box-shadow:
                            0 20px 50px
                            rgba(0,0,0,0.35);
                    }

                    .icon {
                        font-size: 55px;

                        margin-bottom: 15px;
                    }

                    h2 {
                        margin: 0 0 10px;
                    }

                    p {
                        color: #94a3b8;

                        line-height: 1.6;
                    }

                    a {
                        display: inline-block;

                        margin-top: 20px;

                        padding: 13px 22px;

                        background: #2563eb;

                        color: white;

                        text-decoration: none;

                        border-radius: 12px;

                        font-weight: 700;
                    }

                </style>

            </head>

            <body>

                <div class="box">

                    <div class="icon">
                        🚫
                    </div>

                    <h2>
                        Profile Unavailable
                    </h2>

                    <p>
                        You cannot view this profile because
                        one of you has blocked the other.
                    </p>

                    <a href="/find-people">
                        Find People
                    </a>

                </div>

            </body>

            </html>
            """, 403

    # =====================================================
    # FRIENDS ONLY PROFILE
    # =====================================================

    if (
        not is_own_profile
        and profile_visibility == "friends"
        and not is_friend
    ):

        conn.close()

        return """
        <!DOCTYPE html>

        <html lang="en">

        <head>

            <meta charset="UTF-8">

            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            >

            <title>
                Private Profile - PrivateConnect
            </title>

            <style>

                * {
                    box-sizing: border-box;
                }

                body {
                    margin: 0;

                    min-height: 100vh;

                    display: flex;
                    align-items: center;
                    justify-content: center;

                    padding: 20px;

                    font-family: Arial, sans-serif;

                    background: #020617;

                    color: white;
                }

                .box {
                    width: 100%;
                    max-width: 420px;

                    text-align: center;

                    padding: 40px 25px;

                    border-radius: 24px;

                    background: #0f172a;

                    border:
                        1px solid
                        rgba(255,255,255,0.10);

                    box-shadow:
                        0 20px 50px
                        rgba(0,0,0,0.35);
                }

                .icon {
                    font-size: 55px;

                    margin-bottom: 15px;
                }

                h2 {
                    margin: 0 0 10px;
                }

                p {
                    color: #94a3b8;

                    line-height: 1.6;
                }

                a {
                    display: inline-block;

                    margin-top: 20px;

                    padding: 13px 22px;

                    background: #2563eb;

                    color: white;

                    text-decoration: none;

                    border-radius: 12px;

                    font-weight: 700;
                }

            </style>

        </head>

        <body>

            <div class="box">

                <div class="icon">
                    🔒
                </div>

                <h2>
                    Private Profile
                </h2>

                <p>
                    This profile is visible to friends only.
                </p>

                <a href="/find-people">
                    Find People
                </a>

            </div>

        </body>

        </html>
        """, 403

    # =====================================================
    # ONLY ME
    # =====================================================

    if (
        not is_own_profile
        and profile_visibility == "only_me"
    ):

        conn.close()

        return """
        <!DOCTYPE html>

        <html lang="en">

        <head>

            <meta charset="UTF-8">

            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            >

            <title>
                Private Profile - PrivateConnect
            </title>

            <style>

                * {
                    box-sizing: border-box;
                }

                body {
                    margin: 0;

                    min-height: 100vh;

                    display: flex;
                    align-items: center;
                    justify-content: center;

                    padding: 20px;

                    font-family: Arial, sans-serif;

                    background: #020617;

                    color: white;
                }

                .box {
                    width: 100%;
                    max-width: 420px;

                    text-align: center;

                    padding: 40px 25px;

                    border-radius: 24px;

                    background: #0f172a;

                    border:
                        1px solid
                        rgba(255,255,255,0.10);

                    box-shadow:
                        0 20px 50px
                        rgba(0,0,0,0.35);
                }

                .icon {
                    font-size: 55px;

                    margin-bottom: 15px;
                }

                h2 {
                    margin: 0 0 10px;
                }

                p {
                    color: #94a3b8;

                    line-height: 1.6;
                }

                a {
                    display: inline-block;

                    margin-top: 20px;

                    padding: 13px 22px;

                    background: #2563eb;

                    color: white;

                    text-decoration: none;

                    border-radius: 12px;

                    font-weight: 700;
                }

            </style>

        </head>

        <body>

            <div class="box">

                <div class="icon">
                    🔐
                </div>

                <h2>
                    Private Profile
                </h2>

                <p>
                    This user has chosen to keep
                    their profile private.
                </p>

                <a href="/find-people">
                    Find People
                </a>

            </div>

        </body>

        </html>
        """, 403

    # =====================================================
    # RECORD PROFILE VIEW
    # =====================================================

    if (
        not is_own_profile
        and person["profile_views_enabled"]
    ):

        cursor.execute("""
            INSERT INTO profile_views (
                viewer_id,
                viewed_user_id
            )
            VALUES (?, ?)
        """, (
            current_user,
            profile_id
        ))

        conn.commit()

    # =====================================================
    # GET USER POSTS
    # =====================================================

    posts = []

    posts_visibility = person["posts_visibility"]

    if posts_visibility is None:
        posts_visibility = "everyone"

    # =====================================================
    # LOAD POSTS
    # =====================================================

    if (
        is_own_profile
        or posts_visibility == "everyone"
        or is_friend
    ):

        cursor.execute("""
            SELECT
                posts.id,
                posts.user_id,
                posts.caption,
                posts.media,
                posts.created_at,
                COUNT(likes.id) AS like_count

            FROM posts

            LEFT JOIN likes
                ON likes.post_id = posts.id

            WHERE posts.user_id = ?

            GROUP BY
                posts.id,
                posts.user_id,
                posts.caption,
                posts.media,
                posts.created_at

            ORDER BY posts.created_at DESC
        """, (profile_id,))

        posts = cursor.fetchall()

    # =====================================================
    # RELATIONSHIP STATUS
    # =====================================================

    relationship_status = "none"

    pending_request_id = None

    # =====================================================
    # OWN PROFILE
    # =====================================================

    if is_own_profile:

        relationship_status = "own"

    else:

        # =================================================
        # ALREADY FRIENDS
        # =================================================

        if connection:

            relationship_status = "friends"

        else:

            # =============================================
            # OUTGOING REQUEST
            # =============================================

            cursor.execute("""
                SELECT id
                FROM connection_requests
                WHERE
                    sender_id = ?
                    AND receiver_id = ?
                    AND status = 'pending'
                LIMIT 1
            """, (
                current_user,
                profile_id
            ))

            outgoing_request = cursor.fetchone()

            if outgoing_request:

                relationship_status = "sent"

                pending_request_id = (
                    outgoing_request["id"]
                )

            else:

                # =========================================
                # INCOMING REQUEST
                # =========================================

                cursor.execute("""
                    SELECT id
                    FROM connection_requests
                    WHERE
                        sender_id = ?
                        AND receiver_id = ?
                        AND status = 'pending'
                    LIMIT 1
                """, (
                    profile_id,
                    current_user
                ))

                incoming_request = cursor.fetchone()

                if incoming_request:

                    relationship_status = "received"

                    pending_request_id = (
                        incoming_request["id"]
                    )

    # =====================================================
    # GET FRIENDS
    # =====================================================

    cursor.execute("""
        SELECT
            users.id,
            users.name,
            users.profile_picture

        FROM connections

        JOIN users
            ON users.id =
                CASE
                    WHEN connections.user1_id = ?
                    THEN connections.user2_id
                    ELSE connections.user1_id
                END

        WHERE
            connections.user1_id = ?
            OR
            connections.user2_id = ?

        ORDER BY connections.created_at DESC
    """, (
        profile_id,
        profile_id,
        profile_id
    ))

    friends = cursor.fetchall()

    # =====================================================
    # CLOSE DATABASE
    # =====================================================

    conn.close()

    # =====================================================
    # RENDER PROFILE
    # =====================================================

    return render_template(
        "profile.html",

        person=person,

        posts=posts,

        friends=friends,

        is_own_profile=is_own_profile,

        relationship_status=relationship_status,

        pending_request_id=pending_request_id
    )

# =========================================================
# PROFILE VIEWS
# =========================================================

@app.route("/profile-views")
def profile_views():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            profile_views.id,
            profile_views.viewer_id,
            profile_views.created_at,
            users.name,
            users.profile_picture

        FROM profile_views

        JOIN users
        ON users.id = profile_views.viewer_id

        WHERE profile_views.viewed_user_id = ?

        ORDER BY profile_views.created_at DESC
    """, (
        session["user_id"],
    ))

    views = cursor.fetchall()

    conn.close()

    return render_template(
        "profile_views.html",
        views=views
    )

# =========================================================
# EDIT PROFILE
# =========================================================

@app.route(
    "/edit-profile",
    methods=["GET", "POST"]
)
def edit_profile():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    conn = get_db()
    cursor = conn.cursor()

    user_id = session["user_id"]

    # =====================================================
    # SAVE CHANGES
    # =====================================================

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        bio = request.form.get(
            "bio",
            ""
        ).strip()

        if not name:

            conn.close()

            return (
                "Name is required.",
                400
            )

        cursor.execute("""
            UPDATE users
            SET
                name = ?,
                bio = ?
            WHERE id = ?
        """, (
            name,
            bio,
            user_id
        ))

        conn.commit()
        conn.close()

        session["user_name"] = name

        return redirect(
            url_for("profile")
        )

    # =====================================================
    # GET PROFILE DATA
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            name,
            bio
        FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    person = cursor.fetchone()

    conn.close()

    if person is None:
        return "User not found.", 404

    return render_template(
        "edit_profile.html",
        person=person
    )


# =========================================================
# UPLOAD / CROP PROFILE PICTURE
# =========================================================

@app.route(
    "/upload-profile-picture",
    methods=["POST"]
)
def upload_profile_picture():

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    # Get cropped image
    cropped_image = request.form.get(
        "cropped_image"
    )

    # Get original uploaded file
    file = request.files.get(
        "profile_picture"
    )

    filename = (
        f"profile_{session['user_id']}.jpg"
    )

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    # =====================================================
    # SAVE CROPPED IMAGE
    # =====================================================

    if cropped_image:

        try:

            import base64

            # Example:
            # data:image/jpeg;base64,/9j/4AAQ...
            encoded = cropped_image.split(
                ",",
                1
            )[1]

            image_data = base64.b64decode(
                encoded
            )

            with open(
                filepath,
                "wb"
            ) as f:

                f.write(image_data)

        except Exception as e:

            print(
                "Crop error:",
                e
            )

            return (
                "Could not save cropped image.",
                400
            )

    # =====================================================
    # SAVE ORIGINAL IMAGE IF NO CROPPED IMAGE
    # =====================================================

    elif file and file.filename:

        original_filename = secure_filename(
            file.filename
        )

        if not original_filename:

            return (
                "Invalid filename.",
                400
            )

        if not allowed_profile_picture(
            original_filename
        ):

            return (
                "Only JPG, JPEG, PNG, GIF and WEBP images are allowed.",
                400
            )

        file.save(
            filepath
        )

    else:

        return (
            "Please select a profile picture.",
            400
        )

    # =====================================================
    # UPDATE DATABASE
    # =====================================================

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET profile_picture = ?
        WHERE id = ?
    """, (
        filename,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for("profile")
    )

# =========================================================
# FIND PEOPLE
# =========================================================

@app.route("/find-people")
def find_people():

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    search = request.args.get("q", "").strip()

    conn = get_db()
    cursor = conn.cursor()

    if search:

        cursor.execute("""
            SELECT
                id,
                name,
                email,
                profile_picture
            FROM users
            WHERE
                (name LIKE ? OR email LIKE ?)
                AND id != ?
            ORDER BY name
        """, (
            f"%{search}%",
            f"%{search}%",
            current_user
        ))

    else:

        cursor.execute("""
            SELECT
                id,
                name,
                email,
                profile_picture
            FROM users
            WHERE id != ?
            ORDER BY name
        """, (
            current_user,
        ))

    people = cursor.fetchall()

    # Convert each person into a dictionary
    # and determine relationship status

    people_with_status = []

    for person in people:

        person = dict(person)

        person_id = person["id"]

        # -----------------------------------------
        # CHECK FRIENDSHIP
        # -----------------------------------------

        cursor.execute("""
            SELECT id
            FROM connections
            WHERE
                (user1_id = ? AND user2_id = ?)
                OR
                (user1_id = ? AND user2_id = ?)
        """, (
            current_user,
            person_id,
            person_id,
            current_user
        ))

        connection = cursor.fetchone()

        if connection:

            person["relationship_status"] = "friends"

        else:

            # -------------------------------------
            # CHECK SENT REQUEST
            # -------------------------------------

            cursor.execute("""
                SELECT id
                FROM connection_requests
                WHERE
                    sender_id = ?
                    AND receiver_id = ?
                    AND status = 'pending'
            """, (
                current_user,
                person_id
            ))

            sent_request = cursor.fetchone()

            if sent_request:

                person["relationship_status"] = "sent"

            else:

                # ---------------------------------
                # CHECK RECEIVED REQUEST
                # ---------------------------------

                cursor.execute("""
                    SELECT id
                    FROM connection_requests
                    WHERE
                        sender_id = ?
                        AND receiver_id = ?
                        AND status = 'pending'
                """, (
                    person_id,
                    current_user
                ))

                received_request = cursor.fetchone()

                if received_request:

                    person["relationship_status"] = "received"

                else:

                    person["relationship_status"] = "none"

        people_with_status.append(person)

    conn.close()

    return render_template(
        "find_people.html",
        people=people_with_status,
        search=search
    )


# =========================================================
# VIEW OTHER USER PROFILE
# =========================================================

@app.route("/profile/<int:user_id>")
def user_profile(user_id):

    # Check login
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # If opening own profile
    if user_id == current_user:
        return redirect(url_for("profile"))

    conn = get_db()
    cursor = conn.cursor()

    # =====================================================
    # GET USER
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            profile_picture,
            bio,
            last_seen,
            profile_visibility,
            posts_visibility,
            profile_views_enabled
        FROM users
        WHERE id = ?
    """, (user_id,))

    person = cursor.fetchone()

    if person is None:
        conn.close()
        return "Person not found.", 404

    # =====================================================
    # CHECK IF FRIENDS
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM connections
        WHERE
            (user1_id = ? AND user2_id = ?)
            OR
            (user1_id = ? AND user2_id = ?)
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    connection = cursor.fetchone()

    is_friend = connection is not None

    # =====================================================
    # PROFILE PRIVACY
    # =====================================================

    profile_visibility = person["profile_visibility"]

    if profile_visibility is None:
        profile_visibility = "everyone"

    # Friends only
    if profile_visibility == "friends" and not is_friend:

        conn.close()

        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Private Profile - PrivateConnect</title>

            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            >

            <style>

                body {
                    margin: 0;
                    font-family: Arial, sans-serif;
                    background: #f5f7fb;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    color: #111827;
                }

                .box {
                    background: white;
                    width: 90%;
                    max-width: 420px;
                    padding: 35px;
                    border-radius: 18px;
                    text-align: center;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                }

                .icon {
                    font-size: 55px;
                    margin-bottom: 15px;
                }

                h2 {
                    margin-bottom: 10px;
                }

                p {
                    color: #6b7280;
                    line-height: 1.5;
                }

                a {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 12px 20px;
                    background: #2563eb;
                    color: white;
                    text-decoration: none;
                    border-radius: 10px;
                }

            </style>
        </head>

        <body>

            <div class="box">

                <div class="icon">
                    🔒
                </div>

                <h2>
                    Private Profile
                </h2>

                <p>
                    This profile is visible to friends only.
                </p>

                <a href="/find-people">
                    Find People
                </a>

            </div>

        </body>
        </html>
        """, 403

    # Only me
    if profile_visibility == "only_me":

        conn.close()

        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Private Profile - PrivateConnect</title>

            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            >

            <style>

                body {
                    margin: 0;
                    font-family: Arial, sans-serif;
                    background: #f5f7fb;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    color: #111827;
                }

                .box {
                    background: white;
                    width: 90%;
                    max-width: 420px;
                    padding: 35px;
                    border-radius: 18px;
                    text-align: center;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                }

                .icon {
                    font-size: 55px;
                    margin-bottom: 15px;
                }

                h2 {
                    margin-bottom: 10px;
                }

                p {
                    color: #6b7280;
                    line-height: 1.5;
                }

                a {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 12px 20px;
                    background: #2563eb;
                    color: white;
                    text-decoration: none;
                    border-radius: 10px;
                }

            </style>
        </head>

        <body>

            <div class="box">

                <div class="icon">
                    🔐
                </div>

                <h2>
                    Private Profile
                </h2>

                <p>
                    This user has chosen to keep their profile private.
                </p>

                <a href="/find-people">
                    Find People
                </a>

            </div>

        </body>
        </html>
        """, 403

    # =====================================================
    # RECORD PROFILE VIEW
    # =====================================================

    profile_views_enabled = person["profile_views_enabled"]

    if profile_views_enabled:

        cursor.execute("""
            INSERT INTO profile_views (
                viewer_id,
                viewed_user_id
            )
            VALUES (?, ?)
        """, (
            current_user,
            user_id
        ))

        conn.commit()

    # =====================================================
    # GET USER POSTS
    # =====================================================

    posts = []

    posts_visibility = person["posts_visibility"]

    if posts_visibility is None:
        posts_visibility = "everyone"

    # Show posts if everyone OR current user is a friend
    if posts_visibility == "everyone" or is_friend:

        cursor.execute("""
            SELECT
                posts.id,
                posts.user_id,
                posts.caption,
                posts.media,
                posts.created_at,
                COUNT(likes.id) AS like_count

            FROM posts

            LEFT JOIN likes
            ON likes.post_id = posts.id

            WHERE posts.user_id = ?

            GROUP BY
                posts.id,
                posts.user_id,
                posts.caption,
                posts.media,
                posts.created_at

            ORDER BY posts.created_at DESC
        """, (user_id,))

        posts = cursor.fetchall()

    # =====================================================
    # DEFAULT CONNECTION STATUS
    # =====================================================

    relationship_status = "none"
    pending_request_id = None

    # =====================================================
    # CHECK CONNECTION STATUS
    # =====================================================

    if connection:

        relationship_status = "friends"

    else:

        # =================================================
        # CHECK SENT REQUEST
        # =================================================

        cursor.execute("""
            SELECT id
            FROM connection_requests

            WHERE
                sender_id = ?
                AND receiver_id = ?
                AND status = 'pending'
        """, (
            current_user,
            user_id
        ))

        outgoing_request = cursor.fetchone()

        if outgoing_request:

            relationship_status = "sent"

            pending_request_id = outgoing_request["id"]

        else:

            # =============================================
            # CHECK RECEIVED REQUEST
            # =============================================

            cursor.execute("""
                SELECT id
                FROM connection_requests

                WHERE
                    sender_id = ?
                    AND receiver_id = ?
                    AND status = 'pending'
            """, (
                user_id,
                current_user
            ))

            incoming_request = cursor.fetchone()

            if incoming_request:

                relationship_status = "received"

                pending_request_id = incoming_request["id"]

    # =====================================================
    # GET USER CONNECTIONS
    # =====================================================

    cursor.execute("""
        SELECT
            users.id,
            users.name,
            users.profile_picture

        FROM connections

        JOIN users
        ON users.id =
            CASE
                WHEN connections.user1_id = ?
                THEN connections.user2_id
                ELSE connections.user1_id
            END

        WHERE
            connections.user1_id = ?

            OR

            connections.user2_id = ?

        ORDER BY connections.created_at DESC
    """, (
        user_id,
        user_id,
        user_id
    ))

    friends = cursor.fetchall()

    # =====================================================
    # CLOSE DATABASE
    # =====================================================

    conn.close()

    # =====================================================
    # OPEN PROFILE PAGE
    # =====================================================

    return render_template(
        "profile.html",
        person=person,
        posts=posts,
        friends=friends,
        is_own_profile=False,
        relationship_status=relationship_status,
        pending_request_id=pending_request_id
    )


# =========================================================
# SEND CONNECTION REQUEST
# =========================================================

@app.route(
    "/send-request/<int:user_id>",
    methods=["POST"]
)
def send_request(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # Cannot connect with yourself
    if current_user == user_id:
        return (
            "You cannot connect with yourself.",
            400
        )

    conn = get_db()
    cursor = conn.cursor()

    # =====================================================
    # CHECK TARGET USER
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    target_user = cursor.fetchone()

    if not target_user:

        conn.close()

        return "User not found.", 404

    # =====================================================
    # CHECK BLOCK STATUS
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM blocked_users
        WHERE
            (
                blocker_id = ?
                AND blocked_id = ?
            )
            OR
            (
                blocker_id = ?
                AND blocked_id = ?
            )
        LIMIT 1
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    blocked_record = cursor.fetchone()

    if blocked_record:

        conn.close()

        return """
        <!DOCTYPE html>
        <html>
        <head>

            <title>Connection Blocked - PrivateConnect</title>

            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            >

            <style>

                body {
                    margin: 0;
                    font-family: Arial, sans-serif;
                    background: #f5f7fb;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    color: #111827;
                }

                .box {
                    background: white;
                    width: 90%;
                    max-width: 420px;
                    padding: 35px;
                    border-radius: 18px;
                    text-align: center;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                }

                .icon {
                    font-size: 55px;
                    margin-bottom: 15px;
                }

                h2 {
                    margin-bottom: 10px;
                }

                p {
                    color: #6b7280;
                    line-height: 1.5;
                }

                a {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 12px 20px;
                    background: #2563eb;
                    color: white;
                    text-decoration: none;
                    border-radius: 10px;
                }

            </style>

        </head>

        <body>

            <div class="box">

                <div class="icon">
                    🚫
                </div>

                <h2>
                    Connection Not Allowed
                </h2>

                <p>
                    You cannot send a connection request
                    to this user.
                </p>

                <a href="/find-people">
                    Find People
                </a>

            </div>

        </body>
        </html>
        """, 403

    # =====================================================
    # CHECK IF ALREADY FRIENDS
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM connections
        WHERE
            (user1_id = ? AND user2_id = ?)
            OR
            (user1_id = ? AND user2_id = ?)
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    existing_connection = cursor.fetchone()

    if existing_connection:

        conn.close()

        return redirect(
            url_for(
                "user_profile",
                user_id=user_id
            )
        )

    # =====================================================
    # CHECK EXISTING REQUEST
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            sender_id,
            receiver_id,
            status
        FROM connection_requests
        WHERE
            sender_id = ?
            AND receiver_id = ?
    """, (
        current_user,
        user_id
    ))

    existing_request = cursor.fetchone()

    # =====================================================
    # EXISTING REQUEST FOUND
    # =====================================================

    if existing_request:

        # Already pending
        if existing_request["status"] == "pending":

            conn.close()

            return redirect(
                url_for(
                    "find_people",
                    sent=user_id
                )
            )

        # Old accepted/rejected request
        # Change it back to pending
        cursor.execute("""
            UPDATE connection_requests
            SET status = 'pending'
            WHERE id = ?
        """, (
            existing_request["id"],
        ))

    else:

        # =================================================
        # CREATE NEW REQUEST
        # =================================================

        cursor.execute("""
            INSERT INTO connection_requests
            (
                sender_id,
                receiver_id,
                status
            )
            VALUES (?, ?, 'pending')
        """, (
            current_user,
            user_id
        ))

    # =====================================================
    # GET SENDER NAME
    # =====================================================

    cursor.execute("""
        SELECT name
        FROM users
        WHERE id = ?
    """, (
        current_user,
    ))

    sender = cursor.fetchone()

    # =====================================================
    # SEND NOTIFICATION
    # =====================================================

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

    return redirect(
        url_for(
            "find_people",
            sent=user_id
        )
    )


# =========================================================
# UNFRIEND USER
# =========================================================

@app.route(
    "/unfriend/<int:user_id>",
    methods=["POST"]
)
def unfriend(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # Cannot unfriend yourself
    if current_user == user_id:
        return redirect(
            url_for(
                "profile"
            )
        )

    conn = get_db()
    cursor = conn.cursor()

    # =====================================================
    # REMOVE CONNECTION
    # =====================================================

    cursor.execute("""
        DELETE FROM connections
        WHERE
            (user1_id = ? AND user2_id = ?)
            OR
            (user1_id = ? AND user2_id = ?)
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    conn.commit()
    conn.close()

    # =====================================================
    # RETURN TO USER PROFILE
    # =====================================================

    return redirect(
        url_for(
            "user_profile",
            user_id=user_id
        )
    )


# =========================================================
# UNSEND CONNECTION REQUEST
# =========================================================

@app.route(
    "/cancel-request/<int:user_id>",
    methods=["POST"]
)
def cancel_request(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM connection_requests
        WHERE sender_id = ?
        AND receiver_id = ?
        AND status = 'pending'
    """, (
        current_user,
        user_id
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for("find_people")
    )


# =========================================================
# CONNECTION REQUESTS
# =========================================================

@app.route("/requests")
def requests():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_db()

    cursor = conn.cursor()


    cursor.execute("""
        SELECT

            connection_requests.id,

            connection_requests.sender_id,

            connection_requests.created_at,

            users.name,

            users.email,

            users.profile_picture

        FROM connection_requests

        JOIN users
        ON users.id =
            connection_requests.sender_id

        WHERE

            connection_requests.receiver_id = ?

            AND

            connection_requests.status = 'pending'

        ORDER BY connection_requests.created_at DESC

    """, (
        session["user_id"],
    ))


    requests_data = cursor.fetchall()

    conn.close()


    return render_template(
        "requests.html",
        requests=requests_data
    )


# =========================================================
# ACCEPT CONNECTION REQUEST
# =========================================================

@app.route(
    "/accept-request/<int:request_id>",
    methods=["POST"]
)
def accept_request(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            sender_id,
            receiver_id,
            status
        FROM connection_requests
        WHERE id = ?
        AND receiver_id = ?
    """, (
        request_id,
        session["user_id"]
    ))

    connection_request = cursor.fetchone()

    if connection_request is None:
        conn.close()
        return "Request not found.", 404

    if connection_request["status"] != "pending":
        conn.close()
        return redirect(url_for("requests"))

    sender_id = connection_request["sender_id"]
    receiver_id = connection_request["receiver_id"]

    # Mark request as accepted
    cursor.execute("""
        UPDATE connection_requests
        SET status = 'accepted'
        WHERE id = ?
    """, (
        request_id,
    ))

    # Store the friendship/connection
    user1 = min(sender_id, receiver_id)
    user2 = max(sender_id, receiver_id)

    cursor.execute("""
        INSERT OR IGNORE INTO connections
        (
            user1_id,
            user2_id
        )
        VALUES (?, ?)
    """, (
        user1,
        user2
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("requests"))

# =========================================================
# REJECT CONNECTION REQUEST
# =========================================================

@app.route(
    "/reject-request/<int:request_id>",
    methods=["POST"]
)
def reject_request(request_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_db()

    cursor = conn.cursor()


    cursor.execute("""
        UPDATE connection_requests

        SET status = 'rejected'

        WHERE

            id = ?

            AND receiver_id = ?

            AND status = 'pending'

    """, (
        request_id,
        session["user_id"]
    ))


    conn.commit()

    conn.close()


    return redirect(
        url_for("requests")
    )


# =========================================================
# MY CONNECTIONS
# =========================================================

@app.route("/connections")
def connections():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    current_user = session["user_id"]

    conn = get_db()

    cursor = conn.cursor()


    cursor.execute("""
        SELECT

            users.id,

            users.name,

            users.email,

            users.profile_picture

        FROM connections

        JOIN users

        ON users.id =

            CASE

                WHEN connections.user1_id = ?

                THEN connections.user2_id

                ELSE connections.user1_id

            END

        WHERE

            connections.user1_id = ?

            OR

            connections.user2_id = ?

        ORDER BY users.name

    """, (
        current_user,
        current_user,
        current_user
    ))


    people = cursor.fetchall()

    conn.close()


    return render_template(
        "connections.html",
        people=people
    )


# =========================================================
# MESSAGES LIST
# =========================================================

@app.route("/messages")
def messages():

    if "user_id" not in session:
        return redirect(url_for("login"))

    current_user = session["user_id"]

    # Person selected from another user's profile
    selected_user = request.args.get("user_id", type=int)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            u.id,
            u.name,
            u.email,
            u.profile_picture,

            (
                SELECT m.message
                FROM messages m
                WHERE
                    (m.sender_id = ? AND m.receiver_id = u.id)
                    OR
                    (m.sender_id = u.id AND m.receiver_id = ?)
                ORDER BY m.id DESC
                LIMIT 1
            ) AS last_message,

            (
                SELECT m.created_at
                FROM messages m
                WHERE
                    (m.sender_id = ? AND m.receiver_id = u.id)
                    OR
                    (m.sender_id = u.id AND m.receiver_id = ?)
                ORDER BY m.id DESC
                LIMIT 1
            ) AS last_time

        FROM users u

        WHERE u.id IN (

            SELECT
                CASE
                    WHEN sender_id = ?
                    THEN receiver_id
                    ELSE sender_id
                END

            FROM messages

            WHERE
                sender_id = ?
                OR receiver_id = ?
        )

        ORDER BY last_time DESC

    """, (
        current_user,
        current_user,
        current_user,
        current_user,
        current_user,
        current_user,
        current_user
    ))

    people = cursor.fetchall()

    # Get selected person's information
    selected_person = None

    if selected_user:

        cursor.execute("""
            SELECT
                id,
                name,
                email,
                profile_picture
            FROM users
            WHERE id = ?
        """, (selected_user,))

        selected_person = cursor.fetchone()

    conn.close()

    return render_template(
        "messages.html",
        people=people,
        selected_person=selected_person
    )


## =========================================================
# CONVERSATION
# =========================================================

@app.route(
    "/messages/<int:user_id>",
    methods=["GET", "POST"]
)
def conversation(user_id):

    # -----------------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------------

    if "user_id" not in session:

        if request.method == "POST":
            return jsonify({
                "success": False,
                "error": "Not logged in"
            }), 401

        return redirect(url_for("login"))

    current_user = session["user_id"]

    # -----------------------------------------------------
    # CANNOT MESSAGE YOURSELF
    # -----------------------------------------------------

    if current_user == user_id:

        if request.method == "POST":
            return jsonify({
                "success": False,
                "error": "Invalid user"
            }), 400

        return redirect(url_for("messages"))

    conn = get_db()
    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # GET OTHER USER
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                name,
                email,
                profile_picture
            FROM users
            WHERE id = ?
        """, (user_id,))

        user = cursor.fetchone()

        if user is None:

            if request.method == "POST":
                return jsonify({
                    "success": False,
                    "error": "User not found"
                }), 404

            return "User not found.", 404


        # =================================================
        # POST = SEND MESSAGE
        # =================================================

        if request.method == "POST":

            message = request.form.get(
                "message",
                ""
            ).strip()

            image_file = request.files.get("image")

            image_filename = None


            # ---------------------------------------------
            # IMAGE UPLOAD
            # ---------------------------------------------

            if image_file and image_file.filename:

                original_name = secure_filename(
                    image_file.filename
                )

                extension = os.path.splitext(
                    original_name
                )[1].lower()

                allowed_images = {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".webp"
                }

                if extension not in allowed_images:

                    return jsonify({
                        "success": False,
                        "error": "Invalid image format"
                    }), 400


                unique_name = (
                    "chat_"
                    + secrets.token_hex(12)
                    + extension
                )

                upload_folder = app.config[
                    "UPLOAD_FOLDER"
                ]

                os.makedirs(
                    upload_folder,
                    exist_ok=True
                )

                image_path = os.path.join(
                    upload_folder,
                    unique_name
                )

                image_file.save(image_path)

                image_filename = unique_name


            # ---------------------------------------------
            # EMPTY MESSAGE CHECK
            # ---------------------------------------------

            if not message and not image_filename:

                return jsonify({
                    "success": False,
                    "error": "Message or image required"
                }), 400


            # ---------------------------------------------
            # MESSAGE LIMIT
            # ---------------------------------------------

            message = message[:1000]


            # ---------------------------------------------
            # CHECK RECEIVER STATUS
            # ---------------------------------------------

            cursor.execute("""
                SELECT last_seen
                FROM users
                WHERE id = ?
            """, (user_id,))

            receiver = cursor.fetchone()

            delivered_at = None

            if receiver and receiver["last_seen"]:

                try:

                    last_seen = datetime.strptime(
                        receiver["last_seen"],
                        "%Y-%m-%d %H:%M:%S"
                    )

                    seconds_ago = (
                        datetime.now() - last_seen
                    ).total_seconds()

                    if seconds_ago <= 15:

                        delivered_at = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                except Exception:

                    delivered_at = None


            # ---------------------------------------------
            # INSERT MESSAGE
            # ---------------------------------------------

            cursor.execute("""
                INSERT INTO messages
                (
                    sender_id,
                    receiver_id,
                    message,
                    image,
                    delivered_at,
                    read_at
                )
                VALUES (?, ?, ?, ?, ?, NULL)
            """, (
                current_user,
                user_id,
                message,
                image_filename,
                delivered_at
            ))


            # ---------------------------------------------
            # NOTIFICATION
            # ---------------------------------------------

            cursor.execute("""
                SELECT name
                FROM users
                WHERE id = ?
            """, (current_user,))

            sender = cursor.fetchone()

            if sender:

                if image_filename:

                    notification_text = (
                        f"{sender['name']} sent you a photo 📷"
                    )

                elif message:

                    notification_text = (
                        f"{sender['name']} sent you a message 💬"
                    )

                else:

                    notification_text = (
                        f"{sender['name']} sent you a message"
                    )

                try:

                    add_notification(
                        cursor,
                        user_id,
                        current_user,
                        "message",
                        notification_text
                    )

                except Exception as notification_error:

                    print(
                        "NOTIFICATION ERROR:",
                        str(notification_error)
                    )


            # ---------------------------------------------
            # SAVE
            # ---------------------------------------------

            conn.commit()


            # ---------------------------------------------
            # IMPORTANT:
            # RETURN JSON
            # ---------------------------------------------

            return jsonify({
                "success": True,
                "message": "Message sent"
            })


        # =================================================
        # GET = OPEN CHAT PAGE
        # =================================================

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        # ---------------------------------------------
        # MARK RECEIVED MESSAGES AS READ
        # ---------------------------------------------

        cursor.execute("""
            UPDATE messages

            SET
                read_at = ?,

                delivered_at = COALESCE(
                    delivered_at,
                    ?
                )

            WHERE

                sender_id = ?

                AND

                receiver_id = ?

                AND

                read_at IS NULL

        """, (
            now,
            now,
            user_id,
            current_user
        ))

        conn.commit()


        # ---------------------------------------------
        # GET CONVERSATION
        # ---------------------------------------------

        cursor.execute("""
            SELECT
                id,
                sender_id,
                receiver_id,
                message,
                image,
                created_at,
                delivered_at,
                read_at

            FROM messages

            WHERE

                (
                    sender_id = ?
                    AND receiver_id = ?
                )

                OR

                (
                    sender_id = ?
                    AND receiver_id = ?
                )

            ORDER BY id ASC

        """, (
            current_user,
            user_id,
            user_id,
            current_user
        ))

        messages = cursor.fetchall()


        # ---------------------------------------------
        # RENDER CHAT
        # ---------------------------------------------

        return render_template(
            "conversation.html",
            user=user,
            messages=messages
        )


    except Exception as e:

        conn.rollback()

        print(
            "CONVERSATION ERROR:",
            str(e)
        )

        if request.method == "POST":

            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

        return "Unable to open conversation.", 500


    finally:

        conn.close()

# =========================================================
# MESSAGE DATA FOR AUTOMATIC REFRESH
# =========================================================

@app.route("/messages/<int:user_id>/data")
def message_data(user_id):

    # -----------------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------------

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Not logged in"
        }), 401

    current_user = session["user_id"]

    # -----------------------------------------------------
    # CANNOT MESSAGE YOURSELF
    # -----------------------------------------------------

    if current_user == user_id:
        return jsonify({
            "success": False,
            "error": "Invalid user"
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # GET OTHER USER
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                name,
                profile_picture,
                last_seen
            FROM users
            WHERE id = ?
        """, (user_id,))

        other_user = cursor.fetchone()

        if other_user is None:

            return jsonify({
                "success": False,
                "error": "User not found"
            }), 404

        # -------------------------------------------------
        # UPDATE CURRENT USER ONLINE STATUS
        # -------------------------------------------------

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute("""
            UPDATE users
            SET last_seen = ?
            WHERE id = ?
        """, (
            now,
            current_user
        ))

        # -------------------------------------------------
        # MARK RECEIVED MESSAGES AS DELIVERED
        # -------------------------------------------------

        cursor.execute("""
            UPDATE messages
            SET delivered_at = ?
            WHERE
                sender_id = ?
                AND receiver_id = ?
                AND delivered_at IS NULL
        """, (
            now,
            user_id,
            current_user
        ))

        # -------------------------------------------------
        # MARK RECEIVED MESSAGES AS READ
        # -------------------------------------------------

        cursor.execute("""
            UPDATE messages
            SET
                delivered_at = COALESCE(
                    delivered_at,
                    ?
                ),
                read_at = ?
            WHERE
                sender_id = ?
                AND receiver_id = ?
                AND read_at IS NULL
        """, (
            now,
            now,
            user_id,
            current_user
        ))

        # -------------------------------------------------
        # GET ALL CHAT MESSAGES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                messages.id,
                messages.message,
                messages.image,
                messages.created_at,
                messages.delivered_at,
                messages.read_at,
                messages.sender_id,
                messages.receiver_id,
                users.name

            FROM messages

            JOIN users
            ON users.id = messages.sender_id

            WHERE

                (
                    messages.sender_id = ?
                    AND
                    messages.receiver_id = ?
                )

                OR

                (
                    messages.sender_id = ?
                    AND
                    messages.receiver_id = ?
                )

            ORDER BY messages.id ASC
        """, (
            current_user,
            user_id,
            user_id,
            current_user
        ))

        messages_data = cursor.fetchall()

        # -------------------------------------------------
        # SAVE DATABASE CHANGES
        # -------------------------------------------------

        conn.commit()

        # -------------------------------------------------
        # CHECK OTHER USER ONLINE
        # -------------------------------------------------

        online = False

        if other_user["last_seen"]:

            try:

                last_seen = datetime.strptime(
                    other_user["last_seen"],
                    "%Y-%m-%d %H:%M:%S"
                )

                seconds_ago = (
                    datetime.now() - last_seen
                ).total_seconds()

                online = seconds_ago <= 15

            except Exception:

                online = False

        # -------------------------------------------------
        # PREPARE MESSAGE LIST
        # -------------------------------------------------

        result_messages = []

        for message in messages_data:

            result_messages.append({

                "id":
                    message["id"],

                "message":
                    message["message"] or "",

                "image":
                    message["image"]
                    if message["image"]
                    else None,

                "created_at":
                    message["created_at"],

                "delivered_at":
                    message["delivered_at"],

                "read_at":
                    message["read_at"],

                "sender_id":
                    message["sender_id"],

                "receiver_id":
                    message["receiver_id"],

                "name":
                    message["name"]
                    if message["name"]
                    else ""
            })

        # -------------------------------------------------
        # RETURN CHAT DATA
        # -------------------------------------------------

        return jsonify({

            "success": True,

            "user": {

                "id":
                    other_user["id"],

                "name":
                    other_user["name"],

                "profile_picture":
                    other_user["profile_picture"],

                "last_seen":
                    other_user["last_seen"],

                "online":
                    online
            },

            "messages":
                result_messages
        })

    except Exception as e:

        conn.rollback()

        print(
            "MESSAGE DATA ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "error": "Unable to load messages"
        }), 500

    finally:

        conn.close()

# =========================================================
# MARK MESSAGES AS READ
# =========================================================

@app.route(
    "/messages/<int:user_id>/read",
    methods=["POST"]
)
def mark_messages_read(user_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Not logged in"
        }), 401

    current_user = session["user_id"]

    if current_user == user_id:
        return jsonify({
            "success": False,
            "error": "Invalid user"
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    try:

        # Check that the other user exists
        cursor.execute("""
            SELECT id
            FROM users
            WHERE id = ?
        """, (user_id,))

        user = cursor.fetchone()

        if user is None:
            return jsonify({
                "success": False,
                "error": "User not found"
            }), 404

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute("""
            UPDATE messages

            SET
                delivered_at = COALESCE(
                    delivered_at,
                    ?
                ),
                read_at = ?

            WHERE
                sender_id = ?
                AND receiver_id = ?
                AND read_at IS NULL

        """, (
            now,
            now,
            user_id,
            current_user
        ))

        conn.commit()

        return jsonify({
            "success": True
        })

    except Exception as e:

        conn.rollback()

        print(
            "MARK READ ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "error": "Unable to mark messages as read"
        }), 500

    finally:
        conn.close()


# =========================================================
# UNSEND MESSAGE
# =========================================================

@app.route(
    "/messages/unsend/<int:message_id>",
    methods=["POST"]
)
def unsend_message(message_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Not logged in"
        }), 401

    current_user = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                id,
                sender_id,
                receiver_id,
                image
            FROM messages
            WHERE id = ?
        """, (message_id,))

        message = cursor.fetchone()

        if message is None:
            return jsonify({
                "success": False,
                "error": "Message not found"
            }), 404

        # Only sender can unsend
        if message["sender_id"] != current_user:
            return jsonify({
                "success": False,
                "error": "You can only unsend your own message"
            }), 403

        # Delete image file if present
        if message["image"]:

            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                message["image"]
            )

            if os.path.exists(image_path):

                try:
                    os.remove(image_path)

                except Exception as image_error:

                    print(
                        "IMAGE DELETE ERROR:",
                        str(image_error)
                    )

        # Delete message
        cursor.execute("""
            DELETE FROM messages
            WHERE id = ?
            AND sender_id = ?
        """, (
            message_id,
            current_user
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "message_id": message_id
        })

    except Exception as e:

        conn.rollback()

        print(
            "UNSEND MESSAGE ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "error": "Unable to unsend message"
        }), 500

    finally:
        conn.close()


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

init_db()


# =========================================================
# PRIVACY POLICY
# =========================================================

@app.route(
    "/privacy-policy",
    methods=["GET"]
)
def privacy_policy():

    return render_template(
        "privacy_policy.html"
    )


# =========================================================
# TERMS OF SERVICE
# =========================================================

@app.route(
    "/terms-of-service",
    methods=["GET"]
)
def terms_of_service():

    return render_template(
        "terms_of_service.html"
    )


# =========================================================
# HELP & SUPPORT
# =========================================================

@app.route(
    "/help-support",
    methods=["GET"]
)
def help_support():

    return render_template(
        "help_support.html"
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )