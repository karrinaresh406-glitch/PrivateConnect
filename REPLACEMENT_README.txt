PRIVATE CONNECT — COMPLETE REPLACEMENT
========================================

This package is a cleaned replacement for the uploaded project.

Main fixes:
1. Only one application entry file: app.py
2. Removed the confusing app_backup.py.py from the replacement package.
3. Fixed photo/video upload handling with unique filenames.
4. Added WEBP image support.
5. Increased upload limit to 100 MB.
6. Added a friendly 413 response for files over the limit.
7. Added missing routes used by the existing templates:
   settings, password change, privacy, notifications, groups,
   highlights, blocking/unblocking, profile views, matching, etc.
8. Added complete feature-table initialization for fresh databases.
9. Added Flask-SocketIO + simple-websocket dependencies.
10. Updated the Render/Gunicorn command for threaded Socket.IO support.
11. Existing templates were kept and checked for Jinja syntax.
12. All template url_for endpoints are present in app.py.

IMPORTANT DATA NOTE
-------------------
The included users.db and static/uploads are a private data backup from the
uploaded project. Do NOT commit personal users.db or uploaded photos/videos
to a public GitHub repository.

RENDER NOTE
-----------
A normal Render filesystem is not a permanent database/file-storage solution.
SQLite data and uploaded files can disappear after redeploy/restart on an
ephemeral service. For real production use, move the database to a persistent
database (such as PostgreSQL) and media to persistent/object storage
(or use a paid persistent disk where appropriate).

LOCAL WINDOWS START
-------------------
1. Extract this folder.
2. Open Command Prompt/PowerShell in the folder.
3. Create/activate your virtual environment.
4. Install:
      pip install -r requirements.txt
5. Run:
      python app.py
6. Open:
      http://127.0.0.1:5000

GITHUB / RENDER
---------------
Upload the project files to the repository so that app.py is in the repository
root (not app.py.py). Do not upload the .git folder from the old ZIP.

The Procfile already contains:
      web: gunicorn --workers 1 --threads 100 --timeout 120 app:app

After pushing, trigger a Render deploy. Verify the build log installs all
requirements successfully before testing uploads.

UPLOAD TEST
-----------
Test all of these:
- JPG/PNG/WEBP photo in a normal post
- MP4 video in a normal post
- MP4/WEBM/MOV in Reels
- Profile JPG/PNG/WEBP
- Highlight JPG/PNG/WEBP

A successful upload should create a uniquely named file in static/uploads and
store that filename in SQLite.
