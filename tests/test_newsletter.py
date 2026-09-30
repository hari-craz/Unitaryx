from datetime import datetime, timedelta

import pytest

import backend.app as appmod
from backend import mailers
from backend.app import Subscriber, db, app as flask_app


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    appmod.limiter.reset()
    with flask_app.app_context():
        Subscriber.query.delete()
        db.session.commit()
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    sent = []
    monkeypatch.setattr(appmod, "queue_newsletter_confirm_email", lambda **kw: sent.append(kw))
    return sent


@pytest.fixture
def sent(_reset):
    return _reset


def subscribe(client, email, **extra):
    return client.post("/api/newsletter/subscribe", json={"email": email, **extra})


def get_sub(email):
    with flask_app.app_context():
        s = Subscriber.query.filter_by(email=email).first()
        return s and {"confirmed": s.confirmed, "confirm": s.confirm_token, "unsub": s.unsub_token}


def test_subscribe_sends_confirmation_and_stays_unconfirmed(client, sent):
    resp = subscribe(client, "  New@Example.com ")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    sub = get_sub("new@example.com")
    assert sub and sub["confirmed"] is False
    assert len(sent) == 1
    assert sent[0]["recipient"] == "new@example.com"
    assert sent[0]["confirm_url"].endswith(f"/newsletter/confirm/{sub['confirm']}")


def test_invalid_email_rejected(client, sent):
    for bad in ["", "nope", "a@b", "a b@c.com", "x" * 200 + "@a.com"]:
        assert subscribe(client, bad).status_code == 400
    assert sent == []


def test_honeypot_is_silent_and_sends_nothing(client, sent):
    resp = subscribe(client, "bot@example.com", website="http://spam")
    assert resp.status_code == 200
    assert get_sub("bot@example.com") is None and sent == []


def test_reply_is_identical_for_existing_confirmed_address(client, sent):
    first = subscribe(client, "same@example.com").get_json()
    client.post("/api/newsletter/confirm", json={"token": get_sub("same@example.com")["confirm"]})
    sent.clear()
    again = subscribe(client, "same@example.com").get_json()
    assert first == again
    assert sent == []  # already confirmed: nothing is mailed


def test_resend_has_cooldown(client, sent):
    subscribe(client, "wait@example.com")
    subscribe(client, "wait@example.com")
    assert len(sent) == 1
    with flask_app.app_context():
        s = Subscriber.query.filter_by(email="wait@example.com").first()
        s.last_sent_at = datetime.utcnow() - timedelta(minutes=11)
        db.session.commit()
    subscribe(client, "wait@example.com")
    assert len(sent) == 2


def test_mail_failure_does_not_leak_and_allows_retry(client, monkeypatch):
    def boom(**kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(appmod, "queue_newsletter_confirm_email", boom)
    resp = subscribe(client, "fail@example.com")
    assert resp.status_code == 200
    with flask_app.app_context():
        assert Subscriber.query.filter_by(email="fail@example.com").first().last_sent_at is None


def test_confirm_requires_valid_token_and_is_post_only(client, sent):
    subscribe(client, "c@example.com")
    token = get_sub("c@example.com")["confirm"]
    assert client.get(f"/newsletter/confirm/{token}").status_code == 200  # page only
    assert get_sub("c@example.com")["confirmed"] is False  # a GET must not confirm
    assert client.post("/api/newsletter/confirm", json={"token": "short"}).status_code == 404
    assert client.post("/api/newsletter/confirm", json={"token": "x" * 40}).status_code == 404
    assert client.post("/api/newsletter/confirm", json={"token": token}).status_code == 200
    assert get_sub("c@example.com")["confirmed"] is True


def test_unsubscribe_deletes_row_and_is_idempotent(client, sent):
    subscribe(client, "u@example.com")
    unsub = get_sub("u@example.com")["unsub"]
    assert client.post("/api/newsletter/unsubscribe", json={"token": unsub}).status_code == 200
    assert get_sub("u@example.com") is None
    assert client.post("/api/newsletter/unsubscribe", json={"token": unsub}).status_code == 404


def test_action_pages_are_noindex(client):
    resp = client.get("/newsletter/unsubscribe/" + "a" * 43)
    assert resp.status_code == 200
    assert resp.headers["X-Robots-Tag"] == "noindex"


def test_subscribe_is_rate_limited(client, sent):
    codes = [subscribe(client, f"r{i}@example.com").status_code for i in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_admin_summary_and_export_are_superadmin_only(client, superadmin_client, sent):
    subscribe(superadmin_client, "one@example.com")
    subscribe(superadmin_client, "=evil@example.com")
    superadmin_client.post("/api/newsletter/confirm", json={"token": get_sub("=evil@example.com")["confirm"]})

    summary = superadmin_client.get("/api/admin/newsletter/summary").get_json()
    assert summary == {"confirmed": 1, "pending": 1}
    csv_text = superadmin_client.get("/api/admin/newsletter/export.csv").get_data(as_text=True)
    assert "'=evil@example.com" in csv_text and "one@example.com" not in csv_text

    anon = flask_app.test_client()
    assert anon.get("/api/admin/newsletter/summary").status_code in (401, 403)


def test_confirm_email_payload_english_and_hindi():
    subject, plain, html = mailers.build_newsletter_confirm_payload("https://x.test/newsletter/confirm/t", "en")
    assert "Confirm" in subject and "https://x.test/newsletter/confirm/t" in plain and "https://x.test" in html
    subject_hi, plain_hi, _ = mailers.build_newsletter_confirm_payload("https://x.test/c", "hi")
    assert "पुष्टि" in subject_hi and "नमस्ते" in plain_hi


def test_concurrent_insert_race_returns_generic_reply_without_duplicate_mail(client, sent, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    real_commit = db.session.commit
    calls = {"n": 0}

    def commit_once_raising():
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("insert", {}, Exception("duplicate key"))
        return real_commit()

    monkeypatch.setattr(db.session, "commit", commit_once_raising)
    resp = subscribe(client, "race@example.com")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    assert sent == []  # the request that lost the race sends nothing


def test_resend_claim_is_atomic(client, sent):
    subscribe(client, "claim@example.com")
    with flask_app.app_context():
        s = Subscriber.query.filter_by(email="claim@example.com").first()
        s.last_sent_at = datetime.utcnow() - timedelta(minutes=11)
        db.session.commit()
    subscribe(client, "claim@example.com")
    subscribe(client, "claim@example.com")  # second attempt lands inside the new cooldown
    assert len(sent) == 2


def test_confirmation_mail_is_sent_synchronously(monkeypatch):
    captured = {}
    monkeypatch.setattr(mailers, "_deliver", lambda *a, **kw: captured.update(kw))
    mailers.send_newsletter_confirm_email("a@b.co", "https://x.test/c", "from@x.test")
    assert captured.get("sync") is True
