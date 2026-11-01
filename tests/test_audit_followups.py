"""Regression tests for the remaining items from the original bug audit."""
import re
from datetime import datetime, timedelta

import backend.app as appmod
from backend.app import ProjectRequest, SiteTrafficEvent, db, app as flask_app

parse = appmod._parse_deadline_days


# ── 27: deadlines such as "6 weeks" are understood ───────────────────────────

def test_relative_deadlines_are_parsed():
    assert parse("6 weeks") == 42
    assert parse("6 Weeks") == 42
    assert parse("2 months") == 60
    assert parse("10 days") == 10
    assert parse("3 wk") == 21
    assert parse("in 2 weeks") == 14
    assert parse("1.5 months") == 45


def test_urgent_words_count_as_very_soon():
    for text in ("ASAP", "urgent", "need it immediately", "tomorrow"):
        assert parse(text) == 1


def test_a_relative_deadline_shrinks_as_time_passes():
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    assert parse("6 weeks", two_weeks_ago) == 28
    assert parse("1 week", two_weeks_ago) == -7  # already overdue


def test_dates_and_unreadable_values_still_behave():
    in_ten_days = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
    assert parse(in_ten_days) in (9, 10)
    assert parse("") is None and parse(None) is None
    assert parse("whenever") is None
    assert parse("weeks") is None


def test_a_nearer_deadline_raises_the_urgency_score():
    def urgency(deadline):
        req = ProjectRequest(
            name="A", email="a@example.com", service="web", message="x" * 80, priority="Medium",
            value=1000, deadline=deadline, created_at=datetime.utcnow(),
        )
        appmod._score_project_request(req)
        return req.lead_score_urgency

    assert urgency("1 week") > urgency("6 weeks")
    assert urgency("6 weeks") == urgency("")


# ── 29: visitor address and cookie ───────────────────────────────────────────

def _page_view(client, headers=None, **kwargs):
    resp = client.post(
        "/api/traffic/page-view", json={"page_path": "/", "visitor_id": "visitor-abcdef12"}, headers=headers or {}, **kwargs
    )
    assert resp.status_code == 200
    return resp


def test_the_client_address_ignores_what_the_visitor_claims(client):
    with flask_app.app_context():
        SiteTrafficEvent.query.delete()
        db.session.commit()
    _page_view(client, headers={"X-Forwarded-For": "6.6.6.6, 7.7.7.7", "X-Real-IP": "8.8.8.8"})
    with flask_app.app_context():
        event = SiteTrafficEvent.query.order_by(SiteTrafficEvent.id.desc()).first()
        # Only the entry added by our own proxy counts; the leftmost value and
        # X-Real-IP were supplied by the visitor.
        assert event.ip_address == "7.7.7.7"


def test_visitor_cookie_is_secure_only_over_https(client):
    secure = _page_view(client, base_url="https://localhost").headers.get_all("Set-Cookie")
    plain = _page_view(client, base_url="http://localhost").headers.get_all("Set-Cookie")
    assert any("ux_vid" in c and "Secure" in c for c in secure)
    assert any("ux_vid" in c and "Secure" not in c for c in plain)


def test_ab_resolve_cookie_follows_the_same_rule(client):
    cookies = client.get("/api/ab-tests/resolve", base_url="https://localhost").headers.get_all("Set-Cookie")
    assert any("ux_vid" in c and "Secure" in c for c in cookies)


# ── 32: images ───────────────────────────────────────────────────────────────

def test_csp_no_longer_allows_images_from_anywhere(client):
    policy = client.get("/").headers.get("Content-Security-Policy", "")
    sources = re.search(r"img-src ([^;]+)", policy).group(1).split()
    assert "*" not in sources and "http:" not in sources
    assert "'self'" in sources and "https:" in sources and "data:" in sources


# ── team / project flags ─────────────────────────────────────────────────────

def test_string_false_hides_a_team_member(superadmin_client):
    headers = superadmin_client.csrf_headers
    created = superadmin_client.post(
        "/api/admin/founders", json={"name": "Hidden", "role": "Dev", "active": "false"}, headers=headers
    )
    assert created.status_code == 201 and created.get_json()["founder"]["active"] is False
    assert superadmin_client.get("/api/founders").get_json() == []

    founder_id = created.get_json()["founder"]["id"]
    resp = superadmin_client.put(f"/api/admin/founders/{founder_id}", json={"active": "true"}, headers=headers)
    assert resp.get_json()["founder"]["active"] is True
    resp = superadmin_client.put(f"/api/admin/founders/{founder_id}", json={"active": "maybe"}, headers=headers)
    assert resp.status_code == 400


def test_string_false_does_not_feature_a_project(superadmin_client):
    headers = superadmin_client.csrf_headers
    created = superadmin_client.post(
        "/api/admin/projects",
        json={"title": "Plain", "description": "d", "category": "web", "featured": "false"},
        headers=headers,
    )
    assert created.status_code == 201
    project = created.get_json()["project"]
    assert project["featured"] is False
    resp = superadmin_client.put(f"/api/admin/projects/{project['id']}", json={"featured": "true"}, headers=headers)
    assert resp.get_json()["project"]["featured"] is True
    resp = superadmin_client.put(f"/api/admin/projects/{project['id']}", json={"featured": "false"}, headers=headers)
    assert resp.get_json()["project"]["featured"] is False
