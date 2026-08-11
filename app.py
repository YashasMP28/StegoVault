from functools import wraps
import io
import os
import secrets
import sqlite3

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import IntegrityError as PGIntegrityError
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    PGIntegrityError = Exception
import base64
import re
def valid_username(username):
    """Validate username: 3-30 characters, letters/numbers/dot/underscore/hyphen."""
    if not username:
        return False

    return bool(
        re.fullmatch(r"[A-Za-z0-9._-]{3,30}", username)
    )
def valid_email(email):
    """Validate a basic RFC-style email address."""
    if not email:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",
            email,
        )
    )


def valid_mobile(mobile):
    """Validate mobile number: optional + followed by 10-15 digits."""
    if not mobile:
        return False

    return bool(re.fullmatch(r"\+?[0-9]{10,15}", mobile))


def password_errors(password):
    """Return human-readable password policy failures."""
    errors = []

    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("one lowercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("one special character")

    return errors


from datetime import datetime

import cv2
import numpy as np
from PIL import Image
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["ENVIRONMENT"] = os.environ.get("FLASK_ENV", "production" if os.environ.get("RENDER") else "development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Local development uses ./instance when DATABASE_URL is not configured.
# Render production uses managed PostgreSQL through DATABASE_URL.
data_dir = os.environ.get("STEGOVAULT_DATA_DIR") or app.instance_path
os.makedirs(data_dir, exist_ok=True)
app.config["DATA_DIR"] = data_dir
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL")
app.config["DATABASE"] = os.environ.get("DATABASE_PATH") or os.path.join(data_dir, "stegovault.db")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = app.config["ENVIRONMENT"] == "production"

# Keep the Flask session secret stable across restarts. An environment value
# still takes priority for production deployments.
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    secret_file = os.path.join(app.config["DATA_DIR"], ".session.key")
    if os.path.exists(secret_file):
        secret_key = open(secret_file, "r", encoding="utf-8").read().strip()
    else:
        secret_key = secrets.token_hex(32)
        with open(secret_file, "w", encoding="utf-8") as fh:
            fh.write(secret_key)
app.config["SECRET_KEY"] = secret_key

# Secret-message encryption key. Keep this server-side and out of the database.
fernet_key = os.environ.get("MESSAGE_ENCRYPTION_KEY")
if not fernet_key:
    key_file = os.path.join(app.config["DATA_DIR"], ".message.key")
    if os.path.exists(key_file):
        fernet_key = open(key_file, "r", encoding="utf-8").read().strip()
    else:
        fernet_key = Fernet.generate_key().decode()
        with open(key_file, "w", encoding="utf-8") as fh:
            fh.write(fernet_key)
message_cipher = Fernet(fernet_key.encode())

ALLOWED = {"png", "jpg", "jpeg", "webp"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
MOBILE_RE = re.compile(r"^\+?[0-9]{10,15}$")
# Stego v2 is retained for backwards compatibility with images created by Sprint 1-4.
# Stego v3 encrypts the hidden message with AES-256-GCM and binds it to its Group.
MAGIC_V2 = b"STEGv2\x00"
MAGIC_V3 = b"STEGv3\x00"
LEGACY_HEADER_SIZE = len(MAGIC_V2) + 4
SECURE_NONCE_SIZE = 12
SECURE_HEADER_SIZE = len(MAGIC_V3) + 4 + SECURE_NONCE_SIZE + 4
SECURE_AUTH_TAG_SIZE = 16
SECURE_OVERHEAD = SECURE_HEADER_SIZE + SECURE_AUTH_TAG_SIZE


class PostgresDB:
    def __init__(self, url):
        if psycopg2 is None:
            raise RuntimeError("psycopg2-binary is required when DATABASE_URL is configured.")
        self.conn = psycopg2.connect(url)

    @staticmethod
    def _convert(sql):
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(self._convert(sql), params)
        return cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def get_db():
    if "db" not in g:
        if app.config.get("DATABASE_URL"):
            g.db = PostgresDB(app.config["DATABASE_URL"])
        else:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def column_exists(db, table, column):
    if app.config.get("DATABASE_URL"):
        row = db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=? AND column_name=?",
            (table, column),
        ).fetchone()
        return row is not None
    return any(r[1] == column for r in db.execute(f"PRAGMA table_info({table})").fetchall())


def _init_postgres():
    db = PostgresDB(app.config["DATABASE_URL"])
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            first_name TEXT,
            username TEXT UNIQUE,
            mobile TEXT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USER',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS superuser_requests (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            group_name TEXT,
            description TEXT,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reviewed_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS groups (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            super_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            access_username TEXT NOT NULL UNIQUE,
            access_password_hash TEXT NOT NULL,
            encryption_key_encrypted BYTEA,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS group_members (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS group_join_requests (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMPTZ,
            UNIQUE(group_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS group_sessions (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS activities (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            operation TEXT NOT NULL,
            original_filename TEXT,
            output_filename TEXT,
            image_blob BYTEA,
            secret_message_encrypted BYTEA,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'SUCCESS'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL;
    """)
    # Wrap an AES key for every existing Group if this is an upgraded database.
    existing_groups = db.execute("SELECT id FROM groups WHERE encryption_key_encrypted IS NULL").fetchall()
    for row in existing_groups:
        group_key = AESGCM.generate_key(bit_length=256)
        wrapped_key = message_cipher.encrypt(group_key)
        db.execute("UPDATE groups SET encryption_key_encrypted=? WHERE id=?", (wrapped_key, row["id"]))
    db.commit()
    db.close()


def _init_sqlite():
    # Preserve the existing local-development database behavior.
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, first_name TEXT, username TEXT UNIQUE, mobile TEXT, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER', status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS superuser_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE, group_name TEXT, description TEXT, reason TEXT, status TEXT NOT NULL DEFAULT 'PENDING', reviewed_at TEXT, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT, super_user_id INTEGER NOT NULL, access_username TEXT NOT NULL UNIQUE, access_password_hash TEXT NOT NULL, encryption_key_encrypted BLOB, status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(super_user_id) REFERENCES users(id) ON DELETE RESTRICT);
        CREATE TABLE IF NOT EXISTS group_members (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL, user_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE', joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(group_id, user_id), FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS group_join_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL, user_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT, UNIQUE(group_id, user_id), FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS group_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, user_id INTEGER NOT NULL, operation TEXT NOT NULL, original_filename TEXT, output_filename TEXT, image_blob BLOB, secret_message_encrypted BLOB, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'SUCCESS', FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE SET NULL, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        """
    )
    for column, ddl in [("role", "TEXT NOT NULL DEFAULT 'USER'"), ("status", "TEXT NOT NULL DEFAULT 'ACTIVE'"), ("first_name", "TEXT"), ("username", "TEXT"), ("mobile", "TEXT")]:
        if not column_exists(db, "users", column): db.execute(f"ALTER TABLE users ADD COLUMN {column} {ddl}")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL")
    db.execute("UPDATE users SET first_name=COALESCE(first_name,name) WHERE first_name IS NULL")
    db.execute("UPDATE users SET username=COALESCE(username, 'user_' || id) WHERE username IS NULL")
    for table, column, ddl in [("superuser_requests","group_name","TEXT"),("superuser_requests","description","TEXT"),("groups","description","TEXT"),("groups","encryption_key_encrypted","BLOB")]:
        if not column_exists(db, table, column): db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    db.execute("UPDATE superuser_requests SET description=COALESCE(description,reason) WHERE description IS NULL")
    existing_groups = db.execute("SELECT id FROM groups WHERE encryption_key_encrypted IS NULL").fetchall()
    for row in existing_groups:
        group_key = AESGCM.generate_key(bit_length=256)
        wrapped_key = message_cipher.encrypt(group_key)
        db.execute("UPDATE groups SET encryption_key_encrypted=? WHERE id=?", (wrapped_key, row["id"] if app.config.get("DATABASE_URL") else row[0]))
    db.commit(); db.close()


def init_db():
    if app.config.get("DATABASE_URL"):
        _init_postgres()
    else:
        _init_sqlite()


init_db()


def admin_exists():
    return get_db().execute("SELECT 1 FROM users WHERE role=\'ADMIN\' AND status=\'ACTIVE\' LIMIT 1").fetchone() is not None


def current_user():
    if "user_id" not in session:
        return None
    return get_db().execute(
        "SELECT id,name,first_name,username,mobile,email,role,status,created_at FROM users WHERE id=?", (session["user_id"],)
    ).fetchone()


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def require_csrf():
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in to use StegoVault."), 401
            return redirect(url_for("login"))
        if current_user()["status"] != "ACTIVE":
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(error="Your account is not active."), 403
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user()["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="You do not have permission for this action."), 403
                flash("You do not have permission for this page.", "error")
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_user():
    return {"user": current_user(), "csrf_token": csrf_token()}


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def image_from_bytes(data):
    arr = np.frombuffer(data, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded file is not a valid image.")
    return image


def png_bytes(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Could not create PNG output.")
    return encoded.tobytes()


def capacity_bytes(image):
    # This is the maximum plaintext message size for the secure v3 payload.
    total_bits = image.shape[0] * image.shape[1] * 3 * 2
    return max(0, total_bits // 8 - SECURE_OVERHEAD)


def get_group_encryption_key(group):
    wrapped = group["encryption_key_encrypted"]
    if not wrapped:
        raise ValueError("This Group does not have a secure encryption key. Contact the Group administrator.")
    try:
        return message_cipher.decrypt(bytes(wrapped))
    except InvalidToken:
        raise ValueError("The Group encryption key is unavailable or invalid.")


def group_aad(group_id):
    return f"StegoVault|group:{int(group_id)}|stegov3".encode("utf-8")


def hide_data(image, message, group):
    plaintext = message.encode("utf-8")
    key = get_group_encryption_key(group)
    nonce = secrets.token_bytes(SECURE_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, group_aad(group["id"]))
    packet = (
        MAGIC_V3
        + int(group["id"]).to_bytes(4, "big")
        + nonce
        + len(ciphertext).to_bytes(4, "big")
        + ciphertext
    )
    if len(plaintext) > capacity_bytes(image):
        raise ValueError(
            f"Message is too large. This image can store about {capacity_bytes(image):,} bytes, "
            f"but the message needs {len(plaintext):,} bytes."
        )
    bits = []
    for byte in packet:
        bits.extend([(byte >> 6) & 3, (byte >> 4) & 3, (byte >> 2) & 3, byte & 3])
    flat = image.reshape(-1)
    if len(bits) > flat.size:
        raise ValueError("The encrypted message is too large for this image.")
    for i, value in enumerate(bits):
        flat[i] = (int(flat[i]) & 0xFC) | value
    return flat.reshape(image.shape)


def extract_bytes(flat, byte_count, start_byte=0):
    values = (flat[start_byte * 4:(start_byte + byte_count) * 4] & 3).astype(np.uint8)
    payload = bytearray()
    for i in range(0, len(values), 4):
        payload.append((int(values[i]) << 6) | (int(values[i + 1]) << 4) | (int(values[i + 2]) << 2) | int(values[i + 3]))
    return bytes(payload)


def unhide_data(image, group):
    flat = image.reshape(-1)
    if flat.size < LEGACY_HEADER_SIZE * 4:
        raise ValueError("Image is too small to contain a steganography payload.")

    # Read enough bytes to distinguish v2 and v3.
    prefix = extract_bytes(flat, len(MAGIC_V3), 0)
    if prefix == MAGIC_V3:
        if flat.size < SECURE_HEADER_SIZE * 4:
            raise ValueError("The secure hidden payload is incomplete.")
        header = extract_bytes(flat, SECURE_HEADER_SIZE, 0)
        group_id = int.from_bytes(header[len(MAGIC_V3):len(MAGIC_V3) + 4], "big")
        if int(group["id"]) != group_id:
            raise ValueError("This image belongs to a different Group.")
        nonce_start = len(MAGIC_V3) + 4
        nonce = header[nonce_start:nonce_start + SECURE_NONCE_SIZE]
        length_start = nonce_start + SECURE_NONCE_SIZE
        ciphertext_length = int.from_bytes(header[length_start:length_start + 4], "big")
        if ciphertext_length < SECURE_AUTH_TAG_SIZE:
            raise ValueError("The secure hidden payload is invalid.")
        total_bytes = SECURE_HEADER_SIZE + ciphertext_length
        if total_bytes * 4 > flat.size:
            raise ValueError("The secure hidden message appears to be corrupted.")
        ciphertext = extract_bytes(flat, ciphertext_length, SECURE_HEADER_SIZE)
        try:
            plaintext = AESGCM(get_group_encryption_key(group)).decrypt(
                nonce, ciphertext, group_aad(group_id)
            )
        except Exception:
            raise ValueError("The hidden message failed authentication. The image may be corrupted or tampered with.")
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("The decrypted message is not valid UTF-8 data.")

    # Backwards-compatible v2 decoder. Old images were not encrypted; newly
    # generated images always use v3 AES-256-GCM.
    header = extract_bytes(flat, LEGACY_HEADER_SIZE, 0)
    if bytes(header[:len(MAGIC_V2)]) != MAGIC_V2:
        raise ValueError("No compatible hidden message was found in this image.")
    length_start = len(MAGIC_V2)
    length = int.from_bytes(header[length_start:length_start + 4], "big")
    if (LEGACY_HEADER_SIZE + length) * 4 > flat.size:
        raise ValueError("The hidden message appears to be corrupted.")
    payload = extract_bytes(flat, length, LEGACY_HEADER_SIZE)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("The hidden message is not valid UTF-8 data.")


def encrypt_message(message):
    return message_cipher.encrypt(message.encode("utf-8"))


def decrypt_message(blob):
    if not blob:
        return ""
    try:
        return message_cipher.decrypt(blob).decode("utf-8")
    except InvalidToken:
        raise ValueError("The secret message cannot be decrypted with the current server key.")


def user_group_ids(user_id):
    rows = get_db().execute("SELECT group_id FROM group_members WHERE user_id=? AND status='ACTIVE'", (user_id,)).fetchall()
    return [r["group_id"] for r in rows]


def require_group_access(group_id, allow_super=True):
    user = current_user()
    if user["role"] == "ADMIN":
        # Admin can inspect metadata but cannot use secret-message routes.
        group = get_db().execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
        return group
    if user["role"] == "SUPER_USER" and allow_super:
        group = get_db().execute("SELECT * FROM groups WHERE id=? AND super_user_id=?", (group_id, user["id"])).fetchone()
        if not group:
            raise PermissionError("You can access only your own group.")
        return group
    group = get_db().execute(
        "SELECT g.* FROM groups g JOIN group_members gm ON gm.group_id=g.id WHERE g.id=? AND gm.user_id=? AND gm.status='ACTIVE'",
        (group_id, user["id"]),
    ).fetchone()
    if not group:
        raise PermissionError("You are not a member of this group.")
    return group


@app.get("/healthz")
def healthz():
    try:
        get_db().execute("SELECT 1").fetchone()
        return jsonify(status="ok"), 200
    except Exception:
        return jsonify(status="error"), 503


@app.get("/")
@login_required
def index():
    user = current_user()
    if user["role"] == "ADMIN":
        return redirect(url_for("admin_dashboard"))
    if user["role"] == "SUPER_USER":
        return redirect(url_for("superuser_dashboard"))
    return redirect(url_for("workspace"))


@app.get("/workspace")
@login_required
def workspace():
    user = current_user()
    db = get_db()

    if user["role"] == "SUPER_USER":
        # A Super User does not request access to their own Group.
        # They can open the workspace only after entering that Group's credentials,
        # exactly like a normal approved Group member.
        groups = db.execute(
            "SELECT g.id,g.name,g.access_username,g.status FROM groups g "
            "WHERE g.super_user_id=? AND g.status='ACTIVE' ORDER BY g.name",
            (user["id"],),
        ).fetchall()
        join_requests = []
    else:
        groups = db.execute(
            "SELECT g.id,g.name,g.access_username,g.status FROM groups g "
            "JOIN group_members gm ON gm.group_id=g.id "
            "WHERE gm.user_id=? AND gm.status='ACTIVE' AND g.status='ACTIVE' "
            "ORDER BY g.name",
            (user["id"],),
        ).fetchall()
        join_requests = db.execute(
            "SELECT r.id,r.status,r.created_at,g.name AS group_name,g.access_username "
            "FROM group_join_requests r JOIN groups g ON g.id=r.group_id "
            "WHERE r.user_id=? ORDER BY r.id DESC",
            (user["id"],),
        ).fetchall()

    requested_group_id = request.args.get("group_id", type=int)
    session_group_id = session.get("group_id")
    selected_group_id = requested_group_id or session_group_id

    group_ids = {row["id"] for row in groups}
    if selected_group_id not in group_ids:
        selected_group_id = None

    active_unlocked = bool(
        selected_group_id
        and session.get("group_unlocked_id") == selected_group_id
        and session.get("group_id") == selected_group_id
    )
    active_group_name = next(
        (row["name"] for row in groups if row["id"] == selected_group_id),
        None,
    )

    return render_template(
        "index.html",
        groups=groups,
        available_groups=groups,
        join_requests=join_requests,
        active_group_id=selected_group_id,
        active_group_unlocked=active_unlocked,
        active_group_name=active_group_name,
    )


@app.get("/admin")
@role_required("ADMIN")
def admin_dashboard():
    db = get_db()
    users = db.execute("SELECT id,name,first_name,username,mobile,email,role,status,created_at FROM users ORDER BY created_at DESC").fetchall()
    requests = db.execute("SELECT r.*,u.name,u.first_name,u.username,u.mobile,u.email FROM superuser_requests r JOIN users u ON u.id=r.user_id WHERE r.status='PENDING' ORDER BY r.id DESC").fetchall()
    groups = db.execute("SELECT g.*,u.name AS super_name,u.username AS super_username FROM groups g JOIN users u ON u.id=g.super_user_id ORDER BY g.created_at DESC").fetchall()
    group_members = db.execute("""
        SELECT g.id AS group_id,g.name AS group_name,u.id AS user_id,u.first_name,u.username,u.email,gm.status AS member_status
        FROM groups g
        JOIN group_members gm ON gm.group_id=g.id
        JOIN users u ON u.id=gm.user_id
        ORDER BY g.name,u.first_name,u.username
    """).fetchall()
    activity = db.execute("SELECT a.id,a.group_id,a.user_id,a.operation,a.original_filename,a.output_filename,a.created_at,a.status,g.name AS group_name,u.name AS user_name FROM activities a LEFT JOIN groups g ON g.id=a.group_id JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC LIMIT 100").fetchall()
    return render_template("admin.html", users=users, requests=requests, groups=groups, group_members=group_members, activity=activity)

@app.get("/superuser")
@role_required("SUPER_USER")
def superuser_dashboard():
    db = get_db()
    groups = db.execute("SELECT * FROM groups WHERE super_user_id=? AND status='ACTIVE' ORDER BY created_at DESC", (current_user()["id"],)).fetchall()
    latest_request = db.execute("SELECT group_name,description,status FROM superuser_requests WHERE user_id=? ORDER BY id DESC LIMIT 1", (current_user()["id"],)).fetchone()
    pending = db.execute("""
        SELECT r.id,r.status,r.created_at,u.first_name,u.username,u.email,u.mobile,g.id AS group_id,g.name AS group_name
        FROM group_join_requests r
        JOIN users u ON u.id=r.user_id
        JOIN groups g ON g.id=r.group_id
        WHERE g.super_user_id=? AND r.status='PENDING' AND g.status='ACTIVE'
        ORDER BY r.id DESC
    """, (current_user()["id"],)).fetchall()
    members = db.execute("""
        SELECT gm.id,gm.status,u.id AS user_id,u.first_name,u.username,u.email,u.mobile,g.id AS group_id,g.name AS group_name
        FROM group_members gm JOIN users u ON u.id=gm.user_id JOIN groups g ON g.id=gm.group_id
        WHERE g.super_user_id=? AND g.status='ACTIVE' ORDER BY g.name,u.first_name,u.username
    """, (current_user()["id"],)).fetchall()
    return render_template("superuser.html", groups=groups, latest_request=latest_request, pending=pending, members=members)

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    # First-run only: once an active Admin exists, this page is permanently closed.
    if admin_exists():
        return redirect(url_for("login"))
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        username = request.form.get("username", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = []
        if not require_csrf(): errors.append("Session expired. Please try again.")
        if not first_name or len(first_name) < 2: errors.append("Enter a valid first name.")
        if not valid_username(username): errors.append("Username must be 3-30 characters and contain only letters, numbers, dot, underscore or hyphen.")
        if not valid_mobile(mobile): errors.append("Enter a valid mobile number with 10-15 digits.")
        if not valid_email(email): errors.append("Enter a valid email address.")
        pw_errors = password_errors(password)
        if pw_errors: errors.append("Password requires " + ", ".join(pw_errors) + ".")
        if password != confirm: errors.append("Passwords do not match.")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone(): errors.append("That email is already registered.")
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone(): errors.append("That username is already registered.")
        if errors:
            for e in errors: flash(e, "error")
            return render_template("admin_setup.html")
        db.execute("INSERT INTO users(name,first_name,username,mobile,email,password_hash,role,status) VALUES(?,?,?,?,?,?,?,?)",
                   (first_name, first_name, username, mobile, email, generate_password_hash(password), "ADMIN", "ACTIVE"))
        db.commit()
        flash("Admin account created successfully. Please sign in.", "success")
        return redirect(url_for("login"))
    return render_template("admin_setup.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("index"))
    if not admin_exists():
        return redirect(url_for("admin_setup"))
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        username = request.form.get("username", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        account_type = request.form.get("account_type", "USER").upper()
        group_name = request.form.get("group_name", "").strip()
        description = request.form.get("description", "").strip()
        errors = []
        if not require_csrf():
            errors.append("Session expired. Please try again.")
        if not first_name or len(first_name) < 2:
            errors.append("Enter a valid first name.")
        if not valid_username(username):
            errors.append("Username must be 3-30 characters and contain only letters, numbers, dot, underscore or hyphen.")
        if not valid_mobile(mobile):
            errors.append("Enter a valid mobile number with 10-15 digits.")
        if not valid_email(email):
            errors.append("Enter a valid email address, for example name@example.com.")
        pw_errors = password_errors(password)
        if pw_errors:
            errors.append("Password requires " + ", ".join(pw_errors) + ".")
        if password != confirm:
            errors.append("Passwords do not match.")
        if account_type not in {"USER", "SUPER_USER"}:
            errors.append("Select a valid account type.")
        if account_type == "SUPER_USER":
            if len(group_name) < 2:
                errors.append("Group/company name is required for a Super User request.")
            if len(description) < 20:
                errors.append("Super User purpose/description must be at least 20 characters so Admin can review the request.")
        if errors:
            for error in errors: flash(error, "error")
        else:
            try:
                db = get_db()
                user_values = (
                    first_name,
                    first_name,
                    username,
                    mobile,
                    email,
                    generate_password_hash(password),
                    "USER",
                    "ACTIVE",
                )

                # SQLite must not leave a RETURNING statement open when COMMIT
                # is called. PostgreSQL can safely use RETURNING here.
                if app.config.get("DATABASE_URL"):
                    cur = db.execute(
                        "INSERT INTO users(name,first_name,username,mobile,email,password_hash,role,status) "
                        "VALUES(?,?,?,?,?,?,?,?) RETURNING id",
                        user_values,
                    )
                    user_id = cur.fetchone()["id"]
                else:
                    cur = db.execute(
                        "INSERT INTO users(name,first_name,username,mobile,email,password_hash,role,status) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        user_values,
                    )
                    user_id = cur.lastrowid

                if account_type == "SUPER_USER":
                    db.execute(
                        "INSERT INTO superuser_requests(user_id,group_name,description,reason,status,reviewed_at) VALUES(?,?,?,?,?,NULL)",
                        (user_id, group_name, description, description, "PENDING")
                    )
                db.commit()
                session.clear(); session["user_id"] = user_id; csrf_token()
                if account_type == "SUPER_USER":
                    flash("Registration complete. Your Super User request is pending Admin approval.", "success")
                return redirect(url_for("workspace"))
            except (sqlite3.IntegrityError, PGIntegrityError) as exc:
                if "username" in str(exc).lower():
                    flash("That username is already registered.", "error")
                else:
                    flash("An account with that email already exists.", "error")
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if not admin_exists():
        return redirect(url_for("admin_setup"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower(); password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not require_csrf():
            flash("Session expired. Please try again.", "error")
        elif not valid_email(email):
            flash("Enter a valid email address.", "error")
        elif not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
        elif user["status"] != "ACTIVE":
            flash("Your account is not active. Contact the administrator.", "error")
        else:
            session.clear(); session["user_id"] = user["id"]; csrf_token()
            return redirect(url_for("index"))
    return render_template("auth.html", mode="login")


@app.post("/logout")
@login_required
def logout():
    if not require_csrf():
        return "Invalid CSRF token", 400
    session.clear(); return redirect(url_for("login"))


@app.post("/api/superuser/request")
@login_required
def request_superuser():
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    if current_user()["role"] != "USER": return jsonify(error="Only normal users can request Super User approval."), 400
    group_name = request.form.get("group_name", "").strip()
    description = request.form.get("description", "").strip()
    if len(group_name) < 2: return jsonify(error="Group/company name is required."), 400
    if len(description) < 20: return jsonify(error="Please provide at least 20 characters explaining the business purpose to Admin."), 400
    db = get_db()
    existing = db.execute("SELECT status FROM superuser_requests WHERE user_id=?", (current_user()["id"],)).fetchone()
    if existing and existing["status"] == "PENDING": return jsonify(error="Your request is already pending."), 400
    db.execute("INSERT INTO superuser_requests(user_id,group_name,description,reason,status,reviewed_at) VALUES(?,?,?,?,?,NULL) ON CONFLICT(user_id) DO UPDATE SET group_name=EXCLUDED.group_name, description=EXCLUDED.description, reason=EXCLUDED.reason, status=EXCLUDED.status, reviewed_at=NULL", (current_user()["id"],group_name,description,description,"PENDING"))
    db.commit(); return jsonify(ok=True, message="Super User request submitted to Admin.")


@app.post("/api/admin/superuser/<int:req_id>/<action>")
@role_required("ADMIN")
def review_superuser(req_id, action):
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    if action not in {"approve", "reject"}: return jsonify(error="Invalid action."), 400
    db = get_db(); row = db.execute("SELECT * FROM superuser_requests WHERE id=? AND status='PENDING'", (req_id,)).fetchone()
    if not row: return jsonify(error="Pending Super User request not found."), 404
    status = "APPROVED" if action == "approve" else "REJECTED"
    db.execute("UPDATE superuser_requests SET status=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (status,req_id))
    if action == "approve":
        db.execute("UPDATE users SET role='SUPER_USER', status='ACTIVE' WHERE id=?", (row["user_id"],))
    db.commit(); return jsonify(ok=True, message=f"Super User request {status.lower()}.")


@app.post("/api/admin/user/<int:user_id>/status")
@role_required("ADMIN")
def admin_user_status(user_id):
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    status = request.form.get("status", "").upper()
    if status not in {"ACTIVE", "DISABLED"}: return jsonify(error="Invalid status. Use ACTIVE or DISABLED."), 400
    if user_id == current_user()["id"]: return jsonify(error="Admin cannot disable the current account."), 400
    db=get_db(); target=db.execute("SELECT id,role FROM users WHERE id=?", (user_id,)).fetchone()
    if not target: return jsonify(error="User not found."),404
    db.execute("UPDATE users SET status=? WHERE id=?", (status,user_id))
    if target["role"] == "SUPER_USER" and status == "DISABLED":
        db.execute("UPDATE groups SET status='DISABLED' WHERE super_user_id=?", (user_id,))
    db.commit(); return jsonify(ok=True, message=f"Account {status.lower()}.")


@app.post("/api/admin/group/<int:group_id>/remove")
@role_required("ADMIN")
def admin_remove_group(group_id):
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    db=get_db(); row=db.execute("SELECT id FROM groups WHERE id=?",(group_id,)).fetchone()
    if not row:return jsonify(error="Group not found."),404
    db.execute("UPDATE groups SET status='DISABLED' WHERE id=?",(group_id,)); db.execute("UPDATE group_members SET status='DISABLED' WHERE group_id=?",(group_id,)); db.commit()
    return jsonify(ok=True,message="Group removed from active Groups.")


@app.post("/api/admin/superuser/<int:user_id>/remove")
@role_required("ADMIN")
def admin_remove_superuser(user_id):
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    db=get_db(); row=db.execute("SELECT id,role FROM users WHERE id=?",(user_id,)).fetchone()
    if not row or row["role"] != "SUPER_USER": return jsonify(error="Super User not found."),404
    db.execute("UPDATE users SET status='DISABLED',role='SUPER_USER' WHERE id=?",(user_id,)); db.execute("UPDATE groups SET status='DISABLED' WHERE super_user_id=?",(user_id,)); db.commit()
    return jsonify(ok=True,message="Super User removed and owned Groups disabled.")


@app.post("/api/superuser/group")
@role_required("SUPER_USER")
def create_group():
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    name = request.form.get("name", "").strip(); description = request.form.get("description", "").strip(); access_username = request.form.get("access_username", "").strip(); access_password = request.form.get("access_password", "")
    pw_errors = password_errors(access_password)
    if len(name) < 2: return jsonify(error="Group name is required."), 400
    if not valid_username(access_username): return jsonify(error="Group username must be 3-30 characters and contain only letters, numbers, dot, underscore or hyphen."), 400
    if pw_errors: return jsonify(error="Group password requires " + ", ".join(pw_errors) + "."), 400
    try:
        db=get_db(); group_key = AESGCM.generate_key(bit_length=256)
        wrapped_group_key = message_cipher.encrypt(group_key)
        group_values = (
            name,
            description,
            current_user()["id"],
            access_username,
            generate_password_hash(access_password),
            wrapped_group_key,
        )

        # Use lastrowid for SQLite so no RETURNING cursor remains active at COMMIT.
        if app.config.get("DATABASE_URL"):
            cur = db.execute(
                "INSERT INTO groups(name,description,super_user_id,access_username,"
                "access_password_hash,encryption_key_encrypted) VALUES(?,?,?,?,?,?) RETURNING id",
                group_values,
            )
            group_id = cur.fetchone()["id"]
        else:
            cur = db.execute(
                "INSERT INTO groups(name,description,super_user_id,access_username,"
                "access_password_hash,encryption_key_encrypted) VALUES(?,?,?,?,?,?)",
                group_values,
            )
            group_id = cur.lastrowid

        db.commit(); return jsonify(ok=True, group_id=group_id)
    except (sqlite3.IntegrityError, PGIntegrityError):
        if app.config.get("DATABASE_URL"):
            db.rollback()
        return jsonify(error="Group name or access username is already in use."), 400


@app.post("/api/group/request-access")
@role_required("USER")
def request_group_access():
    if not require_csrf(): return jsonify(error="Invalid security token."),400
    group_username=request.form.get("group_username","").strip()
    if not group_username:return jsonify(error="Enter the Group username provided by the Super User."),400
    db=get_db(); group=db.execute("SELECT id,name,status FROM groups WHERE access_username=?",(group_username,)).fetchone()
    if not group or group["status"] != "ACTIVE":return jsonify(error="No active Group was found for that Group username."),404
    existing_member=db.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status='ACTIVE'",(group["id"],current_user()["id"])).fetchone()
    if existing_member:return jsonify(error="You are already a member of this Group."),400
    existing=db.execute("SELECT status FROM group_join_requests WHERE group_id=? AND user_id=?",(group["id"],current_user()["id"])).fetchone()
    if existing and existing["status"]=="PENDING":return jsonify(error="Your Group access request is already pending."),400
    db.execute("INSERT INTO group_join_requests(group_id,user_id,status,reviewed_at) VALUES(?,?, 'PENDING', NULL) ON CONFLICT(group_id,user_id) DO UPDATE SET status='PENDING',reviewed_at=NULL,created_at=CURRENT_TIMESTAMP",(group["id"],current_user()["id"])); db.commit()
    return jsonify(ok=True,message=f"Access request sent to {group['name']} Super User.")


@app.post("/api/superuser/group/<int:group_id>/request/<int:req_id>/<action>")
@role_required("SUPER_USER")
def review_group_request(group_id, req_id, action):
    if not require_csrf():return jsonify(error="Invalid security token."),400
    if action not in {"approve","reject"}:return jsonify(error="Invalid action."),400
    db=get_db(); row=db.execute("""SELECT r.*,g.name AS group_name FROM group_join_requests r JOIN groups g ON g.id=r.group_id WHERE r.id=? AND r.group_id=? AND g.super_user_id=? AND r.status='PENDING'""",(req_id,group_id,current_user()["id"])).fetchone()
    if not row:return jsonify(error="Pending Group access request not found."),404
    status='APPROVED' if action=='approve' else 'REJECTED'
    if action=='approve':
        db.execute("INSERT INTO group_members(group_id,user_id,status) VALUES(?,?, 'ACTIVE') ON CONFLICT(group_id,user_id) DO NOTHING",(group_id,row["user_id"]))
    db.execute("UPDATE group_join_requests SET status=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(status,req_id)); db.commit()
    return jsonify(ok=True,message=f"User {status.lower()} for {row['group_name']}.")


@app.post("/api/superuser/group/<int:group_id>/member/<int:user_id>/remove")
@role_required("SUPER_USER")
def remove_group_member(group_id,user_id):
    if not require_csrf():return jsonify(error="Invalid security token."),400
    require_group_access(group_id)
    db=get_db(); db.execute("UPDATE group_members SET status='DISABLED' WHERE group_id=? AND user_id=?",(group_id,user_id)); db.commit()
    return jsonify(ok=True,message="User removed from the Group.")


@app.get("/api/groups")
@login_required
def groups_api():
    user=current_user(); db=get_db()
    if user["role"] == "ADMIN":
        rows=db.execute("SELECT g.id,g.name,g.access_username,g.status,u.name AS super_name FROM groups g JOIN users u ON u.id=g.super_user_id ORDER BY g.name").fetchall()
    elif user["role"] == "SUPER_USER":
        rows=db.execute("SELECT id,name,access_username,status FROM groups WHERE super_user_id=? ORDER BY name", (user["id"],)).fetchall()
    else:
        rows=db.execute("SELECT g.id,g.name,g.access_username,g.status FROM groups g JOIN group_members gm ON gm.group_id=g.id WHERE gm.user_id=? AND gm.status='ACTIVE' ORDER BY g.name", (user["id"],)).fetchall()
    return jsonify(groups=[dict(r) for r in rows])


@app.post("/api/group/login")
@login_required
def group_login():
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    group_id=request.form.get("group_id", type=int); username=request.form.get("username", "").strip(); password=request.form.get("password", "")
    if not group_id: return jsonify(error="Select a group."), 400
    group=require_group_access(group_id, allow_super=True)
    if current_user()["role"] == "ADMIN": return jsonify(error="Admin uses metadata access and cannot enter a group secret workspace."), 403
    if group["access_username"] != username or not check_password_hash(group["access_password_hash"], password): return jsonify(error="Invalid Group username or password."), 401
    session["group_id"] = group_id
    session["group_unlocked_id"] = group_id
    get_db().execute("INSERT INTO group_sessions(group_id,user_id) VALUES(?,?)", (group_id,current_user()["id"])); get_db().commit()
    return jsonify(ok=True, group_id=group_id, group_name=group["name"])


@app.post("/api/group/select")
@login_required
def select_group():
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    group_id=request.form.get("group_id", type=int)
    if not group_id: return jsonify(error="Select a group."), 400
    require_group_access(group_id, allow_super=True)
    session["group_id"] = group_id
    return jsonify(ok=True)


def active_group_for_user():
    group_id=session.get("group_id")
    unlocked_id=session.get("group_unlocked_id")
    if not group_id or unlocked_id != group_id:
        raise PermissionError("Select and unlock a group first.")
    return require_group_access(group_id, allow_super=True)


@app.post("/api/encode")
@login_required
def encode():
    if not require_csrf(): return jsonify(error="Invalid security token."), 400
    if current_user()["role"] == "ADMIN": return jsonify(error="Admin can audit encoding metadata but cannot create/read secret messages."), 403
    try: group=active_group_for_user()
    except PermissionError as exc: return jsonify(error=str(exc)), 403
    file=request.files.get("image"); message=request.form.get("message", "").strip()
    if not file or not file.filename or not allowed(file.filename): return jsonify(error="Please upload a PNG, JPG, JPEG, or WEBP image."),400
    if not message: return jsonify(error="Please enter a secret message."),400
    try:
        raw=file.read(); image=image_from_bytes(raw); result=hide_data(image,message,group); output=png_bytes(result)
        db=get_db(); db.execute("INSERT INTO activities(group_id,user_id,operation,original_filename,output_filename,image_blob,secret_message_encrypted) VALUES(?,?,?,?,?,?,?)", (group["id"],current_user()["id"],"ENCODE",file.filename,"encoded-image.png",output,encrypt_message(message))); db.commit()
        return send_file(io.BytesIO(output),mimetype="image/png",as_attachment=True,download_name="encoded-image.png")
    except Exception as exc: return jsonify(error=str(exc)),400


@app.post("/api/decode")
@login_required
def decode():
    if not require_csrf(): return jsonify(error="Invalid security token."),400
    if current_user()["role"] == "ADMIN": return jsonify(error="Admin cannot access secret messages."),403
    try: group=active_group_for_user()
    except PermissionError as exc: return jsonify(error=str(exc)),403
    file=request.files.get("image")
    if not file or not file.filename or not allowed(file.filename): return jsonify(error="Please upload a PNG, JPG, JPEG, or WEBP image."),400
    try:
        raw=file.read(); image=image_from_bytes(raw); message=unhide_data(image,group)
        db=get_db(); db.execute("INSERT INTO activities(group_id,user_id,operation,original_filename,output_filename,image_blob,secret_message_encrypted) VALUES(?,?,?,?,?,?,?)", (group["id"],current_user()["id"],"DECODE",file.filename,file.filename,raw,encrypt_message(message))); db.commit()
        return jsonify(message=message)
    except Exception as exc: return jsonify(error=str(exc)),400


@app.get("/api/group/activity")
@login_required
def group_activity():
    if current_user()["role"] == "ADMIN": return jsonify(error="Use the Admin audit endpoint; Admin cannot view secret content."),403
    try: group=active_group_for_user()
    except PermissionError as exc: return jsonify(error=str(exc)),403
    rows=get_db().execute("SELECT a.*,u.name AS user_name,u.email FROM activities a JOIN users u ON u.id=a.user_id WHERE a.group_id=? ORDER BY a.created_at DESC LIMIT 100", (group["id"],)).fetchall()
    result=[]
    for r in rows:
        d=dict(r); d["secret_message"]=decrypt_message(r["secret_message_encrypted"]) if r["secret_message_encrypted"] else ""; d.pop("secret_message_encrypted",None); d.pop("image_blob",None); result.append(d)
    return jsonify(activity=result)


@app.get("/api/admin/audit")
@role_required("ADMIN")
def admin_audit():
    rows=get_db().execute("SELECT a.id,a.group_id,a.user_id,a.operation,a.original_filename,a.output_filename,a.created_at,a.status,g.name AS group_name,u.name AS user_name,u.email FROM activities a LEFT JOIN groups g ON g.id=a.group_id JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC LIMIT 200").fetchall()
    return jsonify(activity=[dict(r) for r in rows])


@app.get("/api/admin/activity/<int:activity_id>/image")
@role_required("ADMIN")
def admin_activity_image(activity_id):
    row=get_db().execute("SELECT image_blob,output_filename,original_filename FROM activities WHERE id=?", (activity_id,)).fetchone()
    if not row or not row["image_blob"]: return jsonify(error="Image not available."),404
    name=row["output_filename"] or row["original_filename"] or "activity-image.png"
    return send_file(io.BytesIO(row["image_blob"]),mimetype="image/png",download_name=name)


@app.post("/api/convert-png")
@login_required
def convert_png():
    if not require_csrf(): return jsonify(error="Invalid security token."),400
    if current_user()["role"]=="ADMIN": return jsonify(error="Admin audit mode does not use transformation tools."),403
    try: active_group_for_user()
    except PermissionError as exc: return jsonify(error=str(exc)),403
    file=request.files.get("image")
    if not file or not file.filename or not allowed(file.filename): return jsonify(error="Please upload a supported image."),400
    try:
        img=Image.open(io.BytesIO(file.read())).convert("RGBA"); out=io.BytesIO(); img.save(out,"PNG"); out.seek(0)
        return send_file(out,mimetype="image/png",as_attachment=True,download_name="converted-image.png")
    except Exception as exc:return jsonify(error=str(exc)),400


@app.post("/api/grayscale")
@login_required
def grayscale():
    if not require_csrf(): return jsonify(error="Invalid security token."),400
    if current_user()["role"]=="ADMIN": return jsonify(error="Admin audit mode does not use transformation tools."),403
    try: active_group_for_user()
    except PermissionError as exc:return jsonify(error=str(exc)),403
    file=request.files.get("image")
    if not file or not file.filename or not allowed(file.filename):return jsonify(error="Please upload a supported image."),400
    try:
        img=Image.open(io.BytesIO(file.read())).convert("L"); out=io.BytesIO(); img.save(out,"PNG"); out.seek(0)
        return send_file(out,mimetype="image/png",as_attachment=True,download_name="grayscale-image.png")
    except Exception as exc:return jsonify(error=str(exc)),400


@app.post("/api/merge")
@login_required
def merge():
    if not require_csrf(): return jsonify(error="Invalid security token."),400
    if current_user()["role"]=="ADMIN": return jsonify(error="Admin audit mode does not use transformation tools."),403
    try: active_group_for_user()
    except PermissionError as exc:return jsonify(error=str(exc)),403
    file1=request.files.get("image1"); file2=request.files.get("image2")
    if not file1 or not file2 or not allowed(file1.filename) or not allowed(file2.filename):return jsonify(error="Please upload two supported images."),400
    try:
        im1=Image.open(io.BytesIO(file1.read())).convert("RGB"); im2=Image.open(io.BytesIO(file2.read())).convert("RGB")
        if im1.height!=im2.height:
            ratio=im2.width/im2.height; im2=im2.resize((int(ratio*im1.height),im1.height),Image.LANCZOS)
        merged=Image.new("RGB",(im1.width+im2.width,im1.height)); merged.paste(im1,(0,0)); merged.paste(im2,(im1.width,0)); out=io.BytesIO(); merged.save(out,"PNG"); out.seek(0)
        return send_file(out,mimetype="image/png",as_attachment=True,download_name="merged-image.png")
    except Exception as exc:return jsonify(error=str(exc)),400


@app.errorhandler(413)
def too_large(_):
    if request.path.startswith("/api/"): return jsonify(error="File is too large. Maximum upload size is 20 MB."),413
    return "File is too large. Maximum upload size is 20 MB.",413


if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
