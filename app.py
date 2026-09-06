from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
import secrets
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
            bio TEXT DEFAULT ''
        )
    """)

    # Add bio to older databases

    try:

        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN bio TEXT DEFAULT ''
        """)

    except sqlite3.OperationalError:

        pass


    # Add profile_picture to older databases

    try:

        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN profile_picture TEXT
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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

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
    # SHARES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shares (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            post_id INTEGER NOT NULL,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

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

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template("index.html")


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


    return render_template(
        "dashboard.html",
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
# LIKE / UNLIKE
# =========================================================

@app.route(
    "/like/<int:post_id>",
    methods=["POST"]
)
def like(post_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_db()

    cursor = conn.cursor()


    # Check post

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

        return "Post not found.", 404


    # Check existing like

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


    if existing_like:

        cursor.execute("""
            DELETE FROM likes

            WHERE user_id = ?

            AND post_id = ?

        """, (
            session["user_id"],
            post_id
        ))


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


    conn.commit()

    conn.close()


    return redirect(
        url_for("dashboard")
    )


# =========================================================
# ADD COMMENT
# =========================================================

@app.route(
    "/comment/<int:post_id>",
    methods=["POST"]
)
def comment(post_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    comment_text = request.form.get(
        "comment",
        ""
    ).strip()


    if not comment_text:

        return redirect(
            url_for("dashboard")
        )


    if len(comment_text) > 500:

        return (
            "Comment is too long.",
            400
        )


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


    if not post:

        conn.close()

        return "Post not found.", 404


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


    conn.commit()

    conn.close()


    return redirect(
        url_for("dashboard")
    )


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

    user_id = session["user_id"]

    # =====================================================
    # PROFILE
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            profile_picture
        FROM users
        WHERE id = ?
    """, (user_id,))

    person = cursor.fetchone()

    if person is None:
        conn.close()
        return "User not found.", 404

    # =====================================================
    # MY POSTS + LIKE COUNT
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
        user_id,
        user_id,
        user_id
    ))

    friends = cursor.fetchall()

    conn.close()

    return render_template(
        "profile.html",
        person=person,
        posts=posts,
        friends=friends
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

        return redirect(
            url_for("login")
        )


    search = request.args.get(
        "q",
        ""
    ).strip()


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

                name LIKE ?

                OR email LIKE ?

            ORDER BY name

        """, (
            f"%{search}%",
            f"%{search}%"
        ))


    else:

        cursor.execute("""
            SELECT

                id,

                name,

                email,

                profile_picture

            FROM users

            ORDER BY name

        """)


    people = cursor.fetchall()

    conn.close()


    return render_template(
        "find_people.html",
        people=people,
        search=search
    )


# =========================================================
# VIEW USER PROFILE
# =========================================================

@app.route(
    "/profile/<int:user_id>"
)
def user_profile(user_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_db()

    cursor = conn.cursor()


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


    person = cursor.fetchone()

    conn.close()


    if person is None:

        return "Person not found.", 404


    return render_template(
        "profile.html",
        person=person
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
            url_for("find_people")
        )


    cursor.execute("""
        SELECT id, status
        FROM connection_requests

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


    existing_request = cursor.fetchone()


    if existing_request:

        conn.close()

        return redirect(
            url_for("find_people")
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

    conn.close()

    return render_template(
        "messages.html",
        people=people
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
                    message
                )
                VALUES (?, ?, ?)
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
    # GET MESSAGES
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            sender_id,
            receiver_id,
            message,
            created_at
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


    # =====================================================
    # GET PERSON
    # =====================================================

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


    person = cursor.fetchone()


    if person is None:

        conn.close()

        return "Person not found.", 404


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

        return (
            "You can only message your connections.",
            403
        )


    # =====================================================
    # SEND MESSAGE
    # =====================================================

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()


        if message:

            if len(message) > 1000:

                conn.close()

                return (
                    "Message is too long.",
                    400
                )


            cursor.execute("""
                INSERT INTO messages
                (
                    sender_id,
                    receiver_id,
                    message
                )

                VALUES (?, ?, ?)

            """, (
                current_user,
                user_id,
                message
            ))


            conn.commit()


    # =====================================================
    # GET MESSAGES
    # =====================================================

    cursor.execute("""
        SELECT

            messages.message,

            messages.created_at,

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


    return render_template(
        "conversation.html",
        person=person,
        messages=messages_data
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

            messages.message,

            messages.created_at,

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
            "message": message["message"],

            "created_at": message["created_at"],

            "name": message["name"],

            "sender_id": message["sender_id"]

        }

        for message in messages_data

    ])


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