"""Admin newsletter: subscriber management and writing/sending campaigns."""
from datetime import datetime, timedelta

import pytest

import backend.app as appmod
from backend import mailers
from backend.app import Newsletter, NewsletterDelivery, Subscriber, db, app as flask_app

SUPER_EMAIL = "harikavi1301@gmail.com"
BODY = "Here is what we shipped this month.\n\nRead the details at https://example.com/changelog."


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    appmod.limiter.reset()
    with flask_app.app_context():
        NewsletterDelivery.query.delete()
        Newsletter.query.delete()
        Subscriber.query.delete()
        db.session.commit()
    monkeypatch.setenv("SMTP_USER", "mailer@example.test")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setattr(appmod, "NEWSLETTER_BACKGROUND", False)
    monkeypatch.setattr(appmod, "NEWSLETTER_SEND_DELAY", 0)
    confirmations = []
    monkeypatch.setattr(appmod, "queue_newsletter_confirm_email", lambda **kw: confirmations.append(kw))
    return confirmations


@pytest.fixture
def confirmations(_setup):
    return _setup


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(
        appmod, "send_newsletter_message",
        lambda recipient, subject, plain, html, sender, unsubscribe_url: sent.append(
            {"to": recipient, "subject": subject, "plain": plain, "html": html, "unsub": unsubscribe_url}
        ),
    )
    return sent


def add_sub(email, confirmed=True, minutes_ago=0):
    with flask_app.app_context():
        sub = Subscriber(
            email=email,
            confirmed=confirmed,
            confirm_token=f"c-{email}-{'x' * 30}",
            unsub_token=f"u-{email}-{'y' * 30}",
            created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
            confirmed_at=datetime.utcnow() if confirmed else None,
            last_sent_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(sub)
        db.session.commit()
        return sub.id


def make_campaign(client, **overrides):
    payload = {"subject": "October update", "body": BODY}
    payload.update(overrides)
    return client.post("/api/admin/newsletter/campaigns", json=payload, headers=client.csrf_headers)


def send(client, campaign_id, **body):
    return client.post(
        f"/api/admin/newsletter/campaigns/{campaign_id}/send",
        json={"confirm": True, **body},
        headers=client.csrf_headers,
    )


# ── subscribers ───────────────────────────────────────────────────────────────

def test_subscriber_list_filters_searches_and_hides_tokens(superadmin_client):
    add_sub("alice@example.com", confirmed=True, minutes_ago=3)
    add_sub("bob@example.com", confirmed=False, minutes_ago=2)
    add_sub("carol@example.org", confirmed=True, minutes_ago=1)

    body = superadmin_client.get("/api/admin/newsletter/subscribers").get_json()
    assert [s["email"] for s in body["subscribers"]] == ["carol@example.org", "bob@example.com", "alice@example.com"]
    assert body["confirmed"] == 2 and body["pending"] == 1 and body["total"] == 3
    assert all(set(s) == {"id", "email", "confirmed", "created_at", "confirmed_at"} for s in body["subscribers"])

    pending = superadmin_client.get("/api/admin/newsletter/subscribers?status=pending").get_json()
    assert [s["email"] for s in pending["subscribers"]] == ["bob@example.com"]

    found = superadmin_client.get("/api/admin/newsletter/subscribers?q=EXAMPLE.ORG").get_json()
    assert [s["email"] for s in found["subscribers"]] == ["carol@example.org"]


def test_subscriber_search_treats_wildcards_literally(superadmin_client):
    add_sub("alice@example.com")
    assert superadmin_client.get("/api/admin/newsletter/subscribers?q=%25").get_json()["total"] == 0
    assert superadmin_client.get("/api/admin/newsletter/subscribers?q=_").get_json()["total"] == 0


def test_subscriber_list_is_paged(superadmin_client):
    for i in range(30):
        add_sub(f"user{i:02d}@example.com", minutes_ago=i)
    first = superadmin_client.get("/api/admin/newsletter/subscribers").get_json()
    second = superadmin_client.get("/api/admin/newsletter/subscribers?page=2").get_json()
    assert len(first["subscribers"]) == 25 and len(second["subscribers"]) == 5
    assert first["total"] == 30 and second["page"] == 2


def test_adding_a_subscriber_sends_confirmation_and_stays_pending(superadmin_client, confirmations):
    resp = superadmin_client.post(
        "/api/admin/newsletter/subscribers", json={"email": "  New@Example.com "}, headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["subscriber"]["email"] == "new@example.com" and body["subscriber"]["confirmed"] is False
    assert body["email_sent"] is True
    assert len(confirmations) == 1 and confirmations[0]["recipient"] == "new@example.com"


def test_add_cannot_mark_anyone_confirmed(superadmin_client):
    resp = superadmin_client.post(
        "/api/admin/newsletter/subscribers",
        json={"email": "sneaky@example.com", "confirmed": True},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.get_json()["subscriber"]["confirmed"] is False


def test_add_validates_and_rejects_duplicates(superadmin_client):
    headers = superadmin_client.csrf_headers
    for bad in ("", "nope", "a@b", "x" * 200 + "@a.com"):
        assert superadmin_client.post(
            "/api/admin/newsletter/subscribers", json={"email": bad}, headers=headers
        ).status_code == 400

    add_sub("done@example.com", confirmed=True)
    resp = superadmin_client.post("/api/admin/newsletter/subscribers", json={"email": "done@example.com"}, headers=headers)
    assert resp.status_code == 409


def test_add_keeps_the_row_when_the_email_cannot_be_sent(superadmin_client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(appmod, "queue_newsletter_confirm_email", boom)
    resp = superadmin_client.post(
        "/api/admin/newsletter/subscribers", json={"email": "later@example.com"}, headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 201 and resp.get_json()["email_sent"] is False
    assert superadmin_client.get("/api/admin/newsletter/subscribers").get_json()["pending"] == 1


def test_resend_respects_cooldown_and_confirmed_state(superadmin_client, confirmations):
    headers = superadmin_client.csrf_headers
    pending_id = add_sub("p@example.com", confirmed=False)
    done_id = add_sub("d@example.com", confirmed=True)

    assert superadmin_client.post(f"/api/admin/newsletter/subscribers/{done_id}/resend", headers=headers).status_code == 409
    assert superadmin_client.post("/api/admin/newsletter/subscribers/9999/resend", headers=headers).status_code == 404

    assert superadmin_client.post(f"/api/admin/newsletter/subscribers/{pending_id}/resend", headers=headers).status_code == 200
    assert len(confirmations) == 1
    assert superadmin_client.post(f"/api/admin/newsletter/subscribers/{pending_id}/resend", headers=headers).status_code == 429
    assert len(confirmations) == 1


def test_remove_subscriber(superadmin_client):
    headers = superadmin_client.csrf_headers
    sub_id = add_sub("gone@example.com")
    assert superadmin_client.delete(f"/api/admin/newsletter/subscribers/{sub_id}", headers=headers).status_code == 200
    assert superadmin_client.delete(f"/api/admin/newsletter/subscribers/{sub_id}", headers=headers).status_code == 404
    assert superadmin_client.get("/api/admin/newsletter/subscribers").get_json()["total"] == 0


# ── writing ──────────────────────────────────────────────────────────────────

def test_campaign_create_update_delete(superadmin_client):
    headers = superadmin_client.csrf_headers
    created = make_campaign(superadmin_client)
    assert created.status_code == 201
    nl = created.get_json()["campaign"]
    assert nl["status"] == "draft" and nl["body"] == BODY.strip()

    resp = superadmin_client.put(
        f"/api/admin/newsletter/campaigns/{nl['id']}",
        json={"subject": "Renamed", "cta_label": "Read more", "cta_url": "https://example.com/post"},
        headers=headers,
    )
    assert resp.status_code == 200
    updated = resp.get_json()["campaign"]
    assert updated["subject"] == "Renamed" and updated["cta_label"] == "Read more"
    assert updated["body"] == BODY.strip()

    assert superadmin_client.delete(f"/api/admin/newsletter/campaigns/{nl['id']}", headers=headers).status_code == 200
    assert superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl['id']}").status_code == 404


def test_campaign_validation(superadmin_client):
    assert make_campaign(superadmin_client, subject="ab").status_code == 400
    assert make_campaign(superadmin_client, subject="x" * 151).status_code == 400
    assert make_campaign(superadmin_client, subject="Line one\nBcc: evil@example.com").status_code == 400
    assert make_campaign(superadmin_client, body="too short").status_code == 400
    assert make_campaign(superadmin_client, body="x" * 20001).status_code == 400
    assert make_campaign(superadmin_client, cta_label="Read").status_code == 400  # label without link
    assert make_campaign(superadmin_client, cta_url="https://example.com").status_code == 400  # link without label
    assert make_campaign(superadmin_client, cta_label="Go", cta_url="javascript:alert(1)").status_code == 400
    assert make_campaign(superadmin_client, cta_label="x" * 41, cta_url="https://example.com").status_code == 400
    assert make_campaign(superadmin_client, cta_label="Go", cta_url="https://example.com").status_code == 201


def test_preview_escapes_markup_and_links_urls(superadmin_client):
    resp = superadmin_client.post(
        "/api/admin/newsletter/campaigns/preview",
        json={"subject": "Hello <b>there</b>", "body": "Careful <script>alert(1)</script> text and https://example.com/a?x=1&y=2."},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 200
    html = resp.get_json()["html"]
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'href="https://example.com/a?x=1&amp;y=2"' in html


def test_only_drafts_can_be_edited(superadmin_client, outbox):
    add_sub("a@example.com")
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    assert send(superadmin_client, nl_id).status_code == 202
    resp = superadmin_client.put(
        f"/api/admin/newsletter/campaigns/{nl_id}", json={"subject": "Too late"}, headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 409


# ── test send ────────────────────────────────────────────────────────────────

def test_test_send_goes_only_to_the_signed_in_admin(superadmin_client, outbox):
    add_sub("subscriber@example.com")
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    resp = superadmin_client.post(f"/api/admin/newsletter/campaigns/{nl_id}/test", headers=superadmin_client.csrf_headers)
    assert resp.status_code == 200 and resp.get_json()["sent_to"] == SUPER_EMAIL
    assert [m["to"] for m in outbox] == [SUPER_EMAIL]
    assert outbox[0]["subject"] == "[Test] October update"


def test_test_send_needs_email_configured(superadmin_client, outbox, monkeypatch):
    monkeypatch.setenv("SMTP_PASS", "")
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    resp = superadmin_client.post(f"/api/admin/newsletter/campaigns/{nl_id}/test", headers=superadmin_client.csrf_headers)
    assert resp.status_code == 400 and outbox == []


# ── sending ──────────────────────────────────────────────────────────────────

def test_send_reaches_only_confirmed_subscribers_with_their_own_unsubscribe_link(superadmin_client, outbox):
    add_sub("one@example.com")
    add_sub("two@example.com")
    add_sub("pending@example.com", confirmed=False)
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]

    resp = send(superadmin_client, nl_id)
    assert resp.status_code == 202 and resp.get_json()["recipients"] == 2

    assert sorted(m["to"] for m in outbox) == ["one@example.com", "two@example.com"]
    links = {m["to"]: m["unsub"] for m in outbox}
    assert links["one@example.com"] != links["two@example.com"]
    for message in outbox:
        assert message["unsub"] in message["plain"] and message["unsub"].replace("&", "&amp;") in message["html"]
        assert "/newsletter/unsubscribe/" in message["unsub"]

    nl = superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl_id}").get_json()["campaign"]
    assert nl["status"] == "sent" and nl["sent_count"] == 2 and nl["failed_count"] == 0 and nl["sent_at"]


def test_send_requires_explicit_confirmation_and_subscribers(superadmin_client, outbox):
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    headers = superadmin_client.csrf_headers
    url = f"/api/admin/newsletter/campaigns/{nl_id}/send"
    assert superadmin_client.post(url, json={}, headers=headers).status_code == 400
    assert superadmin_client.post(url, json={"confirm": "yes"}, headers=headers).status_code == 400
    assert send(superadmin_client, nl_id).status_code == 400  # nobody has confirmed yet
    assert outbox == []
    assert superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl_id}").get_json()["campaign"]["status"] == "draft"


def test_a_newsletter_can_only_be_sent_once(superadmin_client, outbox):
    add_sub("a@example.com")
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    assert send(superadmin_client, nl_id).status_code == 202
    assert send(superadmin_client, nl_id).status_code == 409
    assert len(outbox) == 1


def test_send_is_refused_above_the_recipient_limit(superadmin_client, outbox, monkeypatch):
    monkeypatch.setattr(appmod, "NEWSLETTER_MAX_RECIPIENTS", 1)
    add_sub("a@example.com")
    add_sub("b@example.com")
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    resp = send(superadmin_client, nl_id)
    assert resp.status_code == 400 and "safety limit" in resp.get_json()["message"]
    assert outbox == []
    assert superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl_id}").get_json()["campaign"]["status"] == "draft"


def test_send_needs_email_configured(superadmin_client, outbox, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_FROM", "")
    add_sub("a@example.com")
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    assert send(superadmin_client, nl_id).status_code == 400


def test_one_failed_delivery_does_not_stop_the_rest(superadmin_client, monkeypatch):
    delivered = []

    def flaky(recipient, subject, plain, html, sender, unsubscribe_url):
        if recipient == "bad@example.com":
            raise RuntimeError("mailbox full")
        delivered.append(recipient)

    monkeypatch.setattr(appmod, "send_newsletter_message", flaky)
    for email in ("a@example.com", "bad@example.com", "c@example.com"):
        add_sub(email)
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    assert send(superadmin_client, nl_id).status_code == 202

    nl = superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl_id}").get_json()["campaign"]
    assert sorted(delivered) == ["a@example.com", "c@example.com"]
    assert nl["status"] == "sent" and nl["sent_count"] == 2 and nl["failed_count"] == 1
    with flask_app.app_context():
        failed = NewsletterDelivery.query.filter_by(newsletter_id=nl_id, status="failed").one()
        assert failed.email == "bad@example.com" and failed.error == "RuntimeError"


def test_someone_who_unsubscribes_mid_send_is_skipped(superadmin_client, monkeypatch):
    delivered = []
    ids = {email: add_sub(email) for email in ("first@example.com", "second@example.com")}

    def send_and_unsubscribe_the_other(recipient, subject, plain, html, sender, unsubscribe_url):
        delivered.append(recipient)
        if recipient == "first@example.com":
            with flask_app.app_context():
                Subscriber.query.filter_by(id=ids["second@example.com"]).delete()
                db.session.commit()

    monkeypatch.setattr(appmod, "send_newsletter_message", send_and_unsubscribe_the_other)
    nl_id = make_campaign(superadmin_client).get_json()["campaign"]["id"]
    assert send(superadmin_client, nl_id).status_code == 202

    assert delivered == ["first@example.com"]
    nl = superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl_id}").get_json()["campaign"]
    assert nl["sent_count"] == 1 and nl["skipped_count"] == 1 and nl["status"] == "sent"


def test_a_stalled_send_can_be_resumed_without_mailing_anyone_twice(superadmin_client, outbox):
    add_sub("done@example.com")
    add_sub("waiting@example.com")
    with flask_app.app_context():
        nl = Newsletter(
            subject="Interrupted", body=BODY, status="sending", created_by=SUPER_EMAIL,
            recipients_total=2, updated_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db.session.add(nl)
        db.session.flush()
        db.session.add(NewsletterDelivery(newsletter_id=nl.id, email="done@example.com", status="sent"))
        db.session.add(NewsletterDelivery(newsletter_id=nl.id, email="waiting@example.com", status="pending"))
        db.session.commit()
        nl_id = nl.id
        db.session.query(Newsletter).filter_by(id=nl_id).update(
            {"updated_at": datetime.utcnow() - timedelta(minutes=10)}, synchronize_session=False
        )
        db.session.commit()

    listed = superadmin_client.get("/api/admin/newsletter/campaigns").get_json()["campaigns"]
    assert listed[0]["stalled"] is True

    resp = superadmin_client.post(
        f"/api/admin/newsletter/campaigns/{nl_id}/resume", headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 202
    assert [m["to"] for m in outbox] == ["waiting@example.com"]
    nl = superadmin_client.get(f"/api/admin/newsletter/campaigns/{nl_id}").get_json()["campaign"]
    assert nl["status"] == "sent" and nl["sent_count"] == 2


def test_resume_is_refused_unless_the_send_stalled(superadmin_client, outbox):
    with flask_app.app_context():
        nl = Newsletter(subject="Busy", body=BODY, status="sending", created_by=SUPER_EMAIL)
        db.session.add(nl)
        db.session.commit()
        nl_id = nl.id
    resp = superadmin_client.post(
        f"/api/admin/newsletter/campaigns/{nl_id}/resume", headers=superadmin_client.csrf_headers
    )
    assert resp.status_code == 409
    assert superadmin_client.delete(
        f"/api/admin/newsletter/campaigns/{nl_id}", headers=superadmin_client.csrf_headers
    ).status_code == 409


def test_campaign_list_reports_confirmed_count_and_limits(superadmin_client):
    add_sub("a@example.com")
    add_sub("p@example.com", confirmed=False)
    body = superadmin_client.get("/api/admin/newsletter/campaigns").get_json()
    assert body["confirmed"] == 1 and body["recipient_limit"] == appmod.NEWSLETTER_MAX_RECIPIENTS
    assert body["email_configured"] is True


# ── unsubscribing ───────────────────────────────────────────────────────────

def test_one_click_unsubscribe_post_removes_the_subscriber_but_get_does_not(client):
    add_sub("leaving@example.com")
    token = f"u-leaving@example.com-{'y' * 30}"
    assert client.get(f"/newsletter/unsubscribe/{token}").status_code == 200
    with flask_app.app_context():
        assert Subscriber.query.filter_by(email="leaving@example.com").count() == 1
    assert client.post(f"/newsletter/unsubscribe/{token}").status_code == 200
    with flask_app.app_context():
        assert Subscriber.query.filter_by(email="leaving@example.com").count() == 0
    assert client.post(f"/newsletter/unsubscribe/{token}").status_code == 200  # unknown token: no error, no leak


def test_newsletter_message_carries_list_unsubscribe_headers(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        mailers, "_deliver",
        lambda subject, sender, recipient, plain, html=None, sync=False, headers=None: captured.update(
            subject=subject, recipient=recipient, sync=sync, headers=headers
        ),
    )
    mailers.send_newsletter_message("x@example.com", "S", "plain", "<p>html</p>", "from@example.com", "https://u.example/unsub/t")
    assert captured["sync"] is True
    assert captured["headers"] == {
        "List-Unsubscribe": "<https://u.example/unsub/t>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


# ── permissions ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/newsletter/subscribers"),
    ("get", "/api/admin/newsletter/campaigns"),
    ("post", "/api/admin/newsletter/subscribers"),
    ("post", "/api/admin/newsletter/campaigns"),
    ("post", "/api/admin/newsletter/campaigns/preview"),
    ("post", "/api/admin/newsletter/campaigns/1/send"),
    ("post", "/api/admin/newsletter/campaigns/1/test"),
    ("delete", "/api/admin/newsletter/subscribers/1"),
])
def test_everything_is_superadmin_only(admin_client, method, path):
    resp = getattr(admin_client, method)(path, json={"confirm": True}, headers=admin_client.csrf_headers)
    assert resp.status_code == 403


def test_anonymous_writes_are_rejected(client):
    assert client.post("/api/admin/newsletter/campaigns/1/send", json={"confirm": True}).status_code == 403


def test_list_unsubscribe_header_is_plain_text_not_encoded():
    """Mail apps cannot read an RFC-2047-encoded List-Unsubscribe, so the real
    (long) unsubscribe URL must survive as-is."""
    from backend.email_tasks import build_message

    url = "https://unitaryx.org/newsletter/unsubscribe/" + "a" * 43
    msg = build_message(
        "Subject", "from@example.com", "to@example.com", "plain " * 300, "<p>" + "word " * 300 + "</p>",
        headers={"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
    )
    raw = msg.as_bytes().decode()
    assert f"List-Unsubscribe: <{url}>" in raw
    headers_block = raw.replace("\r\n", "\n").split("\n\n", 1)[0]
    assert "=?utf-8?" not in headers_block.lower()
    assert max(len(line) for line in raw.splitlines()) <= 998


def test_messages_without_extra_headers_are_built_as_before():
    from backend.email_tasks import build_message

    msg = build_message("Hi", "a@example.com", "b@example.com", "plain body")
    assert msg["Subject"] == "Hi" and msg["List-Unsubscribe"] is None
