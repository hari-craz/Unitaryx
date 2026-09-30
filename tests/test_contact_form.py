import pytest

import backend.app as appmod
from backend.app import ProjectRequest, db, app as flask_app

GOOD = {
    "name": "Asha Rao",
    "email": "asha@example.com",
    "phone": "9876543210",
    "service": "web",
    "deadline": "6 weeks",
    "message": "I need a small e-commerce site for my shop with online payments.",
}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    appmod.limiter.reset()
    # Never talk to real SMTP from tests.
    monkeypatch.setattr(appmod, "_smtp_send_message", lambda msg: None)
    monkeypatch.setenv("SMTP_FROM", "")
    with flask_app.app_context():
        ProjectRequest.query.delete()
        db.session.commit()


def post(client, **overrides):
    return client.post("/api/contact", json={**GOOD, **overrides})


def rows():
    with flask_app.app_context():
        return ProjectRequest.query.all()


def test_anonymous_visitor_can_submit_without_login(client):
    resp = post(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["success"] is True and "Asha Rao" in body["message"]
    assert "dashboard" not in body["message"]
    (row,) = rows()
    assert row.user_id is None and row.email == "asha@example.com" and row.service == "web"


def test_signed_in_request_is_linked_to_the_account(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "admin"
    resp = post(client)
    assert resp.status_code == 201 and "dashboard" in resp.get_json()["message"]
    assert rows()[0].user_id == 1


@pytest.mark.parametrize(
    "field,value",
    [("name", ""), ("email", "not-an-email"), ("service", "cooking"), ("service", ""), ("message", "too short")],
)
def test_validation_errors(client, field, value):
    resp = post(client, **{field: value})
    assert resp.status_code == 400 and field in resp.get_json()["errors"]
    assert rows() == []


@pytest.mark.parametrize("field", ["name", "phone", "deadline", "message"])
def test_overlong_input_is_rejected_not_a_server_error(client, field):
    resp = post(client, **{field: "x" * 5000})
    assert resp.status_code == 400 and field in resp.get_json()["errors"]
    assert rows() == []


def test_hosting_is_an_accepted_service(client):
    assert post(client, service="Hosting").status_code == 201
    assert rows()[0].service == "hosting"


def test_honeypot_looks_successful_but_stores_nothing(client):
    resp = post(client, website="http://spam.example")
    assert resp.status_code == 201
    assert rows() == []


def test_newline_in_name_cannot_break_the_notification_subject(client, monkeypatch):
    sent = []
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setattr(appmod, "_smtp_send_message", lambda msg: sent.append(msg))

    import threading

    RealThread = threading.Thread

    class InlineNotificationThread(RealThread):
        """Runs the app's notification synchronously; every other thread is untouched."""

        def start(self):
            if getattr(self._target, "__name__", "") == "send_notification":
                self._target()
            else:
                super().start()

    monkeypatch.setattr(threading, "Thread", InlineNotificationThread)
    assert post(client, name="Eve\r\nBcc: attacker@example.com").status_code == 201
    assert len(sent) == 1
    assert "\n" not in sent[0]["Subject"] and sent[0]["Bcc"] is None


def test_contact_is_rate_limited(client):
    codes = [post(client).status_code for _ in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429
