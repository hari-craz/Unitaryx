"""Phase 5: tasks / finance / approvals JSON API coverage.

CLAUDE.md flags this phase as sensitive (finance + credential flows), so these
tests pin auth, CSRF and capability boundaries explicitly.
"""
import pytest

from backend.app import app as flask_app, db, User, FinanceEntry, AdminTask, ApprovalTicket


# ── auth / CSRF boundaries ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    ["/api/admin/tasks", "/api/admin/finance", "/api/admin/approvals"],
)
def test_workflow_endpoints_require_auth(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/api/admin/tasks", "/api/admin/finance", "/api/admin/approvals"],
)
def test_workflow_endpoints_reject_non_admin(client, path):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "user"
    assert client.get(path).status_code == 403


def test_task_create_requires_csrf(superadmin_client):
    resp = superadmin_client.post("/api/admin/tasks", json={"title": "No CSRF", "assigned_to_email": "x@y.com"})
    assert resp.status_code == 403


def test_finance_create_requires_csrf(superadmin_client):
    resp = superadmin_client.post("/api/admin/finance", json={"title": "No CSRF"})
    assert resp.status_code == 403


# ── tasks ─────────────────────────────────────────────────────────────────────

def test_only_superadmin_can_assign_tasks(admin_client):
    body = admin_client.get("/api/admin/tasks").get_json()
    assert body["can_assign"] is False
    resp = admin_client.post(
        "/api/admin/tasks",
        json={"title": "Ops cannot assign", "assigned_to_email": "admin@unitaryx.com"},
        headers=admin_client.csrf_headers,
    )
    assert resp.status_code == 403


def test_task_assign_validates_title_and_assignee(superadmin_client):
    short = superadmin_client.post(
        "/api/admin/tasks",
        json={"title": "ab", "assigned_to_email": "admin@unitaryx.com"},
        headers=superadmin_client.csrf_headers,
    )
    assert short.status_code == 400

    bad_assignee = superadmin_client.post(
        "/api/admin/tasks",
        json={"title": "Valid title", "assigned_to_email": "nobody@nowhere.com"},
        headers=superadmin_client.csrf_headers,
    )
    assert bad_assignee.status_code == 400


def test_task_assign_and_status_roundtrip(superadmin_client):
    resp = superadmin_client.post(
        "/api/admin/tasks",
        json={
            "title": "Review Q3 numbers",
            "details": "Check the finance ledger",
            "assigned_to_email": "admin@unitaryx.com",
        },
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 201
    task = resp.get_json()["task"]
    assert task["status"] == "Pending"

    upd = superadmin_client.put(
        f"/api/admin/tasks/{task['id']}/status",
        json={"status": "Done"},
        headers=superadmin_client.csrf_headers,
    )
    assert upd.status_code == 200
    assert upd.get_json()["task"]["status"] == "Done"

    bad = superadmin_client.put(
        f"/api/admin/tasks/{task['id']}/status",
        json={"status": "Cancelled"},
        headers=superadmin_client.csrf_headers,
    )
    assert bad.status_code == 400

    gone = superadmin_client.delete(
        f"/api/admin/tasks/{task['id']}", headers=superadmin_client.csrf_headers
    )
    assert gone.status_code == 200
    assert superadmin_client.delete(
        f"/api/admin/tasks/{task['id']}", headers=superadmin_client.csrf_headers
    ).status_code == 404


def test_task_assignment_never_fails_on_email_error(superadmin_client):
    """SMTP is unconfigured in tests; assignment must still succeed and simply
    report email_sent=False (mirrors the classic route's best-effort send)."""
    resp = superadmin_client.post(
        "/api/admin/tasks",
        json={"title": "Email should not block", "assigned_to_email": "admin@unitaryx.com"},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["email_sent"] is False


OPS = "admin@unitaryx.com"
SUPER = "harikavi1301@gmail.com"


def _assign(client, **body):
    return client.post("/api/admin/tasks", json=body, headers=client.csrf_headers)


def test_task_can_be_assigned_to_several_admins_at_once(superadmin_client):
    resp = _assign(superadmin_client, title="Prepare the demo", assigned_to_emails=[OPS, SUPER])
    assert resp.status_code == 201
    body = resp.get_json()
    assert {t["assigned_to_email"] for t in body["tasks"]} == {OPS, SUPER}
    assert body["task"]["assigned_to_email"] == OPS  # first one, for older clients

    listed = superadmin_client.get("/api/admin/tasks").get_json()["tasks"]
    assert sorted(t["assigned_to_email"] for t in listed) == sorted([OPS, SUPER])

    # Each assignee tracks their own status.
    ops_task = next(t for t in listed if t["assigned_to_email"] == OPS)
    resp = superadmin_client.put(
        f"/api/admin/tasks/{ops_task['id']}/status", json={"status": "Done"}, headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 200
    statuses = {t["assigned_to_email"]: t["status"] for t in superadmin_client.get("/api/admin/tasks").get_json()["tasks"]}
    assert statuses == {OPS: "Done", SUPER: "Pending"}


def test_multi_assign_dedupes_and_normalises_emails(superadmin_client):
    resp = _assign(superadmin_client, title="Dedupe me", assigned_to_emails=[OPS, OPS.upper(), f" {OPS} "])
    assert resp.status_code == 201
    assert len(resp.get_json()["tasks"]) == 1


def test_multi_assign_is_all_or_nothing(superadmin_client):
    resp = _assign(superadmin_client, title="Partly bad", assigned_to_emails=[OPS, "nobody@nowhere.com"])
    assert resp.status_code == 400
    assert "nobody@nowhere.com" in resp.get_json()["message"]
    assert superadmin_client.get("/api/admin/tasks").get_json()["tasks"] == []


def test_multi_assign_rejects_empty_and_oversized_lists(superadmin_client):
    assert _assign(superadmin_client, title="Nobody", assigned_to_emails=[]).status_code == 400
    assert _assign(superadmin_client, title="Nobody", assigned_to_emails=["", "  "]).status_code == 400
    too_many = [f"admin{i}@unitaryx.com" for i in range(26)]
    assert _assign(superadmin_client, title="Too many", assigned_to_emails=too_many).status_code == 400
    assert _assign(superadmin_client, title="Wrong type", assigned_to_emails={"a": 1}).status_code == 400


def test_multi_assign_reports_which_notifications_failed(superadmin_client):
    resp = _assign(superadmin_client, title="Report me", assigned_to_emails=[OPS, SUPER])
    body = resp.get_json()
    assert body["email_sent"] is False  # SMTP is unconfigured in tests
    assert sorted(body["emails_failed"]) == sorted([OPS, SUPER])


def test_non_superadmin_only_sees_own_tasks(superadmin_client):
    """Uses a single client and switches the session, since both admin fixtures
    share one client and would otherwise clobber each other's session."""
    client = superadmin_client
    # superadmin assigns one task to the ops admin and one to itself
    for target in ("admin@unitaryx.com", "harikavi1301@gmail.com"):
        client.post(
            "/api/admin/tasks",
            json={"title": f"Task for {target}", "assigned_to_email": target},
            headers=client.csrf_headers,
        )
    assert len(client.get("/api/admin/tasks").get_json()["tasks"]) == 2  # superadmin sees all

    # Switch the same client to the ops admin (id 1). session_token must be
    # dropped too: enforce_active_user_session binds the token to a user, so
    # reusing the superadmin's token under a different user_id is (correctly)
    # rejected and redirected to /login.
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "admin"
        sess.pop("session_token", None)
    body = client.get("/api/admin/tasks").get_json()
    assert body["can_assign"] is False
    assert [t["assigned_to_email"] for t in body["tasks"]] == ["admin@unitaryx.com"]


# ── finance ───────────────────────────────────────────────────────────────────

def test_finance_requires_finance_ops_capability(client):
    """A 'support'-scope admin has neither finance_ops nor admin_control."""
    with flask_app.app_context():
        u = User(name="Support", email="support@example.com", password="x",
                 role="admin", admin_scope="support")
        db.session.add(u)
        db.session.commit()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
    assert client.get("/api/admin/finance").status_code == 403


def test_finance_create_validates(superadmin_client):
    for payload, _reason in [
        ({"title": "ab", "counterparty": "Acme", "amount": 100}, "short title"),
        ({"title": "Valid title", "counterparty": "A", "amount": 100}, "short counterparty"),
        ({"title": "Valid title", "counterparty": "Acme", "amount": 0}, "zero amount"),
    ]:
        resp = superadmin_client.post(
            "/api/admin/finance", json=payload, headers=superadmin_client.csrf_headers
        )
        assert resp.status_code == 400


def test_finance_requires_configured_finance_admins(superadmin_client):
    """With no scope=finance admins seeded, creation is refused exactly like the
    classic route ('Assign two active finance admins first')."""
    resp = superadmin_client.post(
        "/api/admin/finance",
        json={"title": "Server invoice", "counterparty": "Acme Ltd", "amount": 5000},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 400
    assert "finance admins" in resp.get_json()["message"].lower()


def test_finance_full_lifecycle_with_superadmin_review(superadmin_client):
    with flask_app.app_context():
        for i in (1, 2):
            db.session.add(User(name=f"Fin{i}", email=f"fin{i}@example.com", password="x",
                                role="admin", admin_scope="finance"))
        db.session.commit()

    created = superadmin_client.post(
        "/api/admin/finance",
        json={"title": "Server invoice", "counterparty": "Acme Ltd", "amount": 5000,
              "entry_type": "receivable"},
        headers=superadmin_client.csrf_headers,
    )
    assert created.status_code == 201
    entry = created.get_json()["entry"]
    assert entry["status"] == "submitted"
    assert entry["assigned_admin_email"] == "fin1@example.com"

    # escalate into the superadmin queue
    esc = superadmin_client.put(
        f"/api/admin/finance/{entry['id']}/status",
        json={"status": "needs_superadmin_check"},
        headers=superadmin_client.csrf_headers,
    )
    assert esc.status_code == 200

    # invalid status rejected
    assert superadmin_client.put(
        f"/api/admin/finance/{entry['id']}/status",
        json={"status": "banana"},
        headers=superadmin_client.csrf_headers,
    ).status_code == 400

    reviewed = superadmin_client.put(
        f"/api/admin/finance/{entry['id']}/review",
        json={"decision": "approve", "review_note": "Looks good"},
        headers=superadmin_client.csrf_headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.get_json()["entry"]["status"] == "closed"


def test_finance_review_rejects_entry_not_in_queue(superadmin_client):
    with flask_app.app_context():
        db.session.add(User(name="Fin", email="finonly@example.com", password="x",
                            role="admin", admin_scope="finance"))
        db.session.commit()
        e = FinanceEntry(entry_type="payable", title="Hosting", counterparty="Vendor",
                         amount=100, status="submitted",
                         assigned_admin_email="finonly@example.com",
                         created_by_email="finonly@example.com")
        db.session.add(e)
        db.session.commit()
        eid = e.id

    resp = superadmin_client.put(
        f"/api/admin/finance/{eid}/review",
        json={"decision": "approve"},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 400


# ── approvals ─────────────────────────────────────────────────────────────────

def test_approvals_readable_by_admin_but_only_superadmin_reviews(admin_client):
    body = admin_client.get("/api/admin/approvals").get_json()
    assert body["can_review"] is False
    with flask_app.app_context():
        t = ApprovalTicket(action_key="delete_user", payload_json="{}",
                           requested_by_email="ops@example.com", requested_by_scope="ops",
                           status="pending")
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = admin_client.post(
        f"/api/admin/approvals/{tid}/approve", json={}, headers=admin_client.csrf_headers
    )
    assert resp.status_code == 403


def test_approval_reject_flow(superadmin_client):
    with flask_app.app_context():
        t = ApprovalTicket(action_key="delete_user", payload_json="{}",
                           requested_by_email="ops@example.com", requested_by_scope="ops",
                           status="pending")
        db.session.add(t)
        db.session.commit()
        tid = t.id

    resp = superadmin_client.post(
        f"/api/admin/approvals/{tid}/reject",
        json={"review_note": "Not justified"},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 200
    ticket = resp.get_json()["ticket"]
    assert ticket["status"] == "rejected"
    assert ticket["review_note"] == "Not justified"

    # already reviewed -> rejected again should fail
    again = superadmin_client.post(
        f"/api/admin/approvals/{tid}/reject", json={}, headers=superadmin_client.csrf_headers
    )
    assert again.status_code == 400


def test_approval_invalid_decision(superadmin_client):
    resp = superadmin_client.post(
        "/api/admin/approvals/1/maybe", json={}, headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 400
