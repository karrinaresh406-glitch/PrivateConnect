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
    secrets.token_hex(32)
)

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
    # DATABASE MIGRATION
    # For old users.db files
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
        return jsonify({"success": False}), 401

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET last_seen = ?
        WHERE id = ?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        session["user_id"]
    ))

    # Mark incoming messages as DELIVERED
    cursor.execute("""
        UPDATE messages
        SET delivered_at = ?
        WHERE receiver_id = ?
        AND delivered_at IS NULL
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"success": True})


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
            < timedelta(seconds=10)
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

            return "All fields are required.", 400


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


    return render_template("signup.html")


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


        conn = get_db()

        cursor = conn.cursor()


        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (
            email,
        ))


        user = cursor.fetchone()


        if user is None:

            conn.close()

            return (
                "Invalid email or password!",
                401
            )


        stored_password = user["password"]

        password_valid = False


        # =================================================
        # CHECK HASHED PASSWORD
        # =================================================

        try:

            password_valid = check_password_hash(
                stored_password,
                password
            )

        except Exception:

            password_valid = False


        # =================================================
        # SUPPORT OLD PLAIN-TEXT PASSWORDS
        # =================================================

        if not password_valid:

            if stored_password == password:

                password_valid = True

                new_hash = generate_password_hash(
                    password
                )


                cursor.execute("""
                    UPDATE users

                    SET password = ?

                    WHERE id = ?

                """, (
                    new_hash,
                    user["id"]
                ))


                conn.commit()


        conn.close()


        if password_valid:

            session["user_id"] = user["id"]

            session["user_name"] = user["name"]

            session["user_email"] = user["email"]


            return redirect(
                url_for("dashboard")
            )


        return (
            "Invalid email or password!",
            401
        )


    return render_template("login.html")


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


    conn.commit()

    conn.close()


    share_url = (
        request.host_url.rstrip("/")
        + "/dashboard#post-"
        + str(post_id)
    )


    return jsonify({
        "success": True,
        "url": share_url
    })


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    current_user = session["user_id"]

    # =====================================================
    # GET PROFILE USER ID
    # =====================================================

    profile_id = request.args.get(
        "user_id",
        type=int
    )

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
            last_seen
        FROM users
        WHERE id = ?
    """, (profile_id,))

    person = cursor.fetchone()

    if person is None:
        conn.close()
        return "User not found.", 404

    # =====================================================
    # USER POSTS + LIKE COUNT
    # =====================================================

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
    # DEFAULT RELATIONSHIP STATUS
    # =====================================================

    relationship_status = "none"
    pending_request_id = None

    # =====================================================
    # OWN PROFILE
    # =====================================================

    if profile_id == current_user:

        relationship_status = "own"

    else:

        # =================================================
        # CHECK IF ALREADY FRIENDS
        # =================================================

        cursor.execute("""
            SELECT id
            FROM connections
            WHERE
                (user1_id = ? AND user2_id = ?)
                OR
                (user1_id = ? AND user2_id = ?)
        """, (
            current_user,
            profile_id,
            profile_id,
            current_user
        ))

        connection = cursor.fetchone()

        if connection:

            relationship_status = "friends"

        else:

            # =============================================
            # CHECK OUTGOING REQUEST
            # =============================================

            cursor.execute("""
                SELECT id
                FROM connection_requests
                WHERE
                    sender_id = ?
                    AND receiver_id = ?
                    AND status = 'pending'
            """, (
                current_user,
                profile_id
            ))

            outgoing_request = cursor.fetchone()

            if outgoing_request:

                relationship_status = "sent"
                pending_request_id = outgoing_request["id"]

            else:

                # =========================================
                # CHECK INCOMING REQUEST
                # =========================================

                cursor.execute("""
                    SELECT id
                    FROM connection_requests
                    WHERE
                        sender_id = ?
                        AND receiver_id = ?
                        AND status = 'pending'
                """, (
                    profile_id,
                    current_user
                ))

                incoming_request = cursor.fetchone()

                if incoming_request:

                    relationship_status = "received"
                    pending_request_id = incoming_request["id"]

    # =====================================================
    # MY CONNECTIONS / FRIENDS
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

    conn.close()

    # =====================================================
    # SEND DATA TO PROFILE PAGE
    # =====================================================

    return render_template(
        "profile.html",
        person=person,
        posts=posts,
        friends=friends,
        is_own_profile=(
            profile_id == current_user
        ),
        relationship_status=relationship_status,
        pending_request_id=pending_request_id
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
            last_seen
        FROM users
        WHERE id = ?
    """, (user_id,))

    person = cursor.fetchone()

    if person is None:
        conn.close()
        return "Person not found.", 404

    # =====================================================
    # GET USER POSTS
    # =====================================================

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

        return redirect(
            url_for("login")
        )


    current_user = session["user_id"]


    if current_user == user_id:

        return (
            "You cannot connect with yourself.",
            400
        )


    conn = get_db()

    cursor = conn.cursor()


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
        "find_people",
        sent=user_id
    )
)


    # CHECK ONLY PENDING REQUEST
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

    existing_request = cursor.fetchone()

    if existing_request:

        conn.close()

        return redirect(
            url_for(
                "find_people",
                sent=user_id
            )
        )


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


    conn.commit()

    conn.close()


    return redirect(
    url_for(
        "find_people",
        sent=user_id
    )
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


# =========================================================
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

        return redirect(
            url_for("login")
        )


    current_user = session["user_id"]


    # -----------------------------------------------------
    # DON'T MESSAGE YOURSELF
    # -----------------------------------------------------

    if current_user == user_id:

        return (
            "You cannot message yourself.",
            400
        )


    conn = get_db()

    cursor = conn.cursor()


    # -----------------------------------------------------
    # GET USER
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            profile_picture
        FROM users
        WHERE id = ?
    """, (
        user_id,
    ))


    user_row = cursor.fetchone()


    if user_row is None:

        conn.close()

        return (
            "User not found.",
            404
        )


    # Create user dictionary
    # This fixes: 'user' is undefined

    user = {

        "id": user_row["id"],

        "name": user_row["name"],

        "email": user_row["email"],

        "profile_picture":
            user_row["profile_picture"]

    }


    # -----------------------------------------------------
    # CHECK CONNECTION
    # -----------------------------------------------------

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
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))


    connection = cursor.fetchone()


    if connection is None:

        conn.close()

        return (
            "You are not connected with this user.",
            403
        )


    # -----------------------------------------------------
    # SEND MESSAGE
    # -----------------------------------------------------

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()


        if message:

            # Limit message length

            message = message[:1000]


            cursor.execute("""
    INSERT INTO messages
    (
        sender_id,
        receiver_id,
        message,
        delivered_at,
        read_at
    )
    VALUES (?, ?, ?, NULL, NULL)
""", (
    current_user,
    user_id,
    message
))


            conn.commit()


        conn.close()


        return redirect(
            url_for(
                "conversation",
                user_id=user_id
            )
        )


    # -----------------------------------------------------
    # MARK RECEIVED MESSAGES AS READ
    # -----------------------------------------------------

    cursor.execute("""
        UPDATE messages
        SET read_at = ?
        WHERE sender_id = ?
        AND receiver_id = ?
        AND read_at IS NULL
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_id,
        current_user
    ))

    conn.commit()


    # -----------------------------------------------------
    # GET MESSAGES
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            sender_id,
            receiver_id,
            message,
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

        ORDER BY created_at ASC
    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))

    messages = cursor.fetchall()

    conn.close()


    # -----------------------------------------------------
    # OPEN CHAT
    # -----------------------------------------------------

    return render_template(
        "conversation.html",
        user=user,
        messages=messages
    )

    


# =========================================================
# MESSAGE DATA FOR AUTOMATIC REFRESH
# =========================================================

@app.route(
    "/messages/<int:user_id>/data"
)
def message_data(user_id):

    if "user_id" not in session:

        return jsonify({
            "error": "Not logged in"
        }), 401


    current_user = session["user_id"]


    if current_user == user_id:

        return jsonify({
            "error": "Invalid user"
        }), 400


    conn = get_db()

    cursor = conn.cursor()


    # =====================================================
    # CHECK CONNECTION
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


    connected = cursor.fetchone()


    if not connected:

        conn.close()

        return jsonify({
            "error": "Not connected"
        }), 403


    # =====================================================
    # GET MESSAGES
    # =====================================================

    cursor.execute("""
        SELECT

    messages.id,

    messages.message,

    messages.created_at,

    messages.delivered_at,

    messages.read_at,

    users.name,

    messages.sender_id

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

        ORDER BY messages.created_at ASC

    """, (
        current_user,
        user_id,
        user_id,
        current_user
    ))


    messages_data = cursor.fetchall()

    conn.close()


    return jsonify([

    {
        "id": message["id"],

        "message": message["message"],

        "created_at": message["created_at"],

        "delivered_at": message["delivered_at"],

        "read_at": message["read_at"],

        "name": message["name"],

        "sender_id": message["sender_id"]

    }

    for message in messages_data

])

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
            "success": False
        }), 401

    current_user = session["user_id"]

    if current_user == user_id:
        return jsonify({
            "success": False
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

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
            AND receiver_id = ?
            AND read_at IS NULL
    """, (
        now,
        now,
        user_id,
        current_user
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


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
# START APPLICATION
# =========================================================

init_db()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )