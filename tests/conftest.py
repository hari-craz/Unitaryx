import os
import tempfile

import pytest

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
# The app walks up the tree to load a real .env for local/worktree runs; that
# would pull real SMTP creds (and other prod values) into the test process and
# let mail-sending tests hit live SMTP. Tests must use only the env set here.
os.environ["UNITARYX_SKIP_DOTENV_WALKUP"] = "1"
# The repo-root .env is still loaded; blank mail/broker settings so tests never
# reach live SMTP or a Redis broker (an empty value wins over load_dotenv).
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"  # never share a Redis limiter store with tests
for _name in ("SMTP_USER", "SMTP_PASS", "SMTP_FROM", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
    os.environ[_name] = ""

from backend.app import (  # noqa: E402  (must import after env vars are set)
    ABTestEvent,
    app as flask_app,
    db,
    AdminTask,
    ApprovalTicket,
    FinanceEntry,
    Founder,
    Project,
    ProjectRequest,
    User,
)


@pytest.fixture(autouse=True)
def _clean_tables():
    with flask_app.app_context():
        Founder.query.delete()
        Project.query.delete()
        ABTestEvent.query.delete()
        ProjectRequest.query.delete()
        AdminTask.query.delete()
        FinanceEntry.query.delete()
        ApprovalTicket.query.delete()
        # Remove any test-created users (incl. finance/support admins), but keep
        # the seeded ops admin (id 1) and superadmin (id 2) the fixtures rely on.
        User.query.filter(User.id > 2).delete()
        db.session.commit()
    yield


@pytest.fixture
def client():
    flask_app.config["TESTING"] = False  # keep real CSRF validation active in tests
    return flask_app.test_client()


@pytest.fixture
def admin_client(client):
    """A plain 'ops'-scope admin: has analytics_view/export_data but NOT
    admin_control (superadmin-only actions must reject this client)."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "admin"
    token = client.get("/api/csrf-token").get_json()["token"]
    client.csrf_headers = {"X-CSRFToken": token}
    return client


@pytest.fixture
def superadmin_client(client):
    """The seeded SUPERADMIN_EMAIL account (id 2), which is superadmin by email —
    required for admin_control actions such as editing A/B tests. Deliberately
    selects an existing account rather than mutating the ops admin, so these
    fixtures stay independent of test execution order."""
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["role"] = "admin"
    token = client.get("/api/csrf-token").get_json()["token"]
    client.csrf_headers = {"X-CSRFToken": token}
    return client
