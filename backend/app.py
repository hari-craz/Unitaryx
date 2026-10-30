"""
Unitary X - Premium Tech Freelancer Website
Flask Backend with Authentication System
"""

from flask import (Flask, render_template, request, jsonify, make_response,
                   redirect, url_for, flash, session, send_from_directory, abort)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename, safe_join
from datetime import datetime, timedelta
from functools import wraps
import os, re, urllib.parse, random, smtplib, ssl, csv, json, hashlib, uuid, secrets
from io import StringIO
from email.message import EmailMessage
from .mailers import (send_welcome_email as queue_welcome_email, send_assigned_email as queue_assigned_email,
                      send_newsletter_confirm_email as queue_newsletter_confirm_email)
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy import inspect, or_, text
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image, ImageOps, UnidentifiedImageError

# Security & Config
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_seasurf import SeaSurf
from dotenv import load_dotenv

# Keep container/host env vars authoritative while still supporting local .env defaults.
APP_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
BACKUP_DIR = os.path.join(APP_DIR, "instance", "db_backups")
load_dotenv(os.path.join(APP_DIR, ".env"), override=False)
# Also support launching from workspace root where SMTP/OAuth vars are often stored.
load_dotenv(os.path.join(os.path.dirname(APP_DIR), ".env"), override=False)
# When running from a git worktree (…/.claude/worktrees/<name>/backend) the
# real .env lives several levels up in the main checkout and isn't copied in
# (it's gitignored). Walk up the tree and load the first .env found so local
# worktree runs pick up SMTP/OAuth creds instead of silently failing to send.
# Skipped under the test suite (conftest sets the flag) so tests never inherit
# real SMTP creds / prod values and can't hit live mail servers.
if not os.getenv("UNITARYX_SKIP_DOTENV_WALKUP"):
    _env_probe = os.path.dirname(APP_DIR)
    for _ in range(6):
        _env_probe = os.path.dirname(_env_probe)
        if not _env_probe:
            break
        _candidate = os.path.join(_env_probe, ".env")
        if os.path.isfile(_candidate):
            load_dotenv(_candidate, override=False)
            break

# Canonical public URL, used for absolute links in transactional emails (the
# welcome/task CTA buttons render only when this is set). Falls back to the
# production domain so those buttons never silently disappear when APP_URL is
# left blank in the environment.
DEFAULT_APP_URL = "https://unitaryx.org"

def resolved_app_url():
    return (os.getenv("APP_URL") or "").strip() or DEFAULT_APP_URL

app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "frontend", "templates"),
    static_folder=os.path.join(PROJECT_ROOT, "frontend", "static"),
)
# Respect original scheme/host when running behind reverse proxies (NPM/Traefik).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_port=1)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True
_secret_key = (os.getenv("SECRET_KEY") or "").strip()
if not _secret_key:
    if (os.getenv("DEBUG", "False").strip().lower() == "true"):
        _secret_key = "dev-only-insecure-secret-key"
    else:
        raise RuntimeError("SECRET_KEY must be set (only DEBUG=true may run without it).")
app.secret_key = _secret_key
PASSWORD_HASH_METHOD = (os.getenv("PASSWORD_HASH_METHOD") or "pbkdf2:sha256:260000").strip()

_default_google_client_id = "your_google_client_id_here.apps.googleusercontent.com"
_env_google_client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
if not _env_google_client_id or "your_google_client_id_here" in _env_google_client_id:
    app.config['GOOGLE_CLIENT_ID'] = _default_google_client_id
else:
    app.config['GOOGLE_CLIENT_ID'] = _env_google_client_id

DEFAULT_GOOGLE_ALLOWED_ORIGINS = {
    "https://unitaryx.org",
    "http://localhost:10003",
    "http://127.0.0.1:10003",
    "http://unitaryx.org",
    
}

OAUTH_ADMIN_EMAILS = {
    "harikavi1301@gmail.com",
    "darshankannan2008@gmail.com",
}

SUPERADMIN_EMAIL = (os.getenv("SUPERADMIN_EMAIL", "harikavi1301@gmail.com") or "").strip().lower()
_DEBUG_MODE = (os.getenv("DEBUG", "False").strip().lower() == "true")
# Known default passwords exist only for local DEBUG runs; in production an
# unset value yields a random unguessable password (sign in via Google / OTP reset).
SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD") or ("hari@123" if _DEBUG_MODE else os.urandom(18).hex())
SUPERADMIN_NAME = (os.getenv("SUPERADMIN_NAME") or "Super Admin").strip() or "Super Admin"


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_role(value):
    role = (value or "user").strip().lower()
    return role if role in {"user", "admin"} else "user"


def normalize_admin_scope(value):
    scope = (value or "ops").strip().lower()
    return scope if scope in {"superadmin", "ops", "finance", "support"} else "ops"


def normalize_finance_entry_type(value):
    entry_type = (value or "receivable").strip().lower()
    return entry_type if entry_type in {"receivable", "payable"} else "receivable"


def find_user_by_email(email):
    normalized = normalize_email(email)
    if not normalized:
        return None
    return User.query.filter(db.func.lower(User.email) == normalized).first()


def oauth_admin_emails():
    emails = {normalize_email(e) for e in OAUTH_ADMIN_EMAILS if normalize_email(e)}
    configured_admin = normalize_email(os.getenv("ADMIN_EMAIL", "admin@unitaryx.com"))
    if configured_admin:
        emails.add(configured_admin)
    emails.add(normalize_email(SUPERADMIN_EMAIL))
    return emails


def is_admin_identity(email, existing_user=None):
    normalized = normalize_email(email)
    if normalized == normalize_email(SUPERADMIN_EMAIL):
        return True
    if existing_user and normalize_role(existing_user.role) == "admin":
        return True
    admin_user = User.query.filter(
        db.func.lower(User.email) == normalized,
        db.func.lower(User.role) == 'admin'
    ).first()
    if admin_user:
        return True

    cred_record = AdminCredentialRecord.query.filter(
        db.func.lower(AdminCredentialRecord.admin_email) == normalized
    ).first()
    if cred_record:
        return True

    return normalized in oauth_admin_emails()


def establish_session_for_user(user, remember=False, profile_photo=None, auth_provider="password"):
    user_email = normalize_email(user.email)
    role = normalize_role(user.role)
    is_superadmin_account = user_email == normalize_email(SUPERADMIN_EMAIL) or normalize_admin_scope(getattr(user, 'admin_scope', 'ops')) == 'superadmin'
    if is_superadmin_account:
        role = "admin"
    session.permanent = bool(remember)
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['user_email'] = user_email
    session['role'] = role
    session['is_superadmin'] = is_superadmin_account
    session['admin_scope'] = normalize_admin_scope(
        'superadmin' if session['is_superadmin'] else getattr(user, 'admin_scope', 'ops')
    ) if role == 'admin' else ''
    session['user_profile_photo'] = (profile_photo or "").strip()
    session['auth_provider'] = (auth_provider or "password").strip().lower()
    _register_user_session(user)


def _register_user_session(user):
    if not user or not getattr(user, 'id', None):
        return

    existing_token = str(session.get('session_token') or '').strip()
    if existing_token:
        active = UserSession.query.filter_by(
            user_id=user.id,
            session_token=existing_token,
            is_active=True,
        ).first()
        if active:
            active.last_seen = datetime.utcnow()
            active.ip_address = (_extract_client_ip() or '')[:64] or None
            active.user_agent = (request.user_agent.string or '')[:255] or None
            db.session.commit()
            return

    fresh_token = os.urandom(24).hex()
    device = UserSession(
        user_id=user.id,
        session_token=fresh_token,
        ip_address=(_extract_client_ip() or '')[:64] or None,
        user_agent=(request.user_agent.string or '')[:255] or None,
        last_seen=datetime.utcnow(),
        is_active=True,
    )
    session['session_token'] = fresh_token
    db.session.add(device)
    db.session.commit()

# ─── Security Configuration ──────────────────────────────────────────────────

# 1. CSRF Protection
# Cookie/session/form field name defaults to '_csrf_token' (still emitted by the
# remaining Jinja login form) and header name defaults to 'X-CSRFToken' (used by
# the React studio/dashboard fetch wrapper).
csrf = SeaSurf(app)

# 2. Secure Headers (Talisman)
# Force HTTPS only in production, but here we keep it flexible
csp = {
    'default-src': [
        '\'self\'',
        'https://cdnjs.cloudflare.com',
        'https://fonts.googleapis.com',
        'https://fonts.gstatic.com',
        'https://use.fontawesome.com',
        'https://cdn.jsdelivr.net',
    ],
    'img-src': ['\'self\'', 'data:', '*', 'https://www.google.com', 'https://translate.googleapis.com'],
    'media-src': ['\'self\'', 'https://cdn.pixabay.com', 'data:', '*'],
    # Vite inlines small font files as data: URIs; without this they are blocked.
    'font-src': [
        '\'self\'',
        'data:',
        'https://fonts.gstatic.com',
        'https://cdnjs.cloudflare.com',
        'https://use.fontawesome.com',
        'https://cdn.jsdelivr.net',
    ],
    # No 'unsafe-inline' / 'unsafe-eval': the one inline script (login page) carries
    # a per-request nonce via csp_nonce(); the React bundle is external.
    'script-src': [
        '\'self\'',
        'https://cdnjs.cloudflare.com',
        'https://cdn.jsdelivr.net',
        'https://accounts.google.com'
    ],
    'style-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        'https://cdnjs.cloudflare.com',
        'https://fonts.googleapis.com',
        'https://use.fontawesome.com',
        'https://cdn.jsdelivr.net',
        'https://accounts.google.com/gsi/style'
    ],
    'connect-src': [
        '\'self\'',
        'https://translate.googleapis.com',
        'https://accounts.google.com',
        'https://oauth2.googleapis.com',
        'https://www.googleapis.com'
    ],
    'frame-src': [
        '\'self\'',
        'https://translate.google.com',
        'https://accounts.google.com'
    ],
}

talisman = Talisman(
    app,
    content_security_policy=csp,
    content_security_policy_nonce_in=['script-src'],
    force_https=False, # Set to True in production with SSL
    session_cookie_secure=(os.getenv("COOKIE_SECURE", "False").strip().lower() in {"1", "true", "yes", "on"}),  # set COOKIE_SECURE=true behind HTTPS
    session_cookie_http_only=True,
    session_cookie_samesite='Lax',
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    frame_options='DENY', # Blocks clickjacking attacks
    x_xss_protection=True
)

# 3. Rate Limiting (Relaxed for Development)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["10000 per day", "2000 per hour"],
    # Shared store (e.g. redis://redis:6379/2) makes limits hold across Gunicorn workers.
    storage_uri=(os.getenv("RATELIMIT_STORAGE_URI") or "memory://"),
)


@app.after_request
def add_no_cache_headers(response):
    # Prevent stale cache so local template/CSS/JS changes are visible immediately.
    path = (request.path or "").lower()
    if (
        path.startswith("/static/")
        or response.mimetype in {"text/html", "text/css", "application/javascript", "application/json"}
        or path in {"/login", "/send-otp", "/verify-otp", "/reset-password"}
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ─── Database ─────────────────────────────────────────────────────────────────
basedir = os.path.abspath(os.path.dirname(__file__))

# Build DATABASE_URL from individual components if not explicitly set
_database_url = os.getenv("DATABASE_URL", "").strip()
if not _database_url:
    _db_user = (os.getenv("POSTGRES_USER") or "unitaryx").strip()
    _db_pass = os.getenv("POSTGRES_PASSWORD") or "ChangeThisDbPassword!"
    _db_host = (os.getenv("DB_HOST") or "db").strip() or "db"
    _db_port = (os.getenv("DB_PORT") or "5432").strip() or "5432"
    _db_name = (os.getenv("POSTGRES_DB") or "unitaryx").strip()
    # Use psycopg (psycopg3) driver for PostgreSQL
    _database_url = (
        f"postgresql+psycopg://{urllib.parse.quote_plus(_db_user)}"
        f":{urllib.parse.quote_plus(_db_pass)}@{_db_host}:{_db_port}/{_db_name}"
    )

app.config['SQLALCHEMY_DATABASE_URI'] = _database_url or f"sqlite:///{os.path.join(basedir, 'unitaryx_v2.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db_uri = (app.config['SQLALCHEMY_DATABASE_URI'] or "").lower()
if db_uri.startswith("sqlite"):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "connect_args": {"timeout": 5}
    }
else:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "connect_args": {"connect_timeout": 5},
        "pool_pre_ping": True,
    }
db = SQLAlchemy(app)


# ─── Models ───────────────────────────────────────────────────────────────────

class User(db.Model):
    """Registered users (students)"""
    __tablename__ = 'users'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(150), unique=True, nullable=False)
    password     = db.Column(db.String(200), nullable=False)
    role         = db.Column(db.String(20), default='user')   # 'user' | 'admin'
    admin_scope  = db.Column(db.String(20), default='ops')     # superadmin | ops | finance | support
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    is_active    = db.Column(db.Boolean, default=True)

    def set_password(self, raw):
        self.password = generate_password_hash(raw, method=PASSWORD_HASH_METHOD)

    def check_password(self, raw):
        return check_password_hash(self.password, raw)


class UserSession(db.Model):
    """Tracks active login sessions for device management."""
    __tablename__ = 'user_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_token = db.Column(db.String(96), nullable=False, unique=True, index=True)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)


class ABTestConfig(db.Model):
    """Stores configurable A/B experiments for landing content."""
    __tablename__ = 'ab_test_configs'

    id = db.Column(db.Integer, primary_key=True)
    test_key = db.Column(db.String(60), unique=True, nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    allocation_b = db.Column(db.Integer, default=50, nullable=False)
    variant_a = db.Column(db.String(300), nullable=False)
    variant_b = db.Column(db.String(300), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SiteTrafficEvent(db.Model):
    """Stores anonymous and signed-in traffic events for analytics."""
    __tablename__ = 'site_traffic_events'

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.String(80), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    user_email = db.Column(db.String(150), nullable=True, index=True)
    event_type = db.Column(db.String(20), nullable=False, index=True)  # page_view | scroll
    page_path = db.Column(db.String(260), nullable=False)
    scroll_percent = db.Column(db.Integer, nullable=True)
    referrer = db.Column(db.String(260), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class PasswordResetOTP(db.Model):
    """Stores OTP codes for password reset flow."""
    __tablename__ = 'password_reset_otps'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False, index=True)
    otp = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts_left = db.Column(db.Integer, nullable=False, default=5)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AdminTask(db.Model):
    """Tasks assigned by superadmin to specific admin emails."""
    __tablename__ = 'admin_tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    details = db.Column(db.Text)
    assigned_to_email = db.Column(db.String(150), nullable=False, index=True)
    assigned_by_email = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class FinanceEntry(db.Model):
    """Finance records handled by finance admins and checked by superadmin."""
    __tablename__ = 'finance_entries'

    id = db.Column(db.Integer, primary_key=True)
    entry_type = db.Column(db.String(20), nullable=False, default='receivable', index=True)  # receivable | payable
    title = db.Column(db.String(180), nullable=False)
    counterparty = db.Column(db.String(180), nullable=False)
    amount = db.Column(db.Integer, nullable=False, default=0)
    due_date = db.Column(db.String(20))
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), nullable=False, default='submitted', index=True)  # submitted | processed | needs_superadmin_check | closed | rejected
    assigned_admin_email = db.Column(db.String(150), nullable=False, index=True)
    created_by_email = db.Column(db.String(150), nullable=False, index=True)
    reviewed_by_email = db.Column(db.String(150), nullable=True, index=True)
    review_note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AdminFeedback(db.Model):
    """Public feedback corner for signed-in admins/superadmin."""
    __tablename__ = 'admin_feedback'

    id = db.Column(db.Integer, primary_key=True)
    author_email = db.Column(db.String(150), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    author_scope = db.Column(db.String(20), nullable=False, default='ops')
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class Subscriber(db.Model):
    """Newsletter subscriber. Double opt-in: the confirmation email is sent
    while `confirmed` is false; campaign mail, if later added, must be
    restricted to confirmed rows; unsubscribing deletes the row."""
    __tablename__ = 'subscribers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    confirmed = db.Column(db.Boolean, default=False, nullable=False)
    confirm_token = db.Column(db.String(64), unique=True, nullable=False)
    unsub_token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = db.Column(db.DateTime)
    last_sent_at = db.Column(db.DateTime)


class PublicFeedback(db.Model):
    """Public-site feedback submitted by signed-in users."""
    __tablename__ = 'public_feedback'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    author_email = db.Column(db.String(150), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    rating = db.Column(db.Integer, nullable=False, default=5)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class AdminAuditLog(db.Model):
    """Tracks sensitive superadmin actions for accountability."""
    __tablename__ = 'admin_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_email = db.Column(db.String(150), nullable=False, index=True)
    action = db.Column(db.String(80), nullable=False)
    target = db.Column(db.String(180))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class ApprovalTicket(db.Model):
    """Approval queue for sensitive admin operations."""
    __tablename__ = 'approval_tickets'

    id = db.Column(db.Integer, primary_key=True)
    action_key = db.Column(db.String(60), nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=False)
    requested_by_email = db.Column(db.String(150), nullable=False, index=True)
    requested_by_scope = db.Column(db.String(20), nullable=False, default='ops')
    reason = db.Column(db.String(240))
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)  # pending | approved | rejected
    reviewed_by_email = db.Column(db.String(150))
    review_note = db.Column(db.String(300))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
class AdminCredentialRecord(db.Model):
    """Stores superadmin-managed admin credential references."""
    __tablename__ = 'admin_credential_records'

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    admin_email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    temporary_password = db.Column(db.String(200), nullable=False)
    permanent_password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
def upsert_admin_credential_record(admin_user_id, admin_email, temporary_password, permanent_password):
    normalized_email = (admin_email or "").strip().lower()
    record = AdminCredentialRecord.query.filter(
        db.func.lower(AdminCredentialRecord.admin_email) == normalized_email
    ).first()

    if not record and admin_user_id:
        record = AdminCredentialRecord.query.filter_by(admin_user_id=admin_user_id).first()

    if record:
        record.admin_user_id = admin_user_id or record.admin_user_id
        record.admin_email = normalized_email
        record.temporary_password = ""
        record.permanent_password = ""  # never persist plaintext passwords
        record.updated_at = datetime.utcnow()
    else:
        record = AdminCredentialRecord(
            admin_user_id=admin_user_id,
            admin_email=normalized_email,
            temporary_password="",
            permanent_password="",
        )
        db.session.add(record)

    return record


def sync_admin_vault_to_latest_password(admin_user, latest_password):
    """Keep only one latest vault entry for an admin and drop stale password records."""
    if not admin_user or normalize_role(admin_user.role) != 'admin':
        return

    normalized_email = normalize_email(admin_user.email)
    if not normalized_email:
        return

    # Remove stale records tied to this admin id or email, then keep only latest.
    AdminCredentialRecord.query.filter(
        (AdminCredentialRecord.admin_user_id == admin_user.id)
        | (db.func.lower(AdminCredentialRecord.admin_email) == normalized_email)
    ).delete(synchronize_session=False)

    db.session.add(AdminCredentialRecord(
        admin_user_id=admin_user.id,
        admin_email=normalized_email,
        temporary_password="",
        permanent_password="",
    ))


class ProjectRequest(db.Model):
    """Project enquiries from students"""
    __tablename__ = 'project_requests'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), nullable=False)
    phone      = db.Column(db.String(20))
    service    = db.Column(db.String(80), nullable=False)
    deadline   = db.Column(db.String(30))
    message    = db.Column(db.Text, nullable=False)
    status     = db.Column(db.String(30), default='New')
    is_new_update = db.Column(db.Boolean, default=False)
    priority   = db.Column(db.String(20), default='Medium')
    value      = db.Column(db.Integer, default=0)
    lead_score_value = db.Column(db.Integer, default=0)
    lead_score_urgency = db.Column(db.Integer, default=0)
    lead_score_conversion = db.Column(db.Integer, default=0)
    lead_score_total = db.Column(db.Integer, default=0, index=True)
    lead_tier = db.Column(db.String(20), default='C')
    lead_last_scored_at = db.Column(db.DateTime)
    stale_flag = db.Column(db.Boolean, default=False, index=True)
    escalation_level = db.Column(db.Integer, default=0)
    last_followup_at = db.Column(db.DateTime)
    next_followup_at = db.Column(db.DateTime)
    internal_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user       = db.relationship('User', backref='requests', lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "phone": self.phone, "service": self.service,
            "deadline": self.deadline, "message": self.message,
            "status": self.status,
            "lead_score_total": self.lead_score_total,
            "lead_tier": self.lead_tier,
            "created_at": self.created_at.strftime("%d %b %Y, %I:%M %p"),
        }


class Project(db.Model):
    """Portfolio projects shown on the website"""
    __tablename__ = 'projects'

    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category    = db.Column(db.String(50), nullable=False)
    tags        = db.Column(db.String(200))
    price       = db.Column(db.String(30))
    duration    = db.Column(db.String(30))
    rating      = db.Column(db.Float, default=5.0)
    icon        = db.Column(db.String(80))
    bg_class    = db.Column(db.String(30))
    featured    = db.Column(db.Boolean, default=False)
    display_order = db.Column(db.Integer, default=0)
    photo_url   = db.Column(db.String(300))
    problem     = db.Column(db.Text)
    approach    = db.Column(db.Text)
    outcome     = db.Column(db.Text)
    stack       = db.Column(db.String(300))

    @property
    def has_case_study(self):
        return bool((self.problem or self.approach or self.outcome or "").strip())

    @property
    def slug(self):
        base = re.sub(r"[^a-z0-9]+", "-", (self.title or "").lower()).strip("-")[:60].strip("-")
        return f"{base}-{self.id}" if base else str(self.id)

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "slug": self.slug,
            "description": self.description, "category": self.category,
            "tags": self.tags.split(",") if self.tags else [],
            "price": self.price, "duration": self.duration,
            "rating": self.rating, "icon": self.icon,
            "bg_class": self.bg_class, "featured": self.featured,
            "display_order": self.display_order or 0,
            "photo_url": self.photo_url,
            "problem": self.problem, "approach": self.approach, "outcome": self.outcome,
            "stack": self.stack.split(",") if self.stack else [],
            "has_case_study": self.has_case_study,
        }


class Testimonial(db.Model):
    """Student testimonials"""
    __tablename__ = 'testimonials'

    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    role     = db.Column(db.String(150))
    review   = db.Column(db.Text, nullable=False)
    rating   = db.Column(db.Integer, default=5)
    avatar   = db.Column(db.String(10))
    av_class = db.Column(db.String(20))
    active   = db.Column(db.Boolean, default=True)


class Founder(db.Model):
    """Team members shown in the founders/team carousel (table name kept as
    'founders' for continuity, but holds the whole ~10-person team)."""
    __tablename__ = 'founders'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    role          = db.Column(db.String(120), nullable=False)
    bio           = db.Column(db.Text)
    photo_url     = db.Column(db.String(300))
    socials       = db.Column(db.Text)  # JSON-serialized dict, e.g. {"linkedin": "...", "github": "..."}
    display_order = db.Column(db.Integer, default=0)
    active        = db.Column(db.Boolean, default=True)

    def to_dict(self):
        try:
            socials = json.loads(self.socials) if self.socials else {}
        except (TypeError, ValueError):
            socials = {}
        return {
            "id": self.id, "name": self.name, "role": self.role,
            "bio": self.bio, "photo_url": self.photo_url,
            "socials": socials,
            "display_order": self.display_order or 0,
            "active": bool(self.active),
        }


DB_BACKUP_MODELS = {
    "ab_test_configs": ABTestConfig,
    "projects": Project,
    "testimonials": Testimonial,
    "founders": Founder,
    "subscribers": Subscriber,
    "project_requests": ProjectRequest,
    "admin_tasks": AdminTask,
    "admin_audit_logs": AdminAuditLog,
    "site_traffic_events": SiteTrafficEvent,
}


def _serialize_db_value(value):
    if isinstance(value, datetime):
        return {"__type": "datetime", "value": value.isoformat()}
    return value


def _deserialize_db_value(value):
    if isinstance(value, dict) and value.get("__type") == "datetime":
        raw = str(value.get("value") or "").strip()
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None
        return None
    return value


def _safe_backup_filename(raw_name):
    raw = str(raw_name or "").strip()
    if not raw or len(raw) > 140:
        return ""
    if not re.match(r"^[A-Za-z0-9._-]+\.json$", raw):
        return ""
    return raw


def _build_backup_payload(actor_email):
    payload = {
        "created_at": datetime.utcnow().isoformat(),
        "created_by": (actor_email or "").strip().lower(),
        "tables": {},
    }
    row_count = 0
    for table_name, model in DB_BACKUP_MODELS.items():
        rows = []
        for obj in model.query.order_by(model.id.asc()).all():
            row = {}
            for col in model.__table__.columns:
                row[col.name] = _serialize_db_value(getattr(obj, col.name))
            rows.append(row)
        payload["tables"][table_name] = rows
        row_count += len(rows)
    payload["row_count"] = row_count
    return payload


def _restore_backup_payload(payload):
    tables = payload.get("tables") if isinstance(payload, dict) else {}
    if not isinstance(tables, dict):
        raise ValueError("Invalid backup payload format.")

    # The audit trail is append-only: a restore never replaces it.
    restorable = {n: m for n, m in DB_BACKUP_MODELS.items() if n != "admin_audit_logs"}
    if not any(isinstance(tables.get(name), list) for name in restorable):
        raise ValueError("Backup contains no recognised tables; nothing was restored.")

    # Only wipe tables the backup actually carries.
    for name, model in restorable.items():
        if isinstance(tables.get(name), list):
            model.query.delete(synchronize_session=False)

    user_ids = {u.id for u in User.query.with_entities(User.id).all()}

    for table_name, model in restorable.items():
        rows = tables.get(table_name, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            clean = {}
            for col in model.__table__.columns:
                if col.name not in row:
                    continue
                clean[col.name] = _deserialize_db_value(row.get(col.name))

            if model is ProjectRequest:
                uid = clean.get("user_id")
                if uid and uid not in user_ids:
                    clean["user_id"] = None

            db.session.add(model(**clean))


# ─── Template Filters ─────────────────────────────────────────────────────────

@app.template_filter('format_id')
def format_id_filter(id_val):
    """Formats ID as 4-digit strings like 0001"""
    return f"{id_val:04d}"


# ─── Auth Decorators ──────────────────────────────────────────────────────────

def login_required(f):
    """Ensures user is logged in (any role)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Ensures user is logged in as admin. (Relaxed for Dev)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', tab='admin'))
        if session.get('role') != 'admin':
            flash('Admin access only.', 'danger')
            return redirect(url_for('user_dashboard'))
        return f(*args, **kwargs)
    return decorated


def api_admin_required(f):
    """Same session checks as admin_required, but always responds with JSON
    (401/403) instead of redirecting — for fetch-only /api/admin/* routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Authentication required."}), 401
        if session.get('role') != 'admin':
            return jsonify({"success": False, "message": "Admin access only."}), 403
        return f(*args, **kwargs)
    return decorated


def api_superadmin_required(f):
    """Like api_admin_required, but additionally restricts to the superadmin
    account (by email or admin_scope == 'superadmin'). Used for Founders/
    Projects management, which is deliberately kept out of reach of ordinary
    ops/finance/support admins and, of course, consumer accounts."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Authentication required."}), 401
        if session.get('role') != 'admin':
            return jsonify({"success": False, "message": "Admin access only."}), 403
        if not is_super_admin(current_user()):
            return jsonify({"success": False, "message": "Superadmin access only."}), 403
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    """Like login_required, but responds with JSON 401 instead of redirecting —
    for fetch-only customer API routes (e.g. the React dashboard)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Authentication required."}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _password_policy_error(password):
    """Single password policy shared by registration and reset."""
    if len(password) < 6:
        return "Password must be at least 6 characters."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter (e.g. A, B, C...)."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number (e.g. 1, 2, 3...)."
    if not any(c in "@%#$!&*_-+=" for c in password):
        return "Password must contain at least one symbol (e.g. @, %, #, $, !)."
    return None


def validate_email(email):
    return bool(re.match(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$', email))


def wants_json_response():
    accept = (request.headers.get("Accept") or "").lower()
    requested_with = (request.headers.get("X-Requested-With") or "").lower()
    return request.is_json or "application/json" in accept or requested_with == "xmlhttprequest"


def request_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.form


def parse_remember_flag(value):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "on", "yes", "y"}


def end_current_session():
    token = str(session.get('session_token') or '').strip()
    uid = session.get('user_id')
    if token and uid:
        row = UserSession.query.filter_by(user_id=uid, session_token=token).first()
        if row:
            row.is_active = False
            row.last_seen = datetime.utcnow()
            db.session.commit()
    session.clear()


def _parse_deadline_days(deadline_value):
    raw = (deadline_value or "").strip()
    if not raw:
        return None

    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            target = datetime.strptime(raw, fmt).date()
            return (target - datetime.utcnow().date()).days
        except ValueError:
            continue
    return None


def _clamp_score(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _score_project_request(req):
    # Value score (higher budget usually signals stronger intent).
    value = int(req.value or 0)
    value_score = _clamp_score((value / 50000.0) * 100)

    # Urgency score from priority + deadline proximity.
    priority_text = (req.priority or "Medium").strip().lower()
    priority_base = {"high": 80, "medium": 55, "low": 30}.get(priority_text, 50)
    urgency_bonus = 0
    days_to_deadline = _parse_deadline_days(req.deadline)
    if days_to_deadline is not None:
        if days_to_deadline <= 2:
            urgency_bonus = 20
        elif days_to_deadline <= 7:
            urgency_bonus = 12
        elif days_to_deadline <= 14:
            urgency_bonus = 6
    urgency_score = _clamp_score(priority_base + urgency_bonus)

    # Conversion score from message quality + service fit + urgency signal.
    msg_len = len((req.message or "").strip())
    message_component = min(22, msg_len // 14)
    service_text = (req.service or "").strip().lower()
    service_bonus = 0
    if any(k in service_text for k in ["web", "app", "ai", "software"]):
        service_bonus = 10
    elif any(k in service_text for k in ["iot", "hardware", "report"]):
        service_bonus = 6
    urgency_component = 12 if priority_text == "high" else (7 if priority_text == "medium" else 3)
    conversion_score = _clamp_score(40 + message_component + service_bonus + urgency_component)

    total = _clamp_score((value_score * 0.40) + (urgency_score * 0.30) + (conversion_score * 0.30))
    if total >= 80:
        tier = "A"
    elif total >= 65:
        tier = "B"
    elif total >= 45:
        tier = "C"
    else:
        tier = "D"

    req.lead_score_value = value_score
    req.lead_score_urgency = urgency_score
    req.lead_score_conversion = conversion_score
    req.lead_score_total = total
    req.lead_tier = tier
    req.lead_last_scored_at = datetime.utcnow()


def _apply_stale_followup_policy(rows):
    now = datetime.utcnow()
    stale_count = 0
    escalated_count = 0
    changed = False

    for row in rows:
        status = (row.status or "").strip().lower()
        if status == "done":
            if row.stale_flag:
                row.stale_flag = False
                changed = True
            continue

        priority = (row.priority or "Medium").strip().lower()
        threshold = 4
        if priority == "high":
            threshold = 2
        elif priority == "low":
            threshold = 7

        age_days = 0
        if row.created_at:
            age_days = max((now - row.created_at).days, 0)

        is_stale = age_days >= threshold
        if row.stale_flag != is_stale:
            row.stale_flag = is_stale
            changed = True

        if not is_stale:
            continue

        stale_count += 1
        next_follow = row.next_followup_at
        followup_due = (not next_follow) or (next_follow <= now)
        recent_followup = row.last_followup_at and (now - row.last_followup_at) < timedelta(hours=20)
        can_escalate = (row.escalation_level or 0) < 3

        if followup_due and can_escalate and not recent_followup:
            row.escalation_level = int(row.escalation_level or 0) + 1
            row.last_followup_at = now
            row.next_followup_at = now + timedelta(days=1)
            row.is_new_update = True

            if priority == "low":
                row.priority = "Medium"
            elif priority == "medium":
                row.priority = "High"

            _score_project_request(row)
            escalated_count += 1
            changed = True
        elif not row.next_followup_at:
            row.next_followup_at = now + timedelta(days=1)
            changed = True

    return {
        "stale_count": stale_count,
        "escalated_count": escalated_count,
        "changed": changed,
    }


def _extract_client_ip():
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = (request.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip
    return (request.remote_addr or "").strip()


def _resolve_visitor_id(payload):
    payload = payload if isinstance(payload, dict) else {}
    candidate = str(payload.get("visitor_id") or request.cookies.get("ux_vid") or "").strip()
    if candidate and re.match(r"^[A-Za-z0-9._-]{8,80}$", candidate):
        return candidate
    return os.urandom(12).hex()


def _record_traffic_event(event_type, payload):
    payload = payload if isinstance(payload, dict) else {}
    visitor_id = _resolve_visitor_id(payload)
    current = current_user()

    raw_path = str(payload.get("page_path") or request.path or "/").strip()
    page_path = raw_path if raw_path.startswith("/") else f"/{raw_path}"
    page_path = page_path[:260]

    scroll_percent = payload.get("scroll_percent")
    if scroll_percent is not None:
        try:
            scroll_percent = max(0, min(100, int(scroll_percent)))
        except (TypeError, ValueError):
            scroll_percent = None

    client_ip = _extract_client_ip()
    event = SiteTrafficEvent(
        visitor_id=visitor_id,
        user_id=getattr(current, "id", None),
        user_email=(getattr(current, "email", "") or "").strip().lower() or None,
        event_type=event_type,
        page_path=page_path,
        scroll_percent=scroll_percent,
        referrer=(str(payload.get("referrer") or request.referrer or "").strip()[:260] or None),
        ip_address=client_ip[:64] if client_ip else None,
        user_agent=(request.user_agent.string or "")[:255] or None,
    )

    db.session.add(event)
    db.session.commit()
    return visitor_id


def _traffic_bucket_for_path(page_path):
    path = (page_path or "").strip().lower()
    if path in {"/", ""}:
        return "Home"
    if path.startswith("/login") or path.startswith("/register"):
        return "Login"
    if path.startswith("/dashboard"):
        return "Dashboard"
    return "Other"


def _resolve_ab_variant(visitor_id, test_key, allocation_b):
    safe_vid = str(visitor_id or "").strip() or os.urandom(8).hex()
    safe_key = str(test_key or "").strip()
    joined = f"{safe_vid}:{safe_key}".encode("utf-8")
    bucket = int(hashlib.sha256(joined).hexdigest()[:8], 16) % 100
    return "B" if bucket < max(0, min(100, int(allocation_b or 0))) else "A"


def _normalize_origin(origin):
    return (origin or "").strip().rstrip("/")


def _origin_host(origin):
    normalized = _normalize_origin(origin)
    if not normalized:
        return ""
    parsed = urllib.parse.urlsplit(normalized)
    host = (parsed.netloc or parsed.path or "").strip().lower()
    return host


def _is_google_client_id_configured():
    client_id = (app.config.get("GOOGLE_CLIENT_ID") or "").strip()
    if not client_id:
        return False
    if "your_google_client_id_here" in client_id:
        return False
    return client_id.endswith(".apps.googleusercontent.com")


def get_google_origin_settings(current_origin):
    raw = (os.getenv("GOOGLE_ALLOWED_ORIGINS") or "").strip()
    configured = {
        _normalize_origin(x) for x in raw.split(",") if _normalize_origin(x)
    }
    allowed_origins = configured if configured else DEFAULT_GOOGLE_ALLOWED_ORIGINS
    normalized_current = _normalize_origin(current_origin)
    allowed_hosts = {_origin_host(x) for x in allowed_origins if _origin_host(x)}
    current_host = _origin_host(normalized_current)
    # Allow same-host origins even when proxy transport rewriting changes scheme.
    origin_allowed = normalized_current in allowed_origins or (current_host and current_host in allowed_hosts)
    client_id_ok = _is_google_client_id_configured()
    enabled = bool(origin_allowed and client_id_ok)
    if not client_id_ok:
        reason = "Google OAuth client is not configured on server."
    elif not origin_allowed:
        reason = "Current host is not in GOOGLE_ALLOWED_ORIGINS."
    else:
        reason = ""
    return {
        "enabled": enabled,
        "reason": reason,
        "current_origin": normalized_current,
        "allowed_origins": sorted(allowed_origins),
    }


def current_user():
    uid = session.get('user_id')
    return db.session.get(User, uid) if uid else None


@app.before_request
def enforce_active_user_session():
    if request.endpoint == 'static' or (request.path or '').startswith('/static/'):
        return None

    uid = session.get('user_id')
    if not uid:
        return None

    try:
        user = db.session.get(User, uid)
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Session precheck failed while loading user.")
        session.clear()
        return redirect(url_for('login'))
    if not user or not user.is_active:
        session.clear()
        if (request.path or '').startswith(('/api/', '/admin/api/')):
            return jsonify({"success": False, "message": "Authentication required."}), 401
        return redirect(url_for('login'))

    token = str(session.get('session_token') or '').strip()
    if not token:
        _register_user_session(user)
        return None

    try:
        row = UserSession.query.filter_by(user_id=user.id, session_token=token).first()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Session precheck failed while loading device session.")
        session.clear()
        return redirect(url_for('login'))
    if not row or not row.is_active:
        session.clear()
        if (request.path or '').startswith(('/api/', '/admin/api/')):
            return jsonify({"success": False, "message": "Session ended. Please sign in again."}), 401
        flash('Your session was ended from Device Manager. Please sign in again.', 'warning')
        return redirect(url_for('login'))

    now = datetime.utcnow()
    if not row.last_seen or (now - row.last_seen) > timedelta(seconds=60):
        row.last_seen = now
        db.session.commit()
    return None


def is_super_admin(user_obj=None):
    user_obj = user_obj or current_user()
    if not user_obj:
        return False
    return normalize_email(user_obj.email) == normalize_email(SUPERADMIN_EMAIL) or normalize_admin_scope(getattr(user_obj, 'admin_scope', 'ops')) == 'superadmin'


def get_finance_admin_slots():
    """Returns two finance admin slots used for receivable/payable ownership."""
    finance_admins = User.query.filter(
        db.func.lower(User.role) == 'admin',
        db.func.lower(User.admin_scope) == 'finance',
        User.is_active.is_(True),
    ).order_by(User.created_at.asc(), User.email.asc()).all()

    emails = [normalize_email(u.email) for u in finance_admins if normalize_email(u.email)]
    slot_1 = emails[0] if len(emails) >= 1 else ""
    slot_2 = emails[1] if len(emails) >= 2 else slot_1

    return {
        "receivable": slot_1,
        "payable": slot_2,
        "slot_1": slot_1,
        "slot_2": slot_2,
        "all": emails,
    }


def assign_finance_admin_email(entry_type):
    slots = get_finance_admin_slots()
    normalized = normalize_finance_entry_type(entry_type)
    return normalize_email(slots.get(normalized, ""))


ADMIN_SCOPE_CAPABILITIES = {
    "superadmin": {"lead_manage", "analytics_view", "task_ops", "export_data", "admin_control", "finance_ops"},
    "ops": {"lead_manage", "analytics_view", "task_ops", "export_data"},
    "finance": {"analytics_view", "export_data", "finance_ops"},
    "support": {"lead_manage", "analytics_view"},
}


def has_admin_capability(capability, user_obj=None):
    user_obj = user_obj or current_user()
    if not user_obj or normalize_role(getattr(user_obj, 'role', 'user')) != 'admin':
        return False
    if is_super_admin(user_obj):
        return True
    scope = normalize_admin_scope(getattr(user_obj, 'admin_scope', 'ops'))
    return capability in ADMIN_SCOPE_CAPABILITIES.get(scope, set())


def admin_capability_required(capability):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            actor = current_user()
            if not has_admin_capability(capability, actor):
                if wants_json_response() or request.path.startswith(('/api/', '/admin/api/')):
                    return jsonify({"success": False, "message": "Insufficient permission for this action."}), 403
                flash("Insufficient permission for this action.", "danger")
                return redirect(url_for('admin_panel'))
            return fn(*args, **kwargs)
        return decorated
    return wrapper


def log_superadmin_action(action, target="", details="", actor=None):
    actor = actor or current_user()
    if not actor or normalize_role(getattr(actor, "role", "user")) != "admin":
        return
    db.session.add(AdminAuditLog(
        actor_email=(actor.email or "").strip().lower(),
        action=(action or "").strip()[:80],
        target=(target or "").strip()[:180],
        details=(details or "").strip()[:2000],
    ))


def _queue_approval_ticket(action_key, payload, actor, reason=""):
    actor_email = (getattr(actor, 'email', '') or '').strip().lower()
    actor_scope = normalize_admin_scope(getattr(actor, 'admin_scope', 'ops'))
    ticket = ApprovalTicket(
        action_key=(action_key or '').strip()[:60],
        payload_json=json.dumps(payload or {}, ensure_ascii=True),
        requested_by_email=actor_email,
        requested_by_scope=actor_scope,
        reason=(reason or '').strip()[:240] or None,
        status='pending',
    )
    db.session.add(ticket)
    log_superadmin_action(
        action="APPROVAL_QUEUED",
        target=f"{(action_key or '').strip()[:60]}",
        details=(reason or "")[:300],
        actor=actor,
    )
    db.session.commit()
    return ticket


def _apply_project_update_values(req, status, priority, value, message):
    req.status = status
    req.priority = priority
    req.value = int(value or 0)
    # The customer's original message is never editable by admins.
    req.is_new_update = True

    if (req.status or '').strip().lower() == 'done':
        req.stale_flag = False
        req.next_followup_at = None
    _score_project_request(req)


def _apply_bulk_action_rows(rows, action):
    if action == "mark_done":
        for row in rows:
            row.status = "Done"
            row.is_new_update = True
            _score_project_request(row)
    elif action == "mark_progress":
        for row in rows:
            row.status = "In Progress"
            row.is_new_update = True
            _score_project_request(row)
    elif action == "priority_high":
        for row in rows:
            row.priority = "High"
            row.is_new_update = True
            _score_project_request(row)
    elif action == "priority_medium":
        for row in rows:
            row.priority = "Medium"
            row.is_new_update = True
            _score_project_request(row)
    elif action == "priority_low":
        for row in rows:
            row.priority = "Low"
            row.is_new_update = True
            _score_project_request(row)
    elif action == "delete":
        for row in rows:
            db.session.delete(row)
    else:
        raise ValueError("Unsupported bulk action")


def _execute_approval_ticket(ticket):
    payload = json.loads(ticket.payload_json or "{}")
    action_key = (ticket.action_key or '').strip().lower()

    if action_key == 'project_update':
        req_id = int(payload.get('req_id'))
        req = ProjectRequest.query.get(req_id)
        if not req:
            raise ValueError(f"Inquiry #{req_id} no longer exists.")
        _apply_project_update_values(
            req,
            str(payload.get('status') or '').strip(),
            str(payload.get('priority') or '').strip(),
            int(payload.get('value') or 0),
            payload.get('message'),
        )
        return f"Project #{req.id:04d} updated."

    if action_key == 'project_delete':
        req_id = int(payload.get('req_id'))
        req = ProjectRequest.query.get(req_id)
        if not req:
            raise ValueError(f"Inquiry #{req_id} already removed.")
        db.session.delete(req)
        return f"Inquiry #{req_id:04d} deleted."

    if action_key == 'bulk_action':
        action = str(payload.get('action') or '').strip().lower()
        ids = payload.get('ids') or []
        parsed_ids = [int(x) for x in ids]
        rows = ProjectRequest.query.filter(ProjectRequest.id.in_(parsed_ids)).all()
        if not rows:
            raise ValueError("No matching inquiries for bulk action.")
        _apply_bulk_action_rows(rows, action)
        return f"Bulk action '{action}' applied to {len(rows)} inquiries."

    raise ValueError("Unsupported approval action.")


OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5


def _safe_commit():
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        app.logger.exception("Database commit failed in OTP flow")
        return False


def _list_db_backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    items = []
    for name in os.listdir(BACKUP_DIR):
        safe = _safe_backup_filename(name)
        if not safe:
            continue
        full_path = os.path.join(BACKUP_DIR, safe)
        if not os.path.isfile(full_path):
            continue
        stat = os.stat(full_path)
        items.append({
            "name": safe,
            "size": int(stat.st_size or 0),
            "updated_at": datetime.utcfromtimestamp(stat.st_mtime),
        })
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return items


def _cleanup_expired_otps():
    now = datetime.utcnow()
    PasswordResetOTP.query.filter(PasswordResetOTP.expires_at <= now).delete(synchronize_session=False)
    _safe_commit()


def _generate_otp_code():
    return f"{secrets.randbelow(1000000):06d}"


def _save_otp_for_email(email, otp_code):
    PasswordResetOTP.query.filter_by(email=email).delete(synchronize_session=False)
    row = PasswordResetOTP(
        email=email,
        otp=generate_password_hash(otp_code, method=PASSWORD_HASH_METHOD),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
        attempts_left=OTP_MAX_ATTEMPTS,
        is_verified=False,
    )
    db.session.add(row)
    return _safe_commit()


def _env_flag(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        raw = "true" if default else "false"
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _smtp_send_message(msg):
    smtp_host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    smtp_port_raw = (os.getenv("SMTP_PORT") or "587").strip()
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_pass = (os.getenv("SMTP_PASS") or "").strip()
    smtp_use_tls = _env_flag("SMTP_USE_TLS", default=True)
    smtp_use_ssl = _env_flag("SMTP_USE_SSL", default=False)

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError as exc:
        raise RuntimeError("SMTP_PORT must be a valid integer") from exc

    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP_USER/SMTP_PASS are not configured")

    # Port 465 typically requires implicit SSL even when TLS flag is set.
    use_ssl = smtp_use_ssl or smtp_port == 465

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20, context=ssl.create_default_context()) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.ehlo()
        if smtp_use_tls:
            if not server.has_extn("starttls"):
                raise RuntimeError("SMTP server does not support STARTTLS. Set SMTP_USE_TLS=False or SMTP_USE_SSL=True.")
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def _send_welcome_email(email, name):
    """Send a welcoming email to a newly registered customer."""
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or smtp_user).strip()
    if not smtp_from:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be configured")
    queue_welcome_email(
        recipient=email,
        name=name,
        sender=smtp_from,
        locale=os.getenv("MAIL_LOCALE", "en"),
        app_url=resolved_app_url(),
    )


def _send_task_assigned_email(email, title, details, assigned_by):
    """Notify an admin that a task was assigned to them."""
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or smtp_user).strip()
    if not smtp_from:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be configured")
    queue_assigned_email(
        recipient=email,
        title=title,
        details=details,
        assigned_by=assigned_by,
        sender=smtp_from,
        locale=os.getenv("MAIL_LOCALE", "en"),
        app_url=resolved_app_url(),
    )


def _otp_matches(stored_otp_value, otp_code):
    """Verify OTP against hashed storage with compatibility for legacy plain-text rows."""
    try:
        return check_password_hash(stored_otp_value, otp_code)
    except (ValueError, TypeError):
        return str(stored_otp_value or "") == str(otp_code or "")


def _get_active_otp(email):
    now = datetime.utcnow()
    return PasswordResetOTP.query.filter(
        PasswordResetOTP.email == email,
        PasswordResetOTP.expires_at > now,
    ).order_by(PasswordResetOTP.created_at.desc()).first()


def _send_password_reset_otp(email, otp_code):
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or smtp_user).strip()
    if not smtp_from:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be configured")

    msg = EmailMessage()
    msg["Subject"] = "Unitary X Password Reset OTP"
    msg["From"] = smtp_from
    msg["To"] = email
    msg.set_content(
        "Your One-Time Password (OTP) for password reset is: "
        f"{otp_code}\n\n"
        f"This OTP expires in {OTP_TTL_MINUTES} minutes.\n"
        "If you did not request this, please ignore this email."
    )

    _smtp_send_message(msg)


# ─── Seed Data ────────────────────────────────────────────────────────────────

def seed_data():
    # Default admin from .env
    admin_email = os.getenv("ADMIN_EMAIL", "admin@unitaryx.com")
    admin_pass = os.getenv("ADMIN_PASS") or ("Admin@123" if _DEBUG_MODE else os.urandom(18).hex())
    
    if not User.query.filter_by(email=admin_email).first():
        admin = User(name='Unitary X Admin',
                     email=admin_email, role='admin', admin_scope='ops')
        admin.set_password(admin_pass)
        db.session.add(admin)

    # Ensure the initial superadmin comes from environment variables.
    super_admin = User.query.filter(db.func.lower(User.email) == SUPERADMIN_EMAIL).first()
    if not super_admin:
        super_admin = User(name=SUPERADMIN_NAME, email=SUPERADMIN_EMAIL, role='admin', admin_scope='superadmin')
        super_admin.set_password(SUPERADMIN_PASSWORD)
        db.session.add(super_admin)
    super_admin.role = 'admin'
    super_admin.admin_scope = 'superadmin'
    super_admin.is_active = True

    if Project.query.count() == 0:
        db.session.add_all([
            Project(title="E-Commerce Platform",
                    description="Full-stack shopping platform with product management, cart, payment & admin panel built with Flask and MySQL.",
                    category="web", tags="Web,Flask,MySQL", price="Rs.1,500",
                    duration="7 days", rating=5.0, icon="fas fa-shopping-cart",
                    bg_class="bg-1", featured=True),
            Project(title="Face Recognition System",
                    description="Real-time face detection and recognition attendance system using OpenCV and deep learning.",
                    category="ai", tags="AI,Python,OpenCV", price="Rs.2,200",
                    duration="10 days", rating=5.0, icon="fas fa-eye",
                    bg_class="bg-2", featured=True),
            Project(title="Smart Home Automation",
                    description="Arduino + ESP8266 WiFi-controlled home automation system with mobile app interface.",
                    category="hardware", tags="Hardware,IoT,Arduino", price="Rs.3,500",
                    duration="14 days", rating=4.9, icon="fas fa-home",
                    bg_class="bg-3", featured=True),


            Project(title="Line Follower Robot",
                    description="Autonomous line-following robot with IR sensors and Bluetooth remote override.",
                    category="hardware", tags="Hardware,Arduino,Robotics", price="Rs.1,800",
                    duration="8 days", rating=4.8, icon="fas fa-robot", bg_class="bg-6"),
            Project(title="AI Water Management System",
                    description="Smart IoT-based water monitoring and leak detection system using AI algorithms for predictive maintenance.",
                    category="ai", tags="AI,IoT,Water Management", price="Rs.2,100",
                    duration="10 days", rating=5.0, icon="fas fa-tint", bg_class="bg-7", featured=True),
            Project(title="Smart Classroom Management System",
                    description="Integrated software and hardware platform for automated attendance, smart lighting, and classroom resource management.",
                    category="hardware", tags="Hardware,Software,IoT,Classroom", price="Rs.2,500",
                    duration="12 days", rating=4.9, icon="fas fa-chalkboard-teacher", bg_class="bg-8", featured=True),
            Project(title="Vision X - Smart Cap",
                    description="Custom-built wearable smart cap with integrated camera and haptic feedback sensors for real-time obstacle detection and navigation assistance.",
                    category="hardware", tags="Hardware,IoT,Wearable,Arduino", price="Rs.2,900",
                    duration="14 days", rating=5.0, icon="fas fa-low-vision", bg_class="bg-3", featured=True),
            Project(title="Newspaper Flux",
                    description="Automated digital newspaper aggregation and layout system that fetches, categorises, and presents real-time news content with a dynamic flux-based UI.",
                    category="software", tags="Software,Python,Automation,News", price="Rs.1,800",
                    duration="7 days", rating=4.9, icon="fas fa-newspaper", bg_class="bg-2", featured=True),
        ])

    if Testimonial.query.count() == 0:
        db.session.add_all([
            Testimonial(name="Rahul Kumar", role="B.Tech CSE, Anna University",
                        review="Got my final year project (face recognition attendance system) done in just 10 days! The code was clean, well-commented, and I even got a PPT. Scored distinction!",
                        rating=5, avatar="R", av_class="av-1"),
            Testimonial(name="Priya Sharma", role="Diploma in ECE, PSG Polytechnic",
                        review="My Arduino smart home project was built with actual working hardware and proper circuit diagrams. The instructor was super impressed!",
                        rating=5, avatar="P", av_class="av-2"),
            Testimonial(name="Arun Venkatesan", role="MCA Student, Bharathiar University",
                        review="I was struggling with my DBMS mini-project. Got it done in 3 days with MySQL, Python, and a great UI. Total lifesaver for my exams!",
                        rating=5, avatar="A", av_class="av-3"),
            Testimonial(name="Sneha Rajan", role="12th Standard, KV School Chennai",
                        review="School science expo winning project! The line-follower robot was amazing — real working model, poster, and everything!",
                        rating=5, avatar="S", av_class="av-4"),
        ])

    if ABTestConfig.query.count() == 0:
        db.session.add_all([
            ABTestConfig(
                test_key="hero_headline",
                label="Hero Headline",
                enabled=True,
                allocation_b=50,
                variant_a="From Idea to Impact: Premium Projects Built for Results.",
                variant_b="From Idea to Impact: Premium Projects Built for Results.",
            ),
            ABTestConfig(
                test_key="hero_primary_cta",
                label="Hero Primary CTA",
                enabled=True,
                allocation_b=50,
                variant_a="Start Your Project",
                variant_b="Book a Free Strategy Call",
            ),
            ABTestConfig(
                test_key="hire_cta",
                label="Navigation Hire CTA",
                enabled=True,
                allocation_b=50,
                variant_a="Hire Us",
                variant_b="Get Proposal",
            ),
        ])

    db.session.commit()


def _ensure_schema_columns():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())

    table_patch_map = {
        "users": [
            ("admin_scope", "VARCHAR(20) DEFAULT 'ops'"),
        ],
        "user_sessions": [
            ("is_active", "BOOLEAN DEFAULT TRUE"),
            ("last_seen", "TIMESTAMP"),
        ],
        "ab_test_configs": [
            ("enabled", "BOOLEAN DEFAULT TRUE"),
            ("allocation_b", "INTEGER DEFAULT 50"),
            ("variant_a", "VARCHAR(300) DEFAULT ''"),
            ("variant_b", "VARCHAR(300) DEFAULT ''"),
            ("updated_at", "TIMESTAMP"),
        ],
        "project_requests": [
            ("lead_score_value", "INTEGER DEFAULT 0"),
            ("lead_score_urgency", "INTEGER DEFAULT 0"),
            ("lead_score_conversion", "INTEGER DEFAULT 0"),
            ("lead_score_total", "INTEGER DEFAULT 0"),
            ("lead_tier", "VARCHAR(20) DEFAULT 'C'"),
            ("lead_last_scored_at", "TIMESTAMP"),
            ("stale_flag", "BOOLEAN DEFAULT FALSE"),
            ("escalation_level", "INTEGER DEFAULT 0"),
            ("last_followup_at", "TIMESTAMP"),
            ("next_followup_at", "TIMESTAMP"),
        ],
        "projects": [
            ("display_order", "INTEGER DEFAULT 0"),
            ("photo_url", "VARCHAR(300)"),
            ("problem", "TEXT"),
            ("approach", "TEXT"),
            ("outcome", "TEXT"),
            ("stack", "VARCHAR(300)"),
        ],
    }

    for table_name, columns in table_patch_map.items():
        if table_name not in table_names:
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col_name, col_ddl in columns:
            if col_name in existing:
                continue
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_ddl}"))
            app.logger.info("Added missing column %s.%s", table_name, col_name)

    db.session.commit()


# ─── Public Routes ────────────────────────────────────────────────────────────

# Built by `npm run build` in frontend/app — see Dockerfile for the build stage
# that produces this in the deployed image.
DIST_DIR = os.path.join(PROJECT_ROOT, "frontend", "app", "dist")

# The only paths the React Router <Routes> in App.jsx actually renders.
# Anything else must 404 rather than silently serve the homepage — a bare
# catch-all that returns 200 for every path is a classic SPA "soft 404" that
# creates unbounded duplicate-content URLs (all identical to "/") and tanks
# indexing (this is what produced the Search Console duplicate-canonical and
# crawled-not-indexed flags: /about, /services, /projects, /contact, /home,
# /index.html etc. were all serving 200 copies of the homepage).
KNOWN_SPA_ROUTES = {"", "dashboard", "admin/studio"}


@app.before_request
def redirect_www_to_apex():
    """unitaryx.org and www.unitaryx.org were both serving identical content
    with no redirect between them — Search Console flagged this as a
    duplicate with a canonical Google chose itself rather than the one our
    <link rel="canonical"> specifies. Every canonical/OG/sitemap URL in this
    project assumes the bare apex domain, so www must always redirect there."""
    host = (request.host or "").lower()
    if host.startswith("www."):
        parts = urllib.parse.urlsplit(request.url)
        new_url = urllib.parse.urlunsplit((parts.scheme, host[4:], parts.path, parts.query, parts.fragment))
        return redirect(new_url, code=301)


SITE_URL = (os.getenv("SITE_URL") or "https://unitaryx.org").rstrip("/")

# Tags that a per-project page must replace rather than duplicate.
_HEAD_TAG_RE = re.compile(
    r"<title>.*?</title>"
    r'|<link\b[^>]*\brel="canonical"[^>]*>'
    r'|<meta\b[^>]*(?:\bname="(?:description|twitter:[a-z:]+)"|\bproperty="og:[a-z:]+")[^>]*>'
    r'|<script\s+type="application/ld\+json">.*?</script>',
    re.DOTALL,
)


def _project_head(project):
    """Server-rendered <head> tags for a case-study page. Social crawlers do
    not execute JS, so these must be in the raw HTML response."""
    import html as _html

    def e(value):
        return _html.escape(str(value or ""), quote=True)

    url = f"{SITE_URL}/projects/{project.slug}"
    title = f"{project.title} - {project.category.title()} Project | Unitary X"
    desc = re.sub(r"\s+", " ", project.problem or project.description or "").strip()
    if len(desc) > 155:
        desc = desc[:152].rsplit(" ", 1)[0] + "..."
    image = project.photo_url or "/og-image.jpg"
    if image.startswith("/"):
        image = SITE_URL + image
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CreativeWork",
                "name": project.title,
                "description": project.description,
                "abstract": project.problem or project.description,
                "url": url,
                "image": image,
                "genre": project.category,
                "keywords": ", ".join(
                    k.strip() for k in f"{project.stack or ''},{project.tags or ''}".split(",") if k.strip()
                ),
                "creator": {"@type": "Organization", "name": "Unitary X", "url": SITE_URL + "/"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Unitary X", "item": SITE_URL + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Projects", "item": SITE_URL + "/#projects"},
                    {"@type": "ListItem", "position": 3, "name": project.title, "item": url},
                ],
            },
        ],
    }
    ld_json = json.dumps(ld).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    lines = [
        f"<title>{e(title)}</title>",
        f'<meta name="description" content="{e(desc)}" />',
        f'<link rel="canonical" href="{e(url)}" />',
        '<meta property="og:type" content="article" />',
        f'<meta property="og:url" content="{e(url)}" />',
        '<meta property="og:site_name" content="Unitary X" />',
        f'<meta property="og:title" content="{e(title)}" />',
        f'<meta property="og:description" content="{e(desc)}" />',
        f'<meta property="og:image" content="{e(image)}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{e(title)}" />',
        f'<meta name="twitter:description" content="{e(desc)}" />',
        f'<meta name="twitter:image" content="{e(image)}" />',
        f'<script type="application/ld+json">{ld_json}</script>',
    ]
    return "\n".join(lines) + "\n"


@app.route("/projects/<slug>")
def project_page(slug):
    """Shareable case-study page. Unknown ids get a real 404; a stale or
    mistyped slug 301s to the canonical one so only one URL is indexable."""
    m = re.fullmatch(r"(?:.*-)?(\d+)", slug)
    project = db.session.get(Project, int(m.group(1))) if m else None
    if not project:
        return send_from_directory(DIST_DIR, "index.html"), 404
    if slug != project.slug:
        return redirect(f"/projects/{project.slug}", code=301)
    with open(os.path.join(DIST_DIR, "index.html"), encoding="utf-8") as fh:
        shell = fh.read()
    shell = _HEAD_TAG_RE.sub("", shell)
    shell = shell.replace("</head>", _project_head(project) + "</head>", 1)
    resp = make_response(shell)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


STATIC_PAGES = {
    "/privacy": (
        "Privacy notice | Unitary X",
        "What personal data Unitary X collects through its website, why, who it is shared with, "
        "and how to ask for access or deletion.",
    ),
    "/terms": (
        "Terms | Unitary X",
        "Terms for Unitary X hosting and project work: what the hosting plans cover, add-ons, "
        "payment and what is included with a project.",
    ),
}


def _static_page_response(path):
    """SPA shell with its own title/description/canonical/OG tags, for simple
    pages whose canonical must not point at the homepage."""
    import html as _html

    title, description = STATIC_PAGES[path]
    url = f"{SITE_URL}{path}"
    e = lambda v: _html.escape(v, quote=True)
    head = (
        f"<title>{e(title)}</title>\n"
        f'<meta name="description" content="{e(description)}" />\n'
        f'<link rel="canonical" href="{e(url)}" />\n'
        '<meta property="og:type" content="website" />\n'
        f'<meta property="og:url" content="{e(url)}" />\n'
        '<meta property="og:site_name" content="Unitary X" />\n'
        f'<meta property="og:title" content="{e(title)}" />\n'
        f'<meta property="og:description" content="{e(description)}" />\n'
        f'<meta property="og:image" content="{SITE_URL}/og-image.jpg" />\n'
        '<meta name="twitter:card" content="summary_large_image" />\n'
        f'<meta name="twitter:title" content="{e(title)}" />\n'
        f'<meta name="twitter:description" content="{e(description)}" />\n'
        f'<meta name="twitter:image" content="{SITE_URL}/og-image.jpg" />\n'
    )
    with open(os.path.join(DIST_DIR, "index.html"), encoding="utf-8") as fh:
        shell = fh.read()
    shell = _HEAD_TAG_RE.sub("", shell).replace("</head>", head + "</head>", 1)
    resp = make_response(shell)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@app.route("/privacy")
def privacy_page():
    return _static_page_response("/privacy")


@app.route("/terms")
def terms_page():
    return _static_page_response("/terms")


@app.route("/sitemap.xml")
def sitemap_xml():
    import html as _html

    projects = Project.query.order_by(Project.display_order.asc(), Project.id.asc()).all()
    urls = [(f"{SITE_URL}/", "weekly", "1.0"), (f"{SITE_URL}/privacy", "yearly", "0.3"), (f"{SITE_URL}/terms", "yearly", "0.3")] + [
        (f"{SITE_URL}/projects/{p.slug}", "monthly", "0.7" if p.has_case_study else "0.4")
        for p in projects
    ]
    body = "".join(
        f"  <url>\n    <loc>{_html.escape(u)}</loc>\n"
        f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>\n"
        for u, freq, prio in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n"
    )
    return app.response_class(xml, mimetype="application/xml")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path):
    """Serves the built React SPA for known client-side routes and static
    files copied from frontend/app/public/ (robots.txt, sitemap.xml,
    favicons, og-image.jpg) at the paths Vite places them. Any other path
    gets a real 404 instead of a soft-404 copy of the homepage. Kept as
    endpoint 'index' since other routes still redirect via
    url_for('index', _anchor=...)."""
    if path.startswith(("api/", "static/")):
        abort(404)
    if path == "index.html" or path.endswith("/index.html"):
        # /index.html is a byte-identical duplicate of "/" — redirect rather
        # than serve it twice under two URLs.
        return redirect("/" + path[: -len("index.html")], code=301)
    candidate = safe_join(DIST_DIR, path) if path else None
    if candidate and os.path.isfile(candidate):
        return send_from_directory(DIST_DIR, path)
    if path.rstrip("/") in KNOWN_SPA_ROUTES:
        return send_from_directory(DIST_DIR, "index.html")
    return send_from_directory(DIST_DIR, "index.html"), 404


# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("20 per minute", methods=["POST"])
def login():
    if request.method == "GET" and 'user_id' in session:
        return redirect(url_for('admin_panel') if session.get('role') == 'admin'
                        else url_for('user_dashboard'))

    tab   = request.args.get('tab', 'user')  # 'user' or 'admin'
    error = None
    origin_settings = get_google_origin_settings(f"{request.scheme}://{request.host}")

    if request.method == "POST":
        data = request_payload()
        login_type = str(data.get('login_type', 'user')).strip().lower() or 'user'
        email = normalize_email(data.get('email', ''))
        password = str(data.get('password', '')).strip()
        remember = parse_remember_flag(data.get('remember'))

        # Detection for AJAX/JSON clients
        is_ajax = wants_json_response()

        user = find_user_by_email(email)

        if not user or not user.check_password(password):
            error = "Email or password is incorrect."
            if is_ajax: return jsonify({"success": False, "error": error})
            tab   = login_type
        elif not user.is_active:
            error = "Your account has been deactivated. Contact admin."
            if is_ajax: return jsonify({"success": False, "error": error})
            tab   = login_type
        elif login_type == 'admin' and normalize_role(user.role) != 'admin' \
                and not is_admin_identity(email, existing_user=user):
            error = "You don't have admin privileges."
            if is_ajax: return jsonify({"success": False, "error": error})
            tab   = 'admin'
        else:
            normalized_role = normalize_role(user.role)
            if is_admin_identity(email, existing_user=user):
                normalized_role = 'admin'
            if normalize_email(user.email) == normalize_email(SUPERADMIN_EMAIL):
                normalized_role = 'admin'
            if user.role != normalized_role:
                user.role = normalized_role
            if normalized_role == 'admin':
                user.admin_scope = 'superadmin' if normalize_email(user.email) == normalize_email(SUPERADMIN_EMAIL) else normalize_admin_scope(user.admin_scope)
                db.session.commit()

            establish_session_for_user(user, remember=remember)

            target = url_for('admin_panel') if normalized_role == 'admin' else url_for('user_dashboard')
            
            if is_ajax:
                return jsonify({
                    "success": True,
                    "redirect": target,
                    "email": session.get('user_email', ''),
                    "role": session.get('role', 'user'),
                    "is_superadmin": bool(session.get('is_superadmin')),
                })
            
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(target)

    return render_template(
        "login.html",
        tab=tab,
        error=error,
        google_signin_enabled=origin_settings["enabled"],
        google_signin_reason=origin_settings["reason"],
        google_current_origin=origin_settings["current_origin"],
        google_allowed_origins=origin_settings["allowed_origins"],
    )


@app.route("/register", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("50 per hour", methods=["POST"])
def register():
    if 'user_id' in session:
        return redirect(url_for('user_dashboard'))

    error = None

    if request.method == "POST":
        data = request_payload()
        name = str(data.get('name', '')).strip()
        email = str(data.get('email', '')).strip().lower()
        password = str(data.get('password', '')).strip()
        confirm = str(data.get('confirm', data.get('confirm_password', ''))).strip()

        
        # Detection for AJAX/JSON clients
        is_ajax = wants_json_response()

        if not name or len(name) < 2:
            error = "Name must be at least 2 characters."
        elif not validate_email(email):
            error = "Please enter a valid email address."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif not any(c.isupper() for c in password):
            error = "Password must contain at least one uppercase letter (e.g. A, B, C...)."
        elif not any(c.isdigit() for c in password):
            error = "Password must contain at least one number (e.g. 1, 2, 3...)."
        elif not any(c in "@%#$!&*_-+=" for c in password):
            error = "Password must contain at least one symbol (e.g. @, %, #, $, !)."
        elif password != confirm:
            error = "Passwords do not match."
        elif User.query.filter_by(email=email).first() or is_admin_identity(email):
            error = "An account with this email already exists."
        
        if error:
            if is_ajax: return jsonify({"success": False, "error": error})
        else:
            user = User(name=name, email=email, role='user')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            try:
                _send_welcome_email(email, name)
            except Exception:
                app.logger.exception("Failed to send welcome email")
            establish_session_for_user(user, remember=False)

            target = url_for('user_dashboard')
            if is_ajax:
                return jsonify({"success": True, "redirect": target})
                
            flash(f"Account created! Welcome, {name}!", "success")
            return redirect(target)

    return render_template("login.html", tab='register', error=error)


@app.route("/send-otp", methods=["POST"])
@app.route("/forgot-password/send-otp", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per hour", methods=["POST"])
def forgot_password_send_otp():
    data = request.get_json(silent=True) or request.form
    email = str(data.get("email", "")).strip().lower()
    debug_mode = app.debug or (os.getenv("DEBUG", "False").strip().lower() == "true")

    if not validate_email(email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        # Avoid account enumeration by returning the same success message.
        payload = {
            "success": True,
            "message": "If this email is registered, an OTP has been sent."
        }
        if debug_mode:
            payload["debug"] = "DEV: Email not found in users table. OTP was not sent."
        return jsonify(payload)

    _cleanup_expired_otps()
    otp_code = _generate_otp_code()
    if not _save_otp_for_email(email, otp_code):
        return jsonify({"success": False, "error": "Server busy. Please try again."}), 503

    try:
        _send_password_reset_otp(email, otp_code)
    except smtplib.SMTPAuthenticationError:
        app.logger.exception("SMTP authentication failed while sending OTP")
        PasswordResetOTP.query.filter_by(email=email).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"success": False, "error": "Mail login failed. Set SMTP_PASS to a valid Gmail App Password."}), 500
    except Exception as exc:
        app.logger.exception("Failed to send OTP email")
        PasswordResetOTP.query.filter_by(email=email).delete(synchronize_session=False)
        _safe_commit()
        error_message = "Unable to send OTP email right now."
        if debug_mode:
            error_message = f"{error_message} ({exc})"
        return jsonify({"success": False, "error": error_message}), 500

    payload = {
        "success": True,
        "message": "OTP sent to your email.",
        "expires_in_seconds": OTP_TTL_MINUTES * 60,
    }
    if debug_mode:
        payload["debug"] = "DEV: Email exists. OTP generated and email dispatched via SMTP."
    return jsonify(payload)


@app.route("/reset-password", methods=["POST"])
@app.route("/forgot-password/reset", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per hour", methods=["POST"])
def forgot_password_reset():
    data = request.get_json(silent=True) or request.form
    email = str(data.get("email", "")).strip().lower()
    otp_code = str(data.get("otp", "")).strip()
    new_password = str(data.get("new_password") or data.get("newPassword") or "").strip()

    if not validate_email(email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400
    policy_error = _password_policy_error(new_password)
    if policy_error:
        return jsonify({"success": False, "error": policy_error}), 400

    _cleanup_expired_otps()
    payload = _get_active_otp(email)
    if not payload:
        return jsonify({"success": False, "error": "OTP expired or not found."}), 400

    if not _otp_matches(payload.otp, otp_code):
        payload.attempts_left = max(int(payload.attempts_left or OTP_MAX_ATTEMPTS) - 1, 0)
        if payload.attempts_left <= 0:
            db.session.delete(payload)
            if not _safe_commit():
                return jsonify({"success": False, "error": "Server busy. Please try again."}), 503
            return jsonify({"success": False, "error": "Too many invalid attempts. Request a new OTP."}), 400
        if not _safe_commit():
            return jsonify({"success": False, "error": "Server busy. Please try again."}), 503
        return jsonify({"success": False, "error": "Invalid OTP."}), 400

    if not payload.is_verified:
        return jsonify({"success": False, "error": "Verify OTP before resetting password."}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        db.session.delete(payload)
        if not _safe_commit():
            return jsonify({"success": False, "error": "Server busy. Please try again."}), 503
        return jsonify({"success": False, "error": "Account not found."}), 404

    user.set_password(new_password)
    if normalize_role(user.role) == 'admin':
        sync_admin_vault_to_latest_password(user, new_password)
    # A password reset signs the account out everywhere.
    UserSession.query.filter_by(user_id=user.id, is_active=True).update({"is_active": False}, synchronize_session=False)
    db.session.delete(payload)
    if not _safe_commit():
        return jsonify({"success": False, "error": "Server busy. Please try again."}), 503

    return jsonify({"success": True, "message": "Password reset successful. Please sign in."})


@app.route("/verify-otp", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per hour", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or request.form
    email = str(data.get("email", "")).strip().lower()
    otp_code = str(data.get("otp", "")).strip()

    if not validate_email(email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400

    _cleanup_expired_otps()
    payload = _get_active_otp(email)
    if not payload:
        return jsonify({"success": False, "error": "OTP expired or not found."}), 400

    if not _otp_matches(payload.otp, otp_code):
        payload.attempts_left = max(int(payload.attempts_left or OTP_MAX_ATTEMPTS) - 1, 0)
        if payload.attempts_left <= 0:
            db.session.delete(payload)
            if not _safe_commit():
                return jsonify({"success": False, "error": "Server busy. Please try again."}), 503
            return jsonify({"success": False, "error": "Too many invalid attempts. Request a new OTP."}), 400
        if not _safe_commit():
            return jsonify({"success": False, "error": "Server busy. Please try again."}), 503
        return jsonify({"success": False, "error": "Invalid OTP."}), 400

    payload.is_verified = True
    if not _safe_commit():
        return jsonify({"success": False, "error": "Server busy. Please try again."}), 503

    return jsonify({"success": True, "message": "OTP verified."})


@app.route("/google-login", methods=["POST"])
@csrf.exempt
def google_login():
    token = request.json.get("credential") if request.is_json else request.form.get("credential")
    if not token:
        return jsonify({"success": False, "error": "Missing token"}), 400
        
    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), app.config['GOOGLE_CLIENT_ID'])
        if not idinfo.get("email_verified", False):
            return jsonify({"success": False, "error": "Google account email is not verified."}), 400

        email = normalize_email(idinfo.get('email', ''))
        if not email:
            return jsonify({"success": False, "error": "Google did not provide an email address."}), 400

        name = idinfo.get('name', email.split("@")[0])
        is_oauth_admin = is_admin_identity(email)
        
        user = find_user_by_email(email)
        if user and not user.is_active:
            return jsonify({"success": False, "error": "Your account has been deactivated. Contact admin."}), 403
        if not user:
            user = User(
                name=name,
                email=email,
                role='admin' if is_oauth_admin else 'user',
                admin_scope='superadmin' if email == normalize_email(SUPERADMIN_EMAIL) else ('ops' if is_oauth_admin else 'ops'),
            )
            user.set_password(os.urandom(24).hex())
            db.session.add(user)
            db.session.commit()
        else:
            normalized_role = normalize_role(user.role)

            if user.role != normalized_role:
                user.role = normalized_role

            if is_admin_identity(email, existing_user=user) and user.role != 'admin':
                user.role = 'admin'

            if normalize_role(user.role) == 'admin':
                user.admin_scope = 'superadmin' if email == normalize_email(SUPERADMIN_EMAIL) else normalize_admin_scope(user.admin_scope)

            if normalize_email(user.email) != email:
                user.email = email

            if name and user.name != name:
                user.name = name

            db.session.commit()
            
        establish_session_for_user(
            user,
            remember=True,
            profile_photo=idinfo.get('picture') or "",
            auth_provider="google",
        )
        
        # Use a safe role check for redirection target
        final_role = normalize_role(user.role)
        target = url_for('admin_panel') if final_role == 'admin' else url_for('user_dashboard')
        
        return jsonify({
            "success": True,
            "redirect": target,
            "email": session.get('user_email', ''),
            "role": session.get('role', 'user'),
            "is_superadmin": bool(session.get('is_superadmin')),
        })
        
    except Exception as e:
        app.logger.exception("Google login verification failed")
        if app.debug:
            return jsonify({"success": False, "error": f"Google token verification failed: {str(e)}"}), 400
        return jsonify({"success": False, "error": "Invalid token"}), 400


@app.route("/logout")
def logout():
    end_current_session()
    return redirect(url_for('login'))


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    end_current_session()
    return jsonify({"success": True, "message": "Logged out."})


@app.route("/api/auth/session", methods=["GET"])
@csrf.exempt
def api_auth_session():
    user = current_user()
    if not user:
        return jsonify({
            "authenticated": False,
            "user": None,
            "redirect": url_for("login"),
        })

    is_admin_role = normalize_role(user.role) == "admin"
    admin_scope = normalize_admin_scope(session.get("admin_scope") or getattr(user, "admin_scope", "ops")) if is_admin_role else ""
    is_superadmin_flag = bool(session.get("is_superadmin"))
    capabilities = (
        sorted(ADMIN_SCOPE_CAPABILITIES["superadmin"]) if is_superadmin_flag
        else sorted(ADMIN_SCOPE_CAPABILITIES.get(admin_scope, set())) if is_admin_role
        else []
    )

    return jsonify({
        "authenticated": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": normalize_email(user.email),
            "role": normalize_role(user.role),
            "is_superadmin": is_superadmin_flag,
            "admin_scope": admin_scope,
            "capabilities": capabilities,
            "profile_photo": (session.get("user_profile_photo") or "").strip(),
        },
    })


def _main_page_actions_manifest():
    # Main public site actions only (no admin/superadmin management endpoints).
    return [
        {"key": "auth.login", "method": "POST", "path": "/login", "auth": "public", "body": ["login_type", "email", "password", "remember"]},
        {"key": "auth.register", "method": "POST", "path": "/register", "auth": "public", "body": ["name", "email", "password", "confirm"]},
        {"key": "auth.google_login", "method": "POST", "path": "/google-login", "auth": "public", "body": ["credential"]},
        {"key": "auth.send_otp", "method": "POST", "path": "/forgot-password/send-otp", "auth": "public", "body": ["email"]},
        {"key": "auth.verify_otp", "method": "POST", "path": "/verify-otp", "auth": "public", "body": ["email", "otp"]},
        {"key": "auth.reset_password", "method": "POST", "path": "/forgot-password/reset", "auth": "public", "body": ["email", "otp", "new_password"]},
        {"key": "auth.session", "method": "GET", "path": "/api/auth/session", "auth": "public", "body": []},
        {"key": "auth.logout", "method": "POST", "path": "/api/auth/logout", "auth": "user", "body": []},
        {"key": "project.submit_inquiry", "method": "POST", "path": "/api/contact", "auth": "public", "body": ["name", "email", "phone", "service", "deadline", "message"]},
        {"key": "feedback.submit", "method": "POST", "path": "/feedback/submit", "auth": "user", "body": ["message", "rating"]},
        {"key": "projects.list", "method": "GET", "path": "/api/projects", "auth": "public", "body": []},
        {"key": "analytics.page_view", "method": "POST", "path": "/api/traffic/page-view", "auth": "public", "body": ["page", "title", "source"]},
        {"key": "analytics.scroll", "method": "POST", "path": "/api/traffic/scroll", "auth": "public", "body": ["page", "depth", "source"]},
    ]


@app.route("/api/frontend/actions", methods=["GET"])
@app.route("/api/frontend/actions/main-page", methods=["GET"])
@csrf.exempt
def api_frontend_actions():
    actions = _main_page_actions_manifest()

    return jsonify({
        "success": True,
        "scope": "main-page",
        "message": "Frontend action map for Unitary X main page",
        "actions": actions,
    })


# ─── User Dashboard ───────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def user_dashboard():
    # The customer dashboard is now a React route in the SPA. Keep @login_required
    # so unauthenticated visitors are redirected to /login (route stays private and
    # is disallowed in robots.txt). Data is loaded client-side via
    # GET /api/dashboard/requests.
    return send_from_directory(DIST_DIR, "index.html")


def _customer_request_dict(req, is_updated):
    """Customer-safe serialization of a ProjectRequest. Deliberately excludes
    internal_notes and every lead_score_* / lead_tier / escalation_level field
    (admin-only per CLAUDE.md §7.5)."""
    return {
        "id": req.id,
        "service": req.service,
        "message": req.message,
        "status": req.status,
        "priority": req.priority,
        "value": req.value or 0,
        "deadline": req.deadline,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "is_updated": is_updated,
    }


@app.route("/api/dashboard/requests")
@api_login_required
def api_dashboard_requests():
    user = current_user()
    normalized_email = (user.email or "").strip().lower()
    # Email matching is only trusted for Google sign-ins (verified email);
    # password accounts are unverified, so they see only requests linked by id.
    conditions = [ProjectRequest.user_id == user.id]
    if session.get("auth_provider") == "google":
        conditions.append(db.func.lower(ProjectRequest.email) == normalized_email)
    my_requests = ProjectRequest.query.filter(db.or_(*conditions)).order_by(ProjectRequest.created_at.desc()).all()

    active_updates = {r.id for r in my_requests if r.is_new_update}

    # One-shot "updates" semantics preserved from the old route: flag which rows
    # were newly updated this load, then clear the flags.
    if active_updates:
        for req in my_requests:
            if req.is_new_update:
                req.is_new_update = False
        db.session.commit()

    first_name = (user.name or "").strip().split(" ")[0] if user.name else ""
    return jsonify({
        "user": {"name": user.name, "first_name": first_name},
        "requests": [_customer_request_dict(r, r.id in active_updates) for r in my_requests],
    })


# ─── API — Contact Form ───────────────────────────────────────────────────────

CONTACT_SERVICES = {"web", "software", "hardware", "hosting"}
CONTACT_LIMITS = {"name": 100, "email": 150, "phone": 20, "deadline": 30, "message": 3000}


@app.route("/api/contact", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per hour", methods=["POST"])  # Prevent contact spam
def api_contact():
    """Project enquiry. Open to anonymous visitors (a login wall loses people);
    a signed-in user's request is additionally linked to their account so it
    shows on their dashboard."""
    data = request.get_json(silent=True) or request.form

    # Honeypot: real visitors never see or fill this field.
    if str(data.get("website", "")).strip():
        return jsonify({"success": True, "message": "Thanks. Your request has been received."}), 201

    name    = str(data.get("name",    "")).strip()
    email   = str(data.get("email",   "")).strip()
    phone   = str(data.get("phone",   "")).strip()
    service = str(data.get("service", "")).strip().lower()
    deadline= str(data.get("deadline","")).strip()
    message = str(data.get("message", "")).strip()

    errors = {}
    if not name:                             errors["name"]    = "Name is required."
    if not email or not validate_email(email): errors["email"] = "Valid email is required."
    if service not in CONTACT_SERVICES:      errors["service"] = "Please select a service."
    if not message or len(message) < 20:     errors["message"] = "Please describe your project (min 20 chars)."
    for field, value in (("name", name), ("email", email), ("phone", phone), ("deadline", deadline), ("message", message)):
        if len(value) > CONTACT_LIMITS[field] and field not in errors:
            errors[field] = f"Please keep this under {CONTACT_LIMITS[field]} characters."

    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    uid = session.get('user_id')
    req = ProjectRequest(user_id=uid, name=name, email=email, phone=phone,
                         service=service, deadline=deadline, message=message)
    _score_project_request(req)
    db.session.add(req)
    db.session.commit()

    def send_notification():
        try:
            smtp_user = (os.getenv("SMTP_USER") or "").strip()
            smtp_from = (os.getenv("SMTP_FROM") or smtp_user).strip()
            if not smtp_from:
                return
            msg = EmailMessage()
            safe_name = re.sub(r"\s+", " ", name)  # header values may not contain newlines
            msg["Subject"] = f"New Project Request: {service.capitalize()} from {safe_name}"
            msg["From"] = smtp_from
            msg["To"] = "xunitary@gmail.com"
            msg.set_content(
                f"New Project Inquiry Details:\n\n"
                f"Name: {name}\n"
                f"Email: {email}\n"
                f"Phone: {phone}\n"
                f"Service: {service}\n"
                f"Deadline: {deadline}\n"
                f"Account: {'signed in' if uid else 'not signed in'}\n\n"
                f"Message:\n{message}"
            )
            _smtp_send_message(msg)
        except Exception:
            app.logger.exception("Failed to send notification email")

    import threading
    threading.Thread(target=send_notification, daemon=True).start()

    follow_up = "You can track it on your dashboard." if uid else "We usually reply by email within a day."
    return jsonify({
        "success": True,
        "message": f"Thanks, {name}. Your request has been received. {follow_up}",
        "id": req.id
    }), 201


@app.route('/feedback/submit', methods=['POST'])
@login_required
@limiter.limit("20 per day", methods=["POST"])
def submit_public_feedback():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
              'application/json' in (request.headers.get('Accept') or '').lower()

    actor = current_user()
    if not actor:
        if is_ajax:
            return jsonify({
                'success': False,
                'message': 'Please log in to post feedback.',
                'redirect': url_for('login')
            }), 401
        flash('Please log in to post feedback.', 'warning')
        return redirect(url_for('login'))

    message = str(request.form.get('message', '')).strip()
    try:
        rating = int(request.form.get('rating', 5))
    except (TypeError, ValueError):
        rating = 5
    rating = max(1, min(5, rating))

    if len(message) < 4:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Feedback must be at least 4 characters.'}), 400
        flash('Feedback must be at least 4 characters.', 'danger')
        return redirect(url_for('index', _anchor='feedback-corner'))

    if len(message) > 1500:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Feedback must be at most 1500 characters.'}), 400
        flash('Feedback must be at most 1500 characters.', 'danger')
        return redirect(url_for('index', _anchor='feedback-corner'))

    feedback = PublicFeedback(
        user_id=actor.id,
        author_email=normalize_email(getattr(actor, 'email', '')),
        author_name=(getattr(actor, 'name', '') or 'User').strip()[:120],
        rating=rating,
        message=message,
    )
    db.session.add(feedback)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Failed to save public feedback.')
        if is_ajax:
            return jsonify({'success': False, 'message': 'Database is temporarily busy. Please retry in a moment.'}), 503
        flash('Database is temporarily busy. Please try again in a moment.', 'danger')
        return redirect(url_for('index', _anchor='feedback-corner'))

    if is_ajax:
        return jsonify({
            'success': True,
            'message': 'Thanks for your feedback. It is now visible in the public feed.',
            'post': {
                'id': feedback.id,
                'author_name': feedback.author_name,
                'rating': int(feedback.rating or 5),
                'message': feedback.message,
                'created_at': feedback.created_at.strftime('%d %b %Y') if feedback.created_at else ''
            }
        }), 201

    flash('Thanks for your feedback. It is now visible in the public feed.', 'success')
    return redirect(url_for('index', _anchor='feedback-corner'))


def _feedback_dict(fb):
    return {
        "id": fb.id,
        "author_name": fb.author_name,
        "rating": int(fb.rating or 5),
        "message": fb.message,
        "created_at": fb.created_at.strftime("%d %b %Y") if fb.created_at else "",
    }


@app.route("/api/feedback")
def api_feedback_list():
    posts = PublicFeedback.query.order_by(PublicFeedback.created_at.desc()).limit(12).all()
    return jsonify({"feedback": [_feedback_dict(p) for p in posts]})


@app.route("/api/feedback", methods=["POST"])
@api_login_required
@limiter.limit("20 per day", methods=["POST"])
def api_feedback_create():
    actor = current_user()
    data = request_payload()
    message = str(data.get("message", "")).strip()
    try:
        rating = int(data.get("rating", 5))
    except (TypeError, ValueError):
        rating = 5
    rating = max(1, min(5, rating))

    if len(message) < 4:
        return jsonify({"success": False, "message": "Feedback must be at least 4 characters."}), 400
    if len(message) > 1500:
        return jsonify({"success": False, "message": "Feedback must be at most 1500 characters."}), 400

    fb = PublicFeedback(
        user_id=actor.id,
        author_email=normalize_email(getattr(actor, "email", "")),
        author_name=(getattr(actor, "name", "") or "User").strip()[:120],
        rating=rating,
        message=message,
    )
    db.session.add(fb)
    db.session.commit()
    return jsonify({"success": True, "post": _feedback_dict(fb)}), 201


@app.route("/api/projects")
def api_projects():
    category = request.args.get("category", "all")
    query = Project.query if category == "all" else Project.query.filter_by(category=category)
    projects = query.order_by(Project.display_order.asc(), Project.id.asc()).all()
    return jsonify([p.to_dict() for p in projects])


@app.route("/api/projects/<int:project_id>")
def api_project_detail(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"success": False, "message": "Project not found."}), 404
    return jsonify(project.to_dict())


@app.route("/api/csrf-token")
def api_csrf_token():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Authentication required."}), 401
    return jsonify({"token": csrf._get_token()})


# ─── Newsletter (double opt-in) ───────────────────────────────────────────────

NEWSLETTER_RESEND_COOLDOWN = timedelta(minutes=10)
NEWSLETTER_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NEWSLETTER_GENERIC_REPLY = "If that address is valid, we have sent a confirmation link. Please check your inbox."


def _send_newsletter_confirmation(sub):
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or smtp_user).strip()
    if not smtp_from:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be configured")
    queue_newsletter_confirm_email(
        recipient=sub.email,
        confirm_url=f"{resolved_app_url().rstrip('/')}/newsletter/confirm/{sub.confirm_token}",
        sender=smtp_from,
        locale=os.getenv("MAIL_LOCALE", "en"),
    )


@app.route("/api/newsletter/subscribe", methods=["POST"])
@csrf.exempt
@limiter.limit("5 per hour", methods=["POST"])
def api_newsletter_subscribe():
    data = request_payload()
    generic = jsonify({"success": True, "message": NEWSLETTER_GENERIC_REPLY})
    if str(data.get("website", "")).strip():  # honeypot: real visitors never fill this
        return generic
    email = normalize_email(data.get("email"))
    if not email or len(email) > 150 or not NEWSLETTER_EMAIL_RE.match(email):
        return jsonify({"success": False, "message": "Enter a valid email address."}), 400

    now = datetime.utcnow()
    sub = Subscriber.query.filter_by(email=email).first()
    if sub and sub.confirmed:
        return generic  # same reply either way, so addresses cannot be probed

    if sub is None:
        sub = Subscriber(
            email=email,
            confirm_token=secrets.token_urlsafe(32),
            unsub_token=secrets.token_urlsafe(32),
            last_sent_at=now,
        )
        db.session.add(sub)
        try:
            db.session.commit()
        except IntegrityError:
            # A concurrent request for the same address inserted it first and
            # is the one sending the confirmation; do not send a duplicate.
            db.session.rollback()
            return generic
    else:
        # Claim the resend atomically: only one concurrent request can move
        # last_sent_at forward, so the cooldown holds under races too.
        claimed = (
            Subscriber.query.filter(
                Subscriber.id == sub.id,
                Subscriber.confirmed.is_(False),
                or_(Subscriber.last_sent_at.is_(None), Subscriber.last_sent_at < now - NEWSLETTER_RESEND_COOLDOWN),
            ).update({"last_sent_at": now}, synchronize_session=False)
        )
        db.session.commit()
        if not claimed:
            return generic

    try:
        _send_newsletter_confirmation(sub)
    except Exception:
        app.logger.exception("Newsletter confirmation email failed")
        Subscriber.query.filter_by(id=sub.id).update({"last_sent_at": None}, synchronize_session=False)
        db.session.commit()
    return generic


@app.route("/newsletter/confirm/<token>")
@app.route("/newsletter/unsubscribe/<token>")
def newsletter_action_page(token):
    """SPA shell for the confirm/unsubscribe pages. The action itself is a POST
    from a button, so mail scanners that prefetch links cannot confirm or
    unsubscribe anyone."""
    resp = send_from_directory(DIST_DIR, "index.html")
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def _subscriber_by_token(column, token):
    token = str(token or "").strip()
    if len(token) < 20:
        return None
    return Subscriber.query.filter(column == token).first()


@app.route("/api/newsletter/confirm", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per hour", methods=["POST"])
def api_newsletter_confirm():
    sub = _subscriber_by_token(Subscriber.confirm_token, request_payload().get("token"))
    if not sub:
        return jsonify({"success": False, "message": "This link is invalid or has expired."}), 404
    if not sub.confirmed:
        sub.confirmed = True
        sub.confirmed_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"success": True, "message": "You are subscribed. Thank you."})


@app.route("/api/newsletter/unsubscribe", methods=["POST"])
@csrf.exempt
@limiter.limit("30 per hour", methods=["POST"])
def api_newsletter_unsubscribe():
    sub = _subscriber_by_token(Subscriber.unsub_token, request_payload().get("token"))
    if not sub:
        return jsonify({"success": False, "message": "This link is invalid, or you have already unsubscribed."}), 404
    db.session.delete(sub)
    db.session.commit()
    return jsonify({"success": True, "message": "You have been unsubscribed."})


@app.route("/api/admin/newsletter/summary")
@api_superadmin_required
def api_admin_newsletter_summary():
    confirmed = Subscriber.query.filter_by(confirmed=True).count()
    pending = Subscriber.query.filter_by(confirmed=False).count()
    return jsonify({"confirmed": confirmed, "pending": pending})


@app.route("/api/admin/newsletter/export.csv")
@api_superadmin_required
def api_admin_newsletter_export():
    def safe(value):
        # Stop spreadsheet apps from treating an address like "=cmd@x.com" as a formula.
        return "'" + value if value[:1] in ("=", "+", "-", "@") else value

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(["email", "confirmed_at"])
    for sub in Subscriber.query.filter_by(confirmed=True).order_by(Subscriber.confirmed_at.asc()).all():
        writer.writerow([safe(sub.email), sub.confirmed_at.isoformat() if sub.confirmed_at else ""])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=newsletter_subscribers.csv"
    return resp


def _clean_int(value, default=0, minimum=-1_000_000, maximum=1_000_000):
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("Expected a whole number.")
    return max(minimum, min(maximum, number))


def _clean_rating(value, default=5.0):
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Rating must be a number.")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("Rating must be a number.")
    return max(0.0, min(5.0, number))


def _clean_photo_url(value):
    text_value = str(value or "").strip()
    if not text_value:
        return None
    if len(text_value) > 300:
        raise ValueError("Photo URL is too long.")
    if text_value.startswith("/static/uploads/") or re.match(r"^https?://", text_value, re.I):
        return text_value
    raise ValueError("Photo URL must be an uploaded image or an http(s) link.")


def _clean_socials(value):
    if not isinstance(value, dict):
        return None
    cleaned = {}
    for label, url in value.items():
        url = str(url or "").strip()
        if not url:
            continue
        if not re.match(r"^https?://", url, re.I):
            raise ValueError(f"Social link for {str(label)[:30]} must start with http:// or https://.")
        cleaned[str(label)[:30]] = url[:300]
    return json.dumps(cleaned) if cleaned else None


UPLOAD_ROOT = os.path.join(PROJECT_ROOT, "frontend", "static", "uploads")


def _remove_local_upload(url):
    """Delete an uploaded image file that is no longer referenced. Only files
    inside the uploads folder can ever be removed."""
    url = str(url or "")
    prefix = "/static/uploads/"
    if not url.startswith(prefix):
        return
    target = os.path.realpath(os.path.join(UPLOAD_ROOT, url[len(prefix):]))
    if not target.startswith(os.path.realpath(UPLOAD_ROOT) + os.sep):
        return
    still_used = (
        Founder.query.filter_by(photo_url=url).first() or Project.query.filter_by(photo_url=url).first()
    )
    if still_used:
        return
    try:
        os.remove(target)
    except OSError:
        pass


@app.errorhandler(ValueError)
def _handle_admin_value_error(exc):
    if (request.path or "").startswith("/api/admin/"):
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc) or "Invalid value."}), 400
    raise exc


# ─── API — Founders / Team ─────────────────────────────────────────────────────

@app.route("/api/founders")
def api_founders():
    founders = Founder.query.filter_by(active=True) \
        .order_by(Founder.display_order.asc(), Founder.id.asc()).all()
    return jsonify([f.to_dict() for f in founders])


@app.route("/api/admin/founders", methods=["GET"])
@api_superadmin_required
def api_admin_founders_list():
    founders = Founder.query.order_by(Founder.display_order.asc(), Founder.id.asc()).all()
    return jsonify([f.to_dict() for f in founders])


@app.route("/api/admin/founders", methods=["POST"])
@api_superadmin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_founders_create():
    data = request_payload()
    name = str(data.get("name", "")).strip()
    role = str(data.get("role", "")).strip()
    if not name or not role:
        return jsonify({"success": False, "message": "name and role are required."}), 400

    max_order = db.session.query(db.func.max(Founder.display_order)).scalar() or 0
    founder = Founder(
        name=name,
        role=role,
        bio=str(data.get("bio", "")).strip() or None,
        photo_url=_clean_photo_url(data.get("photo_url")),
        socials=_clean_socials(data.get("socials")),
        display_order=_clean_int(data.get("display_order"), max_order + 1),
        active=bool(data.get("active", True)),
    )
    db.session.add(founder)
    db.session.commit()
    return jsonify({"success": True, "founder": founder.to_dict()}), 201


@app.route("/api/admin/founders/<int:founder_id>", methods=["PUT"])
@api_superadmin_required
@limiter.limit("120 per hour", methods=["PUT"])
def api_admin_founders_update(founder_id):
    founder = Founder.query.get(founder_id)
    if not founder:
        return jsonify({"success": False, "message": "Founder not found."}), 404

    data = request_payload()
    if "name" in data:
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"success": False, "message": "name cannot be empty."}), 400
        founder.name = name
    if "role" in data:
        role = str(data.get("role", "")).strip()
        if not role:
            return jsonify({"success": False, "message": "role cannot be empty."}), 400
        founder.role = role
    if "bio" in data:
        founder.bio = str(data.get("bio", "")).strip() or None
    old_photo = founder.photo_url
    if "photo_url" in data:
        founder.photo_url = _clean_photo_url(data.get("photo_url"))
    if "socials" in data:
        founder.socials = _clean_socials(data.get("socials"))
    if "display_order" in data:
        founder.display_order = _clean_int(data.get("display_order"))
    if "active" in data:
        founder.active = bool(data.get("active"))

    db.session.commit()
    if old_photo and old_photo != founder.photo_url:
        _remove_local_upload(old_photo)
    return jsonify({"success": True, "founder": founder.to_dict()})


@app.route("/api/admin/founders/<int:founder_id>", methods=["DELETE"])
@api_superadmin_required
@limiter.limit("60 per hour", methods=["DELETE"])
def api_admin_founders_delete(founder_id):
    founder = Founder.query.get(founder_id)
    if not founder:
        return jsonify({"success": False, "message": "Founder not found."}), 404
    old_photo = founder.photo_url
    db.session.delete(founder)
    db.session.commit()
    _remove_local_upload(old_photo)
    return jsonify({"success": True})


@app.route("/api/admin/founders/reorder", methods=["POST"])
@api_superadmin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_founders_reorder():
    data = request_payload()
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify({"success": False, "message": "order must be a non-empty list of ids."}), 400

    try:
        order_ids = [int(x) for x in order]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "order must contain integer ids."}), 400

    founders = {f.id: f for f in Founder.query.filter(Founder.id.in_(order_ids)).all()}
    if len(founders) != len(set(order_ids)):
        return jsonify({"success": False, "message": "One or more founder ids were not found."}), 400

    for index, founder_id in enumerate(order_ids):
        founders[founder_id].display_order = index
    db.session.commit()
    return jsonify({"success": True})


# ─── API — Admin Projects CRUD ──────────────────────────────────────────────────

CASE_STUDY_TEXT_FIELDS = ("problem", "approach", "outcome")
CASE_STUDY_TEXT_LIMIT = 4000
PROJECT_STACK_LIMIT = 300


def _clean_case_text(value):
    return str(value or "").strip()[:CASE_STUDY_TEXT_LIMIT] or None


def _clean_stack(value):
    items = value if isinstance(value, list) else str(value or "").split(",")
    joined = ",".join(t for t in (str(i).strip() for i in items) if t)
    return joined[:PROJECT_STACK_LIMIT].strip(",") or None


@app.route("/api/admin/projects", methods=["POST"])
@api_superadmin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_projects_create():
    data = request_payload()
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip()
    if not title or not description or not category:
        return jsonify({"success": False, "message": "title, description and category are required."}), 400

    tags = data.get("tags")
    if isinstance(tags, list):
        tags = ",".join(str(t).strip() for t in tags if str(t).strip())

    max_order = db.session.query(db.func.max(Project.display_order)).scalar() or 0
    project = Project(
        title=title,
        description=description,
        category=category,
        tags=tags or None,
        price=str(data.get("price", "")).strip() or None,
        duration=str(data.get("duration", "")).strip() or None,
        rating=_clean_rating(data.get("rating")),
        icon=str(data.get("icon", "")).strip() or None,
        bg_class=str(data.get("bg_class", "")).strip() or None,
        featured=bool(data.get("featured", False)),
        display_order=_clean_int(data.get("display_order"), max_order + 1),
        photo_url=_clean_photo_url(data.get("photo_url")),
        problem=_clean_case_text(data.get("problem")),
        approach=_clean_case_text(data.get("approach")),
        outcome=_clean_case_text(data.get("outcome")),
        stack=_clean_stack(data.get("stack")),
    )
    db.session.add(project)
    db.session.commit()
    return jsonify({"success": True, "project": project.to_dict()}), 201


@app.route("/api/admin/projects/<int:project_id>", methods=["PUT"])
@api_superadmin_required
@limiter.limit("120 per hour", methods=["PUT"])
def api_admin_projects_update(project_id):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"success": False, "message": "Project not found."}), 404

    data = request_payload()
    if "title" in data:
        title = str(data.get("title", "")).strip()
        if not title:
            return jsonify({"success": False, "message": "title cannot be empty."}), 400
        project.title = title
    if "description" in data:
        description = str(data.get("description", "")).strip()
        if not description:
            return jsonify({"success": False, "message": "description cannot be empty."}), 400
        project.description = description
    if "category" in data:
        category = str(data.get("category", "")).strip()
        if not category:
            return jsonify({"success": False, "message": "category cannot be empty."}), 400
        project.category = category
    if "tags" in data:
        tags = data.get("tags")
        if isinstance(tags, list):
            tags = ",".join(str(t).strip() for t in tags if str(t).strip())
        project.tags = tags or None
    if "price" in data:
        project.price = str(data.get("price", "")).strip() or None
    if "duration" in data:
        project.duration = str(data.get("duration", "")).strip() or None
    if "rating" in data:
        project.rating = _clean_rating(data.get("rating"))
    if "icon" in data:
        project.icon = str(data.get("icon", "")).strip() or None
    if "bg_class" in data:
        project.bg_class = str(data.get("bg_class", "")).strip() or None
    if "featured" in data:
        project.featured = bool(data.get("featured"))
    if "display_order" in data:
        project.display_order = _clean_int(data.get("display_order"))
    old_photo = project.photo_url
    if "photo_url" in data:
        project.photo_url = _clean_photo_url(data.get("photo_url"))
    for field in CASE_STUDY_TEXT_FIELDS:
        if field in data:
            setattr(project, field, _clean_case_text(data.get(field)))
    if "stack" in data:
        project.stack = _clean_stack(data.get("stack"))

    db.session.commit()
    if old_photo and old_photo != project.photo_url:
        _remove_local_upload(old_photo)
    return jsonify({"success": True, "project": project.to_dict()})


@app.route("/api/admin/projects/<int:project_id>", methods=["DELETE"])
@api_superadmin_required
@limiter.limit("60 per hour", methods=["DELETE"])
def api_admin_projects_delete(project_id):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"success": False, "message": "Project not found."}), 404
    old_photo = project.photo_url
    db.session.delete(project)
    db.session.commit()
    _remove_local_upload(old_photo)
    return jsonify({"success": True})


@app.route("/api/admin/projects/reorder", methods=["POST"])
@api_superadmin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_projects_reorder():
    data = request_payload()
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify({"success": False, "message": "order must be a non-empty list of ids."}), 400

    try:
        order_ids = [int(x) for x in order]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "order must contain integer ids."}), 400

    projects = {p.id: p for p in Project.query.filter(Project.id.in_(order_ids)).all()}
    if len(projects) != len(set(order_ids)):
        return jsonify({"success": False, "message": "One or more project ids were not found."}), 400

    for index, project_id in enumerate(order_ids):
        projects[project_id].display_order = index
    db.session.commit()
    return jsonify({"success": True})


# ─── API — Admin Image Upload ───────────────────────────────────────────────────

ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_PIXELS = 40_000_000  # reject decompression bombs before decoding
UPLOAD_MAX_DIMENSIONS = {"founders": 1600, "projects": 1200}


@app.route("/api/admin/upload", methods=["POST"])
@api_superadmin_required
@limiter.limit("30 per hour", methods=["POST"])
def api_admin_upload():
    kind = (request.form.get("kind") or "").strip().lower()
    if kind not in UPLOAD_MAX_DIMENSIONS:
        return jsonify({"success": False, "message": "kind must be 'founders' or 'projects'."}), 400

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"success": False, "message": "No file provided."}), 400

    ext = os.path.splitext(secure_filename(upload.filename))[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"success": False, "message": "Unsupported file type."}), 400

    raw = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        return jsonify({"success": False, "message": "File too large (max 8MB)."}), 400

    from io import BytesIO
    try:
        probe = Image.open(BytesIO(raw))
        width, height = probe.size
        if width * height > MAX_UPLOAD_PIXELS:
            return jsonify({"success": False, "message": "Image dimensions are too large."}), 400
        probe.verify()
        image = Image.open(BytesIO(raw))
        image.load()
    except Exception:
        return jsonify({"success": False, "message": "File is not a valid image."}), 400

    try:
        # Phone cameras store orientation in EXIF and keep the pixels un-rotated.
        # We re-encode to JPEG and drop EXIF, so bake the rotation into the pixels
        # first — otherwise portrait photos display sideways.
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass

        # Handle RGBA/transparency gracefully by blending onto a white background
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        max_dim = UPLOAD_MAX_DIMENSIONS[kind]
        image.thumbnail((max_dim, max_dim), Image.LANCZOS)

        filename = f"{uuid.uuid4().hex}.jpg"
        upload_dir = os.path.join(PROJECT_ROOT, "frontend", "static", "uploads", kind)
        os.makedirs(upload_dir, exist_ok=True)
        image.save(os.path.join(upload_dir, filename), format="JPEG", quality=85, optimize=True)

        return jsonify({"success": True, "url": f"/static/uploads/{kind}/{filename}"}), 201
    except Exception as e:
        app.logger.exception("Failed to process and save uploaded image")
        return jsonify({"success": False, "message": "Failed to save image."}), 500


@app.route("/api/traffic/page-view", methods=["POST"])
@csrf.exempt
@limiter.limit("1200 per hour", methods=["POST"])
def api_track_page_view():
    payload = request.get_json(silent=True) or {}
    try:
        visitor_id = _record_traffic_event("page_view", payload)
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to track page view")
        return jsonify({"success": False}), 500

    response = jsonify({"success": True})
    response.set_cookie(
        "ux_vid",
        visitor_id,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        secure=False,
        httponly=False,
    )
    return response


@app.route("/api/traffic/scroll", methods=["POST"])
@csrf.exempt
@limiter.limit("3600 per hour", methods=["POST"])
def api_track_scroll():
    payload = request.get_json(silent=True) or {}
    try:
        visitor_id = _record_traffic_event("scroll", payload)
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to track scroll")
        return jsonify({"success": False}), 500

    response = jsonify({"success": True})
    response.set_cookie(
        "ux_vid",
        visitor_id,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        secure=False,
        httponly=False,
    )
    return response


@app.route("/admin/api/traffic-summary")
@admin_required
@admin_capability_required("analytics_view")
def admin_traffic_summary():
    now_utc = datetime.utcnow()
    five_minutes_ago = now_utc - timedelta(minutes=5)
    today_start = datetime.combine(now_utc.date(), datetime.min.time())

    active_now = db.session.query(db.func.count(db.distinct(SiteTrafficEvent.visitor_id))).filter(
        SiteTrafficEvent.created_at >= five_minutes_ago
    ).scalar() or 0
    today_opens = SiteTrafficEvent.query.filter(
        SiteTrafficEvent.event_type == "page_view",
        SiteTrafficEvent.created_at >= today_start,
    ).count()
    unique_visitors_today = db.session.query(db.func.count(db.distinct(SiteTrafficEvent.visitor_id))).filter(
        SiteTrafficEvent.event_type == "page_view",
        SiteTrafficEvent.created_at >= today_start,
    ).scalar() or 0
    today_scrolled = db.session.query(db.func.count(db.distinct(SiteTrafficEvent.visitor_id))).filter(
        SiteTrafficEvent.event_type == "scroll",
        SiteTrafficEvent.scroll_percent >= 25,
        SiteTrafficEvent.created_at >= today_start,
    ).scalar() or 0

    scroll_max_subq = db.session.query(
        SiteTrafficEvent.visitor_id.label("visitor_id"),
        db.func.max(SiteTrafficEvent.scroll_percent).label("max_scroll"),
    ).filter(
        SiteTrafficEvent.event_type == "scroll",
        SiteTrafficEvent.created_at >= today_start,
        SiteTrafficEvent.scroll_percent.isnot(None),
    ).group_by(SiteTrafficEvent.visitor_id).subquery()

    avg_scroll_depth = db.session.query(db.func.avg(scroll_max_subq.c.max_scroll)).scalar() or 0

    registered_total = User.query.count()
    users = User.query.order_by(User.created_at.desc()).limit(50).all()
    recent_users = [
        {
            "name": (u.name or "").strip() or "Unknown",
            "email": (u.email or "").strip(),
            "created_at": u.created_at.strftime("%d %b %Y %H:%M") if u.created_at else "",
        }
        for u in users
    ]

    return jsonify({
        "active_now": int(active_now),
        "today_opens": int(today_opens),
        "unique_visitors_today": int(unique_visitors_today),
        "today_scrolled": int(today_scrolled),
        "avg_scroll_depth": round(float(avg_scroll_depth), 1),
        "registered_total": registered_total,
        "registered_users": recent_users,
    })


def _build_live_website_users(window_minutes=5, limit=50):
    now_utc = datetime.utcnow()
    cutoff = now_utc - timedelta(minutes=window_minutes)

    active_count = db.session.query(
        db.func.count(db.distinct(SiteTrafficEvent.visitor_id)),
    ).filter(
        SiteTrafficEvent.created_at >= cutoff,
    ).scalar() or 0

    active_rows = db.session.query(
        SiteTrafficEvent.visitor_id.label("visitor_id"),
        db.func.max(SiteTrafficEvent.created_at).label("last_seen"),
        db.func.count(SiteTrafficEvent.id).label("event_count"),
    ).filter(
        SiteTrafficEvent.created_at >= cutoff,
    ).group_by(
        SiteTrafficEvent.visitor_id,
    ).order_by(
        db.func.max(SiteTrafficEvent.created_at).desc(),
    ).limit(limit).all()

    visitor_ids = [row.visitor_id for row in active_rows]
    latest_events = {}
    if visitor_ids:
        recent_events = SiteTrafficEvent.query.filter(
            SiteTrafficEvent.visitor_id.in_(visitor_ids),
            SiteTrafficEvent.created_at >= cutoff,
        ).order_by(SiteTrafficEvent.created_at.desc()).all()

        for event in recent_events:
            latest_events.setdefault(event.visitor_id, event)

    user_ids = {event.user_id for event in latest_events.values() if event.user_id}
    users_by_id = {
        user.id: user
        for user in User.query.filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    live_users = []
    for row in active_rows:
        event = latest_events.get(row.visitor_id)
        if not event:
            continue

        user = users_by_id.get(event.user_id)
        display_name = (user.name or "").strip() if user else ""
        if not display_name:
            display_name = (event.user_email or "Anonymous Visitor").strip() or "Anonymous Visitor"

        live_users.append({
            "visitor_id": row.visitor_id,
            "name": display_name,
            "email": (user.email if user else event.user_email or "") or "-",
            "page_path": event.page_path or "/",
            "event_count": int(row.event_count or 0),
            "last_seen": row.last_seen.strftime('%Y-%m-%d %H:%M:%S') if row.last_seen else "-",
            "state": "authenticated" if event.user_id else "guest",
        })

    return live_users, int(active_count)


@app.route("/admin/api/live-users")
@admin_required
@admin_capability_required("analytics_view")
def admin_live_users():
    total_users = User.query.count()

    login_rows = db.session.query(
        User.id.label('user_id'),
        User.name.label('name'),
        User.email.label('email'),
        User.role.label('role'),
        User.admin_scope.label('admin_scope'),
        db.func.max(UserSession.last_seen).label('last_seen'),
        db.func.count(UserSession.id).label('session_count'),
    ).join(
        UserSession,
        UserSession.user_id == User.id,
    ).filter(
        UserSession.is_active.is_(True),
    ).group_by(
        User.id, User.name, User.email, User.role, User.admin_scope,
    ).order_by(
        db.func.max(UserSession.last_seen).desc(),
    ).all()

    payload = {
        "total_users": int(total_users or 0),
        "active_session_users": len(login_rows),
    }

    admin_user = current_user()
    if is_super_admin(admin_user):
        payload["logged_in_users"] = [
            {
                "user_id": int(row.user_id),
                "name": row.name or "Unknown",
                "email": row.email or "",
                "role": row.role or "user",
                "admin_scope": row.admin_scope or "",
                "session_count": int(row.session_count or 0),
                "last_seen": row.last_seen.strftime('%Y-%m-%d %H:%M:%S') if row.last_seen else "-",
            }
            for row in login_rows
        ]

    return jsonify(payload)


@app.route("/admin/api/live-website-users")
@admin_required
@admin_capability_required("analytics_view")
def admin_live_website_users():
    live_users, active_count = _build_live_website_users()

    return jsonify({
        "total_users": int(User.query.count() or 0),
        "active_website_users": active_count,
        "live_users": live_users,
    })


@app.route("/admin/api/traffic-daily-pages")
@admin_required
@admin_capability_required("analytics_view")
def admin_traffic_daily_pages():
    days = request.args.get("days", default=14, type=int)
    if not days or days < 1:
        days = 14
    days = min(days, 60)

    today = datetime.utcnow().date()
    start_day = today - timedelta(days=days - 1)
    start_ts = datetime.combine(start_day, datetime.min.time())

    events = SiteTrafficEvent.query.filter(
        SiteTrafficEvent.event_type == "page_view",
        SiteTrafficEvent.created_at >= start_ts,
    ).all()

    labels = [
        (start_day + timedelta(days=idx)).strftime("%d %b")
        for idx in range(days)
    ]
    iso_days = [
        (start_day + timedelta(days=idx)).isoformat()
        for idx in range(days)
    ]

    bucket_names = ["Home", "Login", "Dashboard", "Portfolio", "Other"]
    day_index = {iso: idx for idx, iso in enumerate(iso_days)}
    series = {name: [0] * days for name in bucket_names}

    for ev in events:
        if not ev.created_at:
            continue
        day_key = ev.created_at.date().isoformat()
        idx = day_index.get(day_key)
        if idx is None:
            continue
        bucket = _traffic_bucket_for_path(ev.page_path)
        series[bucket][idx] += 1

    return jsonify({
        "labels": labels,
        "datasets": [
            {"label": name, "data": series[name]}
            for name in bucket_names
        ]
    })


@app.route("/admin/export/traffic-csv")
@admin_required
@admin_capability_required("export_data")
def export_traffic_csv():
    logs = SiteTrafficEvent.query.order_by(SiteTrafficEvent.created_at.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Visitor ID", "User ID", "User Email", "Event Type", "Page", "Page Bucket",
        "Scroll Percent", "Referrer", "IP Address", "User Agent", "Created At (UTC)"
    ])

    for ev in logs:
        writer.writerow([
            ev.id,
            ev.visitor_id,
            ev.user_id or "",
            ev.user_email or "",
            ev.event_type,
            ev.page_path,
            _traffic_bucket_for_path(ev.page_path),
            ev.scroll_percent if ev.scroll_percent is not None else "",
            ev.referrer or "",
            ev.ip_address or "",
            ev.user_agent or "",
            ev.created_at.strftime("%Y-%m-%d %H:%M:%S") if ev.created_at else "",
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=unitaryx_traffic_logs.csv"
    return response


@app.route('/api/ab-tests/resolve')
@csrf.exempt
def resolve_ab_tests():
    visitor_id = _resolve_visitor_id(request.args.to_dict() if request.args else {})
    tests = ABTestConfig.query.filter_by(enabled=True).all()

    assignments = {}
    for test in tests:
        variant = _resolve_ab_variant(visitor_id, test.test_key, test.allocation_b)
        text_value = test.variant_b if variant == 'B' else test.variant_a
        assignments[test.test_key] = {
            'variant': variant,
            'text': text_value,
            'allocation_b': int(test.allocation_b or 0),
        }

    res = jsonify({
        'success': True,
        'visitor_id': visitor_id,
        'assignments': assignments,
    })
    res.set_cookie('ux_vid', visitor_id, max_age=86400 * 180, samesite='Lax')
    return res


def _ab_test_dict(test):
    return {
        "id": test.id,
        "test_key": test.test_key,
        "label": test.label,
        "enabled": bool(test.enabled),
        "allocation_b": int(test.allocation_b or 0),
        "variant_a": test.variant_a,
        "variant_b": test.variant_b,
        "updated_at": test.updated_at.isoformat() if test.updated_at else None,
    }


@app.route("/api/admin/ab-tests")
@api_admin_required
def api_admin_ab_tests():
    """JSON list of A/B configs for the React studio. Editing stays gated behind
    the same 'admin_control' capability the classic panel uses, surfaced as
    `can_edit` so the UI can render read-only for non-superadmins."""
    tests = ABTestConfig.query.order_by(ABTestConfig.id.asc()).all()
    return jsonify({
        "can_edit": has_admin_capability("admin_control"),
        "tests": [_ab_test_dict(t) for t in tests],
    })


@app.route("/api/admin/ab-tests/<int:test_id>", methods=["PUT"])
@api_admin_required
@limiter.limit("120 per hour", methods=["PUT"])
def api_admin_ab_test_update(test_id):
    if not has_admin_capability("admin_control"):
        return jsonify({"success": False, "message": "Insufficient permission for this action."}), 403

    test = ABTestConfig.query.get(test_id)
    if not test:
        return jsonify({"success": False, "message": "A/B test not found."}), 404

    data = request_payload()
    variant_a = str(data.get("variant_a", test.variant_a) or "").strip()
    variant_b = str(data.get("variant_b", test.variant_b) or "").strip()
    if not variant_a or not variant_b:
        return jsonify({"success": False, "message": "Both variants must have text."}), 400

    try:
        allocation = int(data.get("allocation_b", test.allocation_b))
    except (TypeError, ValueError):
        allocation = test.allocation_b

    test.enabled = bool(data.get("enabled", test.enabled))
    test.allocation_b = max(0, min(100, allocation))
    test.variant_a = variant_a[:300]
    test.variant_b = variant_b[:300]
    test.updated_at = datetime.utcnow()
    db.session.commit()

    log_superadmin_action(
        action='AB_TEST_UPDATED',
        target=test.test_key,
        details=f'enabled={test.enabled},allocation_b={test.allocation_b}',
        actor=current_user(),
    )
    return jsonify({"success": True, "test": _ab_test_dict(test)})


# ─── API — Admin workflow (tasks / finance / approvals) ───────────────────────
# JSON mirrors of the classic panel's form-post workflow routes, for the React
# studio. Business rules (capabilities, lane ownership, allowed statuses) are
# kept identical to the originals so both surfaces behave the same.

def _capability_denied():
    return jsonify({"success": False, "message": "Insufficient permission for this action."}), 403


def _admin_task_dict(task):
    return {
        "id": task.id,
        "title": task.title,
        "details": task.details,
        "assigned_to_email": task.assigned_to_email,
        "assigned_by_email": task.assigned_by_email,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@app.route("/api/admin/tasks")
@api_admin_required
def api_admin_tasks():
    actor = current_user()
    actor_email = normalize_email(getattr(actor, "email", ""))
    is_super = is_super_admin(actor)

    query = AdminTask.query
    if not is_super:
        # Non-superadmins only see tasks assigned to them.
        query = query.filter(db.func.lower(AdminTask.assigned_to_email) == actor_email)
    tasks = query.order_by(AdminTask.created_at.desc()).all()

    assignable = []
    if is_super:
        assignable = [
            normalize_email(u.email)
            for u in User.query.filter(
                db.func.lower(User.role) == "admin", User.is_active.is_(True)
            ).order_by(User.email.asc()).all()
        ]

    return jsonify({
        "can_assign": is_super,
        "my_email": actor_email,
        "assignable_admins": assignable,
        "tasks": [_admin_task_dict(t) for t in tasks],
    })


@app.route("/api/admin/tasks", methods=["POST"])
@api_admin_required
@limiter.limit("120 per hour", methods=["POST"])
def api_admin_tasks_create():
    creator = current_user()
    if not is_super_admin(creator):
        return _capability_denied()

    data = request_payload()
    title = str(data.get("title", "")).strip()
    details = str(data.get("details", "")).strip()

    # `assigned_to_emails` (list) is the multi-assign form; the single
    # `assigned_to_email` string is still accepted.
    raw = data.get("assigned_to_emails")
    if raw is None:
        raw = [data.get("assigned_to_email", "")]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return jsonify({"success": False, "message": "Please choose at least one admin."}), 400
    emails = []
    for item in raw:
        email = normalize_email(item)
        if email and email not in emails:
            emails.append(email)

    if len(title) < 3 or len(title) > 160:
        return jsonify({"success": False, "message": "Task title must be between 3 and 160 characters."}), 400
    if not emails:
        return jsonify({"success": False, "message": "Please choose at least one admin."}), 400
    if len(emails) > 25:
        return jsonify({"success": False, "message": "You can assign a task to at most 25 admins at once."}), 400
    if not all(validate_email(e) for e in emails):
        return jsonify({"success": False, "message": "Please choose valid admin emails."}), 400

    active_admins = {
        normalize_email(u.email)
        for u in User.query.filter(
            db.func.lower(User.email).in_(emails), User.role == "admin", User.is_active.is_(True)
        ).all()
    }
    missing = [e for e in emails if e not in active_admins]
    if missing:
        return jsonify({
            "success": False,
            "message": f"Not an active admin account: {', '.join(missing)}.",
        }), 400

    # One task row per assignee so each person tracks their own status.
    creator_email = normalize_email(getattr(creator, "email", ""))
    tasks = [
        AdminTask(
            title=title,
            details=details,
            assigned_to_email=email,
            assigned_by_email=creator_email,
            status="Pending",
        )
        for email in emails
    ]
    db.session.add_all(tasks)
    for email in emails:
        log_superadmin_action(
            action="TASK_ASSIGNED",
            target=email,
            details=f"title={title}",
            actor=creator,
        )
    db.session.commit()

    # Best-effort notifications, exactly like the classic route: a mail failure
    # must never fail the assignment itself.
    emails_failed = []
    for email in emails:
        try:
            _send_task_assigned_email(email, title, details, creator_email)
        except Exception:
            emails_failed.append(email)
            app.logger.exception("Failed to send task assignment email")

    return jsonify({
        "success": True,
        "task": _admin_task_dict(tasks[0]),
        "tasks": [_admin_task_dict(t) for t in tasks],
        "email_sent": not emails_failed,
        "emails_failed": emails_failed,
    }), 201


@app.route("/api/admin/tasks/<int:task_id>/status", methods=["PUT"])
@api_admin_required
@limiter.limit("240 per hour", methods=["PUT"])
def api_admin_task_status(task_id):
    actor = current_user()
    actor_email = normalize_email(getattr(actor, "email", ""))
    data = request_payload()
    next_status = str(data.get("status", "")).strip()

    if next_status not in {"Pending", "In Progress", "Done"}:
        return jsonify({"success": False, "message": "Invalid task status selected."}), 400

    task = AdminTask.query.get(task_id)
    if not task:
        return jsonify({"success": False, "message": "Task not found."}), 404

    if normalize_email(task.assigned_to_email) != actor_email and not is_super_admin(actor):
        return jsonify({
            "success": False,
            "message": "You can only update tasks assigned to your admin account.",
        }), 403

    task.status = next_status
    task.updated_at = datetime.utcnow()
    if is_super_admin(actor):
        log_superadmin_action(
            action="TASK_STATUS_UPDATED",
            target=normalize_email(task.assigned_to_email),
            details=f"task_id={task.id},status={next_status}",
            actor=actor,
        )
    db.session.commit()
    return jsonify({"success": True, "task": _admin_task_dict(task)})


@app.route("/api/admin/tasks/<int:task_id>", methods=["DELETE"])
@api_admin_required
@limiter.limit("60 per hour", methods=["DELETE"])
def api_admin_task_delete(task_id):
    actor = current_user()
    if not is_super_admin(actor):
        return _capability_denied()

    task = AdminTask.query.get(task_id)
    if not task:
        return jsonify({"success": False, "message": "Task not found."}), 404

    log_superadmin_action(
        action="TASK_DELETED",
        target=normalize_email(task.assigned_to_email),
        details=f"task_id={task.id}",
        actor=actor,
    )
    db.session.delete(task)
    db.session.commit()
    return jsonify({"success": True})


def _finance_entry_dict(entry):
    return {
        "id": entry.id,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "counterparty": entry.counterparty,
        "amount": entry.amount,
        "due_date": entry.due_date,
        "notes": entry.notes,
        "status": entry.status,
        "assigned_admin_email": entry.assigned_admin_email,
        "created_by_email": entry.created_by_email,
        "reviewed_by_email": entry.reviewed_by_email,
        "review_note": entry.review_note,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@app.route("/api/admin/finance")
@api_admin_required
def api_admin_finance():
    actor = current_user()
    if not has_admin_capability("finance_ops", actor):
        return _capability_denied()

    entries = FinanceEntry.query.order_by(FinanceEntry.created_at.desc()).all()
    return jsonify({
        "can_review": is_super_admin(actor),
        "my_email": normalize_email(getattr(actor, "email", "")),
        "slots": get_finance_admin_slots(),
        "entries": [_finance_entry_dict(e) for e in entries],
    })


@app.route("/api/admin/finance", methods=["POST"])
@api_admin_required
@limiter.limit("120 per hour", methods=["POST"])
def api_admin_finance_create():
    actor = current_user()
    if not has_admin_capability("finance_ops", actor):
        return _capability_denied()

    actor_email = normalize_email(getattr(actor, "email", ""))
    data = request_payload()
    entry_type = normalize_finance_entry_type(data.get("entry_type", "receivable"))
    title = str(data.get("title", "")).strip()
    counterparty = str(data.get("counterparty", "")).strip()
    due_date = str(data.get("due_date", "")).strip()
    notes = str(data.get("notes", "")).strip()

    try:
        amount = int(float(data.get("amount", 0) or 0))
    except (TypeError, ValueError):
        amount = 0

    if len(title) < 3:
        return jsonify({"success": False, "message": "Finance title must be at least 3 characters."}), 400
    if len(counterparty) < 2:
        return jsonify({"success": False, "message": "Counterparty is required."}), 400
    if amount <= 0:
        return jsonify({"success": False, "message": "Amount must be greater than 0."}), 400

    assigned_email = assign_finance_admin_email(entry_type)
    if not assigned_email:
        return jsonify({
            "success": False,
            "message": "Assign two active finance admins first (scope=finance).",
        }), 400

    if not is_super_admin(actor) and actor_email != assigned_email:
        return jsonify({"success": False, "message": "This lane is assigned to the other finance admin."}), 403

    entry = FinanceEntry(
        entry_type=entry_type,
        title=title,
        counterparty=counterparty,
        amount=amount,
        due_date=due_date,
        notes=notes,
        status="submitted",
        assigned_admin_email=assigned_email,
        created_by_email=actor_email,
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({"success": True, "entry": _finance_entry_dict(entry)}), 201


@app.route("/api/admin/finance/<int:entry_id>/status", methods=["PUT"])
@api_admin_required
@limiter.limit("240 per hour", methods=["PUT"])
def api_admin_finance_status(entry_id):
    actor = current_user()
    if not has_admin_capability("finance_ops", actor):
        return _capability_denied()

    actor_email = normalize_email(getattr(actor, "email", ""))
    entry = FinanceEntry.query.get(entry_id)
    if not entry:
        return jsonify({"success": False, "message": "Finance entry not found."}), 404

    requested = str(request_payload().get("status", "")).strip().lower()
    if requested not in {"submitted", "processed", "needs_superadmin_check", "closed"}:
        return jsonify({"success": False, "message": "Invalid finance status."}), 400

    if not is_super_admin(actor) and actor_email != normalize_email(entry.assigned_admin_email):
        return jsonify({
            "success": False,
            "message": "You can update only your assigned finance items.",
        }), 403
    if not is_super_admin(actor) and (requested in {"closed", "rejected"} or entry.status in {"closed", "rejected"}):
        return jsonify({
            "success": False,
            "message": "Closing or reopening an entry needs superadmin review.",
        }), 403

    entry.status = requested
    if requested == "needs_superadmin_check":
        entry.reviewed_by_email = None
        entry.review_note = None
    db.session.commit()
    return jsonify({"success": True, "entry": _finance_entry_dict(entry)})


@app.route("/api/admin/finance/<int:entry_id>/review", methods=["PUT"])
@api_admin_required
@limiter.limit("120 per hour", methods=["PUT"])
def api_admin_finance_review(entry_id):
    reviewer = current_user()
    if not is_super_admin(reviewer):
        return _capability_denied()

    entry = FinanceEntry.query.get(entry_id)
    if not entry:
        return jsonify({"success": False, "message": "Finance entry not found."}), 404

    data = request_payload()
    decision = str(data.get("decision", "")).strip().lower()
    note = str(data.get("review_note", "")).strip()

    if entry.status != "needs_superadmin_check":
        return jsonify({
            "success": False,
            "message": "This finance entry is not in the superadmin check queue.",
        }), 400
    if decision not in {"approve", "reject"}:
        return jsonify({"success": False, "message": "Invalid review decision."}), 400

    entry.reviewed_by_email = normalize_email(getattr(reviewer, "email", ""))
    entry.review_note = note[:300] if note else ""
    entry.status = "closed" if decision == "approve" else "rejected"
    db.session.commit()

    log_superadmin_action(
        action="FINANCE_ENTRY_REVIEWED",
        target=f"finance_entry:{entry.id}",
        details=f"decision={decision},type={entry.entry_type},amount={entry.amount}",
        actor=reviewer,
    )
    return jsonify({"success": True, "entry": _finance_entry_dict(entry)})


def _approval_ticket_dict(ticket):
    return {
        "id": ticket.id,
        "action_key": ticket.action_key,
        "payload_json": ticket.payload_json,
        "requested_by_email": ticket.requested_by_email,
        "requested_by_scope": ticket.requested_by_scope,
        "reason": ticket.reason,
        "status": ticket.status,
        "reviewed_by_email": ticket.reviewed_by_email,
        "review_note": ticket.review_note,
        "reviewed_at": ticket.reviewed_at.isoformat() if ticket.reviewed_at else None,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }


@app.route("/api/admin/approvals")
@api_admin_required
def api_admin_approvals():
    actor = current_user()
    tickets = ApprovalTicket.query.order_by(ApprovalTicket.created_at.desc()).all()
    return jsonify({
        "can_review": has_admin_capability("admin_control", actor),
        "tickets": [_approval_ticket_dict(t) for t in tickets],
    })


@app.route("/api/admin/approvals/<int:ticket_id>/<decision>", methods=["POST"])
@api_admin_required
@limiter.limit("120 per hour", methods=["POST"])
def api_admin_approval_decide(ticket_id, decision):
    reviewer = current_user()
    if not has_admin_capability("admin_control", reviewer):
        return _capability_denied()
    if decision not in {"approve", "reject"}:
        return jsonify({"success": False, "message": "Invalid decision."}), 400

    ticket = ApprovalTicket.query.get(ticket_id)
    if not ticket:
        return jsonify({"success": False, "message": "Ticket not found."}), 404
    if ticket.status != "pending":
        return jsonify({"success": False, "message": "Ticket already reviewed."}), 400

    reviewer_email = normalize_email(getattr(reviewer, "email", ""))
    note = str(request_payload().get("review_note", "")).strip()

    if decision == "approve":
        try:
            result_note = _execute_approval_ticket(ticket)
        except Exception as exc:
            db.session.rollback()
            app.logger.exception("Approval execution failed for ticket %s", ticket_id)
            return jsonify({"success": False, "message": f"Approval failed: {exc}"}), 400
        ticket.status = "approved"
        ticket.review_note = (result_note or "")[:300]
    else:
        ticket.status = "rejected"
        ticket.review_note = note[:300] if note else "Rejected by superadmin."

    ticket.reviewed_by_email = reviewer_email
    ticket.reviewed_at = datetime.utcnow()
    db.session.commit()

    log_superadmin_action(
        action="APPROVAL_APPROVED" if decision == "approve" else "APPROVAL_REJECTED",
        target=f"ticket:{ticket.id}",
        details=f"action={ticket.action_key}",
        actor=reviewer,
    )
    return jsonify({"success": True, "ticket": _approval_ticket_dict(ticket)})


# ─── API — Admin leads (ProjectRequest management) ────────────────────────────
# The core admin surface, ported from the classic panel. Unlike the customer
# dashboard, this IS the admin view, so lead-scoring and internal_notes ARE
# returned here. Sensitive actions by non-superadmins still queue approval
# tickets, exactly like the classic form routes (same helpers reused).

def _lead_dict(req):
    return {
        "id": req.id,
        "name": req.name,
        "email": req.email,
        "phone": req.phone,
        "service": req.service,
        "deadline": req.deadline,
        "message": req.message,
        "status": req.status,
        "priority": req.priority,
        "value": req.value or 0,
        "is_new_update": bool(req.is_new_update),
        "internal_notes": req.internal_notes,
        "lead_score_total": req.lead_score_total,
        "lead_score_value": req.lead_score_value,
        "lead_score_urgency": req.lead_score_urgency,
        "lead_score_conversion": req.lead_score_conversion,
        "lead_tier": req.lead_tier,
        "stale_flag": bool(req.stale_flag),
        "escalation_level": int(req.escalation_level or 0),
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


@app.route("/api/admin/leads")
@api_admin_required
def api_admin_leads():
    if not has_admin_capability("lead_manage"):
        return _capability_denied()

    rows = ProjectRequest.query.order_by(ProjectRequest.created_at.desc()).all()
    # Same freshness maintenance the classic admin panel performs on load.
    policy = _apply_stale_followup_policy(rows)
    scores_updated = bool(policy.get("changed"))
    for row in rows:
        if row.lead_last_scored_at is None:
            _score_project_request(row)
            scores_updated = True
    if scores_updated:
        db.session.commit()

    total = len(rows)
    summary = {
        "total": total,
        "new": sum(1 for r in rows if r.status == "New"),
        "in_progress": sum(1 for r in rows if r.status == "In Progress"),
        "done": sum(1 for r in rows if r.status == "Done"),
        "total_value": sum((r.value or 0) for r in rows),
        "updates": sum(1 for r in rows if r.is_new_update),
    }
    return jsonify({
        "can_manage": has_admin_capability("lead_manage"),
        "is_super": is_super_admin(),
        "summary": summary,
        "leads": [_lead_dict(r) for r in rows],
    })


@app.route("/api/admin/leads/<int:req_id>", methods=["PUT"])
@api_admin_required
@limiter.limit("240 per hour", methods=["PUT"])
def api_admin_lead_update(req_id):
    actor = current_user()
    if not has_admin_capability("lead_manage"):
        return _capability_denied()

    req = ProjectRequest.query.get(req_id)
    if not req:
        return jsonify({"success": False, "message": "Inquiry not found."}), 404

    data = request_payload()
    status = data.get("status", req.status)
    priority = data.get("priority", req.priority)
    try:
        value = int(data.get("value", req.value) or 0)
    except (TypeError, ValueError):
        value = req.value or 0
    message = data.get("message", None)

    status_map = {"new": "New", "in progress": "In Progress", "done": "Done"}
    priority_map = {"low": "Low", "medium": "Medium", "high": "High"}
    status = status_map.get(str(status or "").strip().lower())
    priority = priority_map.get(str(priority or "").strip().lower())
    if not status or not priority:
        return jsonify({"success": False, "message": "Invalid status or priority."}), 400

    # Approval is needed only when a change moves the lead INTO a sensitive
    # state, not whenever an already-sensitive lead is touched.
    requires_approval = (not is_super_admin(actor)) and (
        (status.lower() == "done" and (req.status or "").lower() != "done")
        or (priority.lower() == "high" and (req.priority or "").lower() != "high")
        or (int(value or 0) >= 20000 and int(value or 0) != int(req.value or 0))
    )
    if requires_approval:
        if "internal_notes" in data:  # notes are not sensitive; never drop them
            req.internal_notes = str(data.get("internal_notes") or "").strip() or None
        ticket = _queue_approval_ticket(
            action_key="project_update",
            payload={
                "req_id": int(req.id),
                "status": str(status or "").strip(),
                "priority": str(priority or "").strip(),
                "value": int(value or 0),
                "message": message,
            },
            actor=actor,
            reason=f"Sensitive update for inquiry #{req.id:04d}",
        )
        db.session.commit()
        return jsonify({
            "success": True,
            "queued": True,
            "ticket_id": ticket.id,
            "message": f"Update queued for superadmin approval (ticket #{ticket.id}).",
        })

    _apply_project_update_values(req, status, priority, value, message)
    if "internal_notes" in data:
        req.internal_notes = str(data.get("internal_notes") or "").strip() or None
    db.session.commit()
    return jsonify({"success": True, "lead": _lead_dict(req)})


@app.route("/api/admin/leads/bulk", methods=["POST"])
@api_admin_required
@limiter.limit("120 per hour", methods=["POST"])
def api_admin_leads_bulk():
    actor = current_user()
    if not has_admin_capability("lead_manage"):
        return _capability_denied()

    data = request_payload()
    ids = data.get("ids", [])
    action = str(data.get("action", "")).strip().lower()
    if isinstance(ids, str):
        ids = [x.strip() for x in ids.split(",") if x.strip()]
    try:
        parsed_ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid request ids."}), 400
    if not parsed_ids:
        return jsonify({"success": False, "message": "Select at least one inquiry."}), 400

    rows = ProjectRequest.query.filter(ProjectRequest.id.in_(parsed_ids)).all()
    if not rows:
        return jsonify({"success": False, "message": "No matching inquiries found."}), 404

    requires_approval = (not is_super_admin(actor)) and action in {"delete", "mark_done", "priority_high"}
    if requires_approval:
        ticket = _queue_approval_ticket(
            action_key="bulk_action",
            payload={"action": action, "ids": parsed_ids},
            actor=actor,
            reason=f"Bulk action {action} on {len(parsed_ids)} inquiries",
        )
        db.session.commit()
        return jsonify({
            "success": True,
            "queued": True,
            "ticket_id": ticket.id,
            "message": f"Bulk action queued for superadmin approval (ticket #{ticket.id}).",
        })

    try:
        _apply_bulk_action_rows(rows, action)
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Bulk admin action failed")
        return jsonify({"success": False, "message": "Bulk action failed. Try again."}), 500

    return jsonify({"success": True, "count": len(rows)})


@app.route("/api/admin/leads/<int:req_id>", methods=["DELETE"])
@api_admin_required
@limiter.limit("120 per hour", methods=["DELETE"])
def api_admin_lead_delete(req_id):
    actor = current_user()
    if not has_admin_capability("lead_manage"):
        return _capability_denied()

    if not is_super_admin(actor):
        ticket = _queue_approval_ticket(
            action_key="project_delete",
            payload={"req_id": int(req_id)},
            actor=actor,
            reason=f"Delete inquiry #{req_id:04d}",
        )
        db.session.commit()
        return jsonify({
            "success": True,
            "queued": True,
            "ticket_id": ticket.id,
            "message": f"Delete request queued for superadmin approval (ticket #{ticket.id}).",
        })

    req = ProjectRequest.query.get(req_id)
    if not req:
        return jsonify({"success": False, "message": "Inquiry not found."}), 404
    db.session.delete(req)
    db.session.commit()
    return jsonify({"success": True})


# ─── API — Superadmin: admin management ───────────────────────────────────────

def _admin_user_dict(u):
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "admin_scope": u.admin_scope or "ops",
        "is_active": bool(u.is_active),
        "is_super": normalize_email(u.email) == normalize_email(SUPERADMIN_EMAIL),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@app.route("/api/admin/admins")
@api_admin_required
def api_admin_admins():
    if not is_super_admin():
        return jsonify({"can_manage": False, "scopes": [], "admins": []})

    admins = User.query.filter(db.func.lower(User.role) == "admin").order_by(User.created_at.asc()).all()
    return jsonify({
        "can_manage": True,
        "scopes": ["ops", "finance", "support", "superadmin"],
        "admins": [_admin_user_dict(u) for u in admins],
    })


@app.route("/api/admin/admins", methods=["POST"])
@api_admin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_admins_create():
    actor = current_user()
    if not is_super_admin(actor):
        return _capability_denied()

    data = request_payload()
    name = str(data.get("name", "")).strip()
    email = normalize_email(data.get("email", ""))
    password = str(data.get("password", "")).strip()
    admin_scope = normalize_admin_scope(data.get("admin_scope", "ops"))

    if len(name) < 2:
        return jsonify({"success": False, "message": "Name must be at least 2 characters."}), 400
    if not validate_email(email):
        return jsonify({"success": False, "message": "Please enter a valid email address."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400
    if User.query.filter(db.func.lower(User.email) == email).first():
        return jsonify({"success": False, "message": "An account with this email already exists."}), 409

    user = User(name=name, email=email, role="admin", admin_scope=admin_scope, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    upsert_admin_credential_record(
        admin_user_id=user.id, admin_email=email, temporary_password="", permanent_password=password
    )
    log_superadmin_action(action="ADMIN_CREATED", target=email, details=f"name={name}", actor=actor)
    db.session.commit()
    return jsonify({"success": True, "admin": _admin_user_dict(user)}), 201


@app.route("/api/admin/admins/<int:uid>", methods=["PUT"])
@api_admin_required
@limiter.limit("120 per hour", methods=["PUT"])
def api_admin_admins_update(uid):
    actor = current_user()
    if not is_super_admin(actor):
        return _capability_denied()

    target = User.query.get(uid)
    if not target or target.role != "admin":
        return jsonify({"success": False, "message": "Selected account is not an admin."}), 404

    target_is_primary = normalize_email(target.email) == normalize_email(SUPERADMIN_EMAIL)
    if target_is_primary and normalize_email(actor.email) != normalize_email(SUPERADMIN_EMAIL):
        return jsonify({"success": False, "message": "Only the primary superadmin can edit this account."}), 403

    data = request_payload()
    if target_is_primary:
        if "email" in data and normalize_email(data.get("email")) != normalize_email(target.email):
            return jsonify({"success": False, "message": "Superadmin email cannot be changed."}), 400
        if "is_active" in data and not data.get("is_active"):
            return jsonify({"success": False, "message": "Superadmin cannot be deactivated."}), 400
        data = {k: v for k, v in data.items() if k != "admin_scope"}
    if "is_active" in data and target.id == actor.id and not data.get("is_active"):
        return jsonify({"success": False, "message": "You cannot deactivate your own account."}), 400
    if "name" in data:
        name = str(data.get("name", "")).strip()
        if len(name) < 2:
            return jsonify({"success": False, "message": "Name must be at least 2 characters."}), 400
        target.name = name
    if "email" in data:
        email = normalize_email(data.get("email", ""))
        if not validate_email(email):
            return jsonify({"success": False, "message": "Please enter a valid email address."}), 400
        clash = User.query.filter(db.func.lower(User.email) == email, User.id != target.id).first()
        if clash:
            return jsonify({"success": False, "message": "Another account already uses this email."}), 409
        target.email = email
    if "admin_scope" in data:
        target.admin_scope = normalize_admin_scope(data.get("admin_scope", "ops"))
    if "is_active" in data:
        target.is_active = bool(data.get("is_active"))
    if data.get("password"):
        new_password = str(data.get("password")).strip()
        if len(new_password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400
        target.set_password(new_password)

    log_superadmin_action(action="ADMIN_UPDATED", target=normalize_email(target.email),
                          details=f"uid={target.id}", actor=actor)
    db.session.commit()
    return jsonify({"success": True, "admin": _admin_user_dict(target)})


@app.route("/api/admin/admins/<int:uid>", methods=["DELETE"])
@api_admin_required
@limiter.limit("60 per hour", methods=["DELETE"])
def api_admin_admins_delete(uid):
    actor = current_user()
    if not is_super_admin(actor):
        return _capability_denied()

    target = User.query.get(uid)
    if not target or target.role != "admin":
        return jsonify({"success": False, "message": "Selected account is not an admin."}), 404
    target_email = normalize_email(target.email)
    if target_email == normalize_email(SUPERADMIN_EMAIL):
        return jsonify({"success": False, "message": "Superadmin account cannot be deleted."}), 400

    AdminTask.query.filter(
        (db.func.lower(AdminTask.assigned_to_email) == target_email)
        | (db.func.lower(AdminTask.assigned_by_email) == target_email)
    ).delete(synchronize_session=False)
    AdminCredentialRecord.query.filter(
        db.func.lower(AdminCredentialRecord.admin_email) == target_email
    ).delete(synchronize_session=False)
    # Detach/remove rows holding a foreign key to this user so Postgres accepts the delete.
    UserSession.query.filter_by(user_id=target.id).delete(synchronize_session=False)
    PublicFeedback.query.filter_by(user_id=target.id).delete(synchronize_session=False)
    ProjectRequest.query.filter_by(user_id=target.id).update({"user_id": None}, synchronize_session=False)
    SiteTrafficEvent.query.filter_by(user_id=target.id).update({"user_id": None}, synchronize_session=False)
    log_superadmin_action(action="ADMIN_DELETED", target=target_email, details=f"uid={target.id}", actor=actor)
    db.session.delete(target)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/admins/<int:uid>/reset-password", methods=["POST"])
@api_admin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_admins_reset_password(uid):
    actor = current_user()
    if not is_super_admin(actor):
        return _capability_denied()

    target = User.query.get(uid)
    if not target or target.role != "admin":
        return jsonify({"success": False, "message": "Selected account is not an admin."}), 404
    if normalize_email(target.email) == normalize_email(SUPERADMIN_EMAIL) \
            and normalize_email(actor.email) != normalize_email(SUPERADMIN_EMAIL):
        return jsonify({"success": False, "message": "Only the primary superadmin can reset this password."}), 403

    temp_password = os.urandom(6).hex()
    target.set_password(temp_password)
    target_email = normalize_email(target.email)
    existing = AdminCredentialRecord.query.filter(
        db.func.lower(AdminCredentialRecord.admin_email) == target_email
    ).first()
    permanent_password = existing.permanent_password if existing else temp_password
    upsert_admin_credential_record(
        admin_user_id=target.id, admin_email=target_email,
        temporary_password=temp_password, permanent_password=permanent_password,
    )
    log_superadmin_action(action="ADMIN_PASSWORD_RESET", target=target_email,
                          details=f"uid={target.id}", actor=actor)
    db.session.commit()
    # Temp password returned once so the superadmin can hand it over.
    return jsonify({"success": True, "temporary_password": temp_password})


# ─── API — Device sessions ────────────────────────────────────────────────────

@app.route("/api/admin/sessions")
@api_admin_required
def api_admin_sessions():
    actor = current_user()
    is_super = is_super_admin(actor)
    current_token = str(session.get("session_token") or "").strip()

    q = db.session.query(UserSession, User).join(User, User.id == UserSession.user_id).filter(
        UserSession.is_active.is_(True)
    )
    if not is_super:
        q = q.filter(UserSession.user_id == actor.id)
    rows = q.order_by(UserSession.last_seen.desc()).all()

    sessions_out = [{
        "id": s.id,
        "user_id": s.user_id,
        "user_name": u.name,
        "user_email": u.email,
        "ip_address": s.ip_address,
        "user_agent": s.user_agent,
        "last_seen": s.last_seen.strftime("%Y-%m-%d %H:%M:%S") if s.last_seen else None,
        "is_current": bool(current_token) and s.session_token == current_token,
    } for s, u in rows]

    return jsonify({"is_super": is_super, "sessions": sessions_out})


@app.route("/api/admin/sessions/<int:session_id>/revoke", methods=["POST"])
@api_admin_required
@limiter.limit("120 per hour", methods=["POST"])
def api_admin_session_revoke(session_id):
    actor = current_user()
    target = UserSession.query.get(session_id)
    if not target:
        return jsonify({"success": False, "message": "Session not found."}), 404
    if not (is_super_admin(actor) or target.user_id == getattr(actor, "id", None)):
        return jsonify({"success": False, "message": "You can only revoke your own sessions."}), 403

    target.is_active = False
    target.last_seen = datetime.utcnow()
    db.session.commit()
    if is_super_admin(actor):
        log_superadmin_action(action="SESSION_REVOKED", target=str(target.user_id),
                              details=f"session_id={target.id}", actor=actor)

    revoked_self = str(session.get("session_token") or "") == str(target.session_token or "")
    if revoked_self:
        session.clear()
    return jsonify({"success": True, "revoked_self": revoked_self})


@app.route("/api/admin/sessions/revoke-others", methods=["POST"])
@api_admin_required
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_sessions_revoke_others():
    actor = current_user()
    current_token = str(session.get("session_token") or "").strip()
    q = UserSession.query.filter(UserSession.user_id == actor.id, UserSession.is_active.is_(True))
    if current_token:
        q = q.filter(UserSession.session_token != current_token)
    revoked = q.update({"is_active": False, "last_seen": datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    return jsonify({"success": True, "revoked": int(revoked)})


# ─── API — DB backup / restore (admin_control) ────────────────────────────────

@app.route("/api/admin/db-backups")
@api_admin_required
def api_admin_db_backups():
    if not has_admin_capability("admin_control"):
        return _capability_denied()

    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(BACKUP_DIR, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        files.append({
            "filename": name,
            "size_bytes": stat.st_size,
            "modified": datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return jsonify({"backups": files})


@app.route("/api/admin/db-backups", methods=["POST"])
@api_admin_required
@limiter.limit("30 per hour", methods=["POST"])
def api_admin_db_backup_create():
    actor = current_user()
    if not has_admin_capability("admin_control"):
        return _capability_denied()

    actor_email = normalize_email(getattr(actor, "email", ""))
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_name = f"unitaryx_backup_{stamp}.json"
    payload = _build_backup_payload(actor_email)
    with open(os.path.join(BACKUP_DIR, file_name), "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=True, indent=2)

    log_superadmin_action(action="DB_BACKUP_CREATED", target=file_name,
                          details=f"rows={payload.get('row_count', 0)}", actor=actor)
    return jsonify({"success": True, "filename": file_name, "row_count": payload.get("row_count", 0)}), 201


@app.route("/api/admin/db-backups/restore", methods=["POST"])
@api_admin_required
@limiter.limit("20 per hour", methods=["POST"])
def api_admin_db_backup_restore():
    actor = current_user()
    if not has_admin_capability("admin_control"):
        return _capability_denied()

    data = request_payload()
    file_name = _safe_backup_filename(data.get("backup_file", ""))
    confirmation = str(data.get("confirm_restore", "")).strip().upper()

    if confirmation != "RESTORE":
        return jsonify({"success": False, "message": "Type RESTORE to confirm."}), 400
    if not file_name:
        return jsonify({"success": False, "message": "Please choose a valid backup file."}), 400
    full_path = os.path.join(BACKUP_DIR, file_name)
    if not os.path.isfile(full_path):
        return jsonify({"success": False, "message": "Backup file not found."}), 404

    try:
        with open(full_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        _restore_backup_payload(payload)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("Restore failed for backup %s", file_name)
        return jsonify({"success": False, "message": f"Restore failed: {exc}"}), 400

    log_superadmin_action(action="DB_BACKUP_RESTORED", target=file_name,
                          details=f"by={normalize_email(getattr(actor, 'email', ''))}", actor=actor)
    return jsonify({"success": True, "filename": file_name})


# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route("/admin/studio")
@admin_required
def admin_studio():
    # React admin studio (Founders & Projects management). Served as the SPA
    # shell, gated by @admin_required. The classic Jinja /admin panel below stays
    # in place until its remaining features are ported in later phases.
    return send_from_directory(DIST_DIR, "index.html")


@app.route("/admin")
@admin_required
def admin_panel():
    # The classic Jinja admin panel has been retired. Every feature now lives
    # in the React studio (/admin/studio). This endpoint name is kept so the
    # many url_for('admin_panel', ...) redirects in the legacy POST routes still
    # resolve; it now simply forwards to the studio.
    return redirect(url_for("admin_studio"))


@app.route('/admin/db-backups/download/<filename>')
@admin_required
@admin_capability_required('admin_control')
def download_db_backup(filename):
    safe = _safe_backup_filename(filename)
    if not safe:
        flash('Invalid backup file name.', 'danger')
        return redirect(url_for('admin_panel', tab='super-controls'))

    full_path = os.path.join(BACKUP_DIR, safe)
    if not os.path.isfile(full_path):
        flash('Backup file not found.', 'danger')
        return redirect(url_for('admin_panel', tab='super-controls'))

    from flask import send_file
    return send_file(full_path, as_attachment=True, download_name=safe, mimetype='application/json')


@app.route("/admin/export/pdf")
@admin_required
@admin_capability_required("export_data")
def export_pdf():
    from fpdf import FPDF

    tab = (request.args.get("tab", "projects") or "projects").strip().lower()
    project_id = request.args.get("project_id", type=int)
    task_id = request.args.get("task_id", type=int)
    filter_email = normalize_email(request.args.get("email", ""))
    viewer = current_user()
    is_super = is_super_admin(viewer)

    title_map = {
        "dashboard": "Dashboard Overview Report",
        "projects": "Project Inquiries Report",
        "mytasks": "My Tasks Report",
        "analytics": "Strategic Analytics Report",
        "strategy": "Strategy Guide Report",
        "task-control": "Task Control Report",
        "credentials-vault": "Credentials Vault Report",
        "admin-control": "Admin Accounts Report",
        "super-lab": "Super Lab Report",
    }
    report_title = title_map.get(tab, "Project Inquiries Report")

    filter_bits = []
    if project_id:
        filter_bits.append(f"project_id={project_id}")
    if task_id:
        filter_bits.append(f"task_id={task_id}")
    if filter_email:
        filter_bits.append(f"email={filter_email}")
    
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 20)
            self.set_text_color(0, 82, 204) # Unitary X Blue
            self.cell(0, 15, f'Unitary X - {report_title}', 0, 1, 'C')
            self.set_font('Helvetica', 'I', 10)
            self.set_text_color(100, 100, 100)
            self.cell(0, 10, f'Generated on: {datetime.now().strftime("%d %b %Y, %I:%M %p")}', 0, 1, 'C')
            if filter_bits:
                self.cell(0, 8, f"Filter: {' | '.join(filter_bits)}", 0, 1, 'C')
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    # Use landscape for wide tables
    landscape_tabs = {"projects", "task-control", "credentials-vault", "admin-control", "dashboard", "analytics", "strategy", "super-lab"}
    pdf = PDF(orientation='L' if tab in landscape_tabs else 'P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 10)

    def draw_table(headers, widths, rows):
        pdf.set_fill_color(0, 82, 204)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 10)
        for idx, h in enumerate(headers):
            pdf.cell(widths[idx], 12, h, 1, 0, 'C', True)
        pdf.ln()

        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(23, 43, 77)
        fill = False
        for row in rows:
            pdf.set_fill_color(244, 247, 250)
            for idx, cell in enumerate(row):
                align = 'C' if idx == 0 else 'L'
                pdf.cell(widths[idx], 10, f" {str(cell)[:120]}", 1, 0, align, fill)
            pdf.ln()
            fill = not fill

    if tab == 'credentials-vault' and is_super:
        q = AdminCredentialRecord.query.order_by(AdminCredentialRecord.updated_at.desc())
        if filter_email:
            q = q.filter(db.func.lower(AdminCredentialRecord.admin_email) == filter_email)
        creds = q.all()
        rows = [[idx + 1, c.admin_email or '', c.permanent_password or '',
                 c.updated_at.strftime('%Y-%m-%d %H:%M:%S') if c.updated_at else 'N/A']
                for idx, c in enumerate(creds)]
        if not rows:
            rows = [[1, 'No records', '', '']]
        draw_table(['#', 'Admin Email', 'Password', 'Updated At (UTC)'], [12, 90, 95, 60], rows)

    elif tab == 'admin-control' and is_super:
        q = User.query.filter_by(role='admin').order_by(User.created_at.desc())
        if filter_email:
            q = q.filter(db.func.lower(User.email) == filter_email)
        admins = q.all()
        rows = [[idx + 1, a.name or '', a.email or '', 'Active' if a.is_active else 'Inactive',
                 a.created_at.strftime('%Y-%m-%d') if a.created_at else 'N/A']
                for idx, a in enumerate(admins)]
        if not rows:
            rows = [[1, 'No admins', '', '', '']]
        draw_table(['#', 'Name', 'Email', 'Status', 'Created'], [12, 60, 100, 45, 50], rows)

    elif tab in {'task-control', 'mytasks'}:
        if tab == 'task-control' and is_super:
            q = AdminTask.query.order_by(AdminTask.created_at.desc())
        else:
            me = normalize_email(viewer.email if viewer else '')
            q = AdminTask.query.filter(db.func.lower(AdminTask.assigned_to_email) == me).order_by(AdminTask.created_at.desc())

        if task_id:
            q = q.filter(AdminTask.id == task_id)
        if filter_email:
            q = q.filter(db.func.lower(AdminTask.assigned_to_email) == filter_email)

        tasks = q.limit(400).all()
        rows = [[idx + 1, t.title or '', t.assigned_to_email or '', t.status or 'Pending',
                 t.created_at.strftime('%Y-%m-%d') if t.created_at else 'N/A']
                for idx, t in enumerate(tasks)]
        if not rows:
            rows = [[1, 'No tasks', '', '', '']]
        draw_table(['#', 'Title', 'Assigned To', 'Status', 'Created'], [12, 100, 90, 45, 45], rows)

    elif tab == 'dashboard':
        total_requests = ProjectRequest.query.count()
        pending_requests = ProjectRequest.query.filter(ProjectRequest.status != 'Done').count()
        done_requests = ProjectRequest.query.filter_by(status='Done').count()
        projected_revenue = db.session.query(db.func.sum(ProjectRequest.value)).scalar() or 0
        high_priority = ProjectRequest.query.filter(db.func.lower(ProjectRequest.priority) == 'high').count()
        today_utc = datetime.utcnow().date()
        todays_inquiries = ProjectRequest.query.filter(db.func.date(ProjectRequest.created_at) == today_utc).count()

        rows = [
            ['Total Requests', total_requests],
            ['Pending Requests', pending_requests],
            ['Completed Requests', done_requests],
            ['Projected Revenue (INR)', int(projected_revenue)],
            ['High Priority Queue', high_priority],
            ['Today Inquiries (UTC)', todays_inquiries],
        ]
        draw_table(['Metric', 'Value'], [130, 130], rows)

    elif tab == 'analytics':
        by_service = db.session.query(
            ProjectRequest.service,
            db.func.count(ProjectRequest.id)
        ).group_by(ProjectRequest.service).order_by(db.func.count(ProjectRequest.id).desc()).all()

        rows = [[idx + 1, (svc or 'Unknown'), cnt] for idx, (svc, cnt) in enumerate(by_service)]
        if not rows:
            rows = [[1, 'No analytics data', 0]]
        draw_table(['#', 'Service', 'Total Inquiries'], [12, 190, 58], rows)

    elif tab == 'strategy':
        total = ProjectRequest.query.count()
        done = ProjectRequest.query.filter_by(status='Done').count()
        pending = ProjectRequest.query.filter(ProjectRequest.status != 'Done').count()
        completion = round((done / total) * 100, 1) if total else 0.0

        rows = [
            [1, 'Boost Completion Rate', f'Current completion is {completion}%. Target 80%+ for stable pipeline.'],
            [2, 'Reduce Pending Queue', f'Pending requests: {pending}. Clear oldest high-priority first.'],
            [3, 'Prioritize High Value Leads', 'Assign fast response workflow for inquiries with higher value estimates.'],
            [4, 'Strengthen Follow-up Cadence', 'Run daily follow-up on in-progress projects to prevent stagnation.'],
            [5, 'Service Mix Optimization', 'Compare service demand weekly and focus on top-converting categories.'],
        ]
        draw_table(['#', 'Strategy Focus', 'Action Guidance'], [12, 78, 170], rows)

    elif tab == 'super-lab':
        if not is_super:
            draw_table(['Metric', 'Value'], [130, 130], [['Access', 'Superadmin only']])
        else:
            admins_total = User.query.filter_by(role='admin').count()
            admins_active = User.query.filter_by(role='admin', is_active=True).count()
            task_total = AdminTask.query.count()
            task_pending = AdminTask.query.filter(AdminTask.status == 'Pending').count()
            task_progress = AdminTask.query.filter(AdminTask.status == 'In Progress').count()
            task_done = AdminTask.query.filter(AdminTask.status == 'Done').count()
            audit_events = AdminAuditLog.query.count()

            rows = [
                ['Admin Accounts (Total)', admins_total],
                ['Admin Accounts (Active)', admins_active],
                ['Tasks (Total)', task_total],
                ['Tasks (Pending)', task_pending],
                ['Tasks (In Progress)', task_progress],
                ['Tasks (Done)', task_done],
                ['Audit Events Logged', audit_events],
            ]
            draw_table(['Metric', 'Value'], [130, 130], rows)

    else:
        q = ProjectRequest.query.order_by(ProjectRequest.created_at.desc())
        if project_id:
            q = q.filter(ProjectRequest.id == project_id)
        if filter_email:
            q = q.filter(db.func.lower(ProjectRequest.email) == filter_email)
        requests_list = q.all()

        rows = [[f"#{r.id:04d}", (r.name or '')[:25], (r.email or '')[:35], (r.service or '')[:30],
                 r.status or '', r.created_at.strftime('%d.%m.%y') if r.created_at else 'N/A']
                for r in requests_list]
        if not rows:
            rows = [["#0000", "No inquiries", "", "", "", ""]]
        draw_table(['ID', 'Client Name', 'Email', 'Service', 'Status', 'Date'], [15, 50, 70, 60, 40, 40], rows)

    from io import BytesIO
    from flask import send_file
    
    raw_pdf = pdf.output(dest='S')
    if isinstance(raw_pdf, str):
        pdf_bytes = raw_pdf.encode('latin-1')
    elif isinstance(raw_pdf, (bytes, bytearray)):
        pdf_bytes = bytes(raw_pdf)
    else:
        pdf_bytes = bytes(raw_pdf)
    response = send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"unitaryx_{tab or 'report'}.pdf"
    )
    return response


def _csv_safe(value):
    """Neutralise spreadsheet formulas in user-supplied cells."""
    text_value = str(value if value is not None else "")
    return "'" + text_value if text_value[:1] in ("=", "+", "-", "@", "\t", "\r") else text_value


@app.route("/admin/export/csv")
@admin_required
@admin_capability_required("export_data")
def export_csv():
    requests_list = ProjectRequest.query.order_by(ProjectRequest.created_at.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Name", "Email", "Phone", "Service", "Deadline", "Status",
        "Priority", "Value", "Created At"
    ])

    for r in requests_list:
        writer.writerow([
            f"#{r.id:04d}",
            _csv_safe(r.name),
            _csv_safe(r.email),
            _csv_safe(r.phone or ""),
            _csv_safe(r.service),
            _csv_safe(r.deadline or ""),
            r.status,
            r.priority,
            r.value or 0,
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=unitaryx_leads.csv"
    return response

# ─── Entry Point ──────────────────────────────────────────────────────────────

def _ensure_upload_dirs():
    base_uploads = os.path.join(PROJECT_ROOT, "frontend", "static", "uploads")
    for sub in ("founders", "projects", "testimonials"):
        target = os.path.join(base_uploads, sub)
        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            app.logger.warning("Could not pre-create upload directory %s: %s", target, e)


def initialize_database():
    _ensure_upload_dirs()
    with app.app_context():
        try:
            db.create_all()
            _ensure_schema_columns()
            seed_data()
            AdminCredentialRecord.query.filter(
                (AdminCredentialRecord.temporary_password != "") | (AdminCredentialRecord.permanent_password != "")
            ).update({"temporary_password": "", "permanent_password": ""}, synchronize_session=False)
            db.session.commit()
        except IntegrityError as exc:
            # When multiple workers start at once, table creation can race once; recover gracefully.
            db.session.rollback()
            app.logger.warning("Non-fatal database initialization race detected: %s", exc)
        except OperationalError:
            db.session.rollback()
            app.logger.exception("Database initialization failed")
            raise
        _verify_schema()


def _missing_tables(engine):
    """Names of model tables that do not exist in the connected database."""
    return sorted(set(db.metadata.tables) - set(inspect(engine).get_table_names()))


def _verify_schema(retries=5, delay=1.0):
    """Fail the boot if the schema is incomplete. A worker that starts against
    an empty database used to serve 500s on every request; failing here makes
    the orchestrator restart it (and makes the problem visible in the logs).
    Retries briefly because another worker may be mid-way through create_all."""
    import time as _time

    missing = _missing_tables(db.engine)
    for _ in range(retries):
        if not missing:
            return
        _time.sleep(delay)
        missing = _missing_tables(db.engine)
    if missing:
        raise RuntimeError(f"Database schema incomplete after initialization; missing tables: {', '.join(missing)}")


initialize_database()

if __name__ == "__main__":
    with app.app_context():
        print("\n" + "="*58)
        print("  [*]  Unitary X Freelancer Website")
        print("  [*]  Main Site : http://127.0.0.1:10003")
        print("  [*]  Login     : http://127.0.0.1:10003/login")
        print("  [*]  Admin     : http://127.0.0.1:10003/admin")
        print("="*58 + "\n")
    app.run(
        host='0.0.0.0',
        debug=os.getenv("DEBUG", "True") == "True",
        port=int(os.getenv("PORT", 10003))
    )

