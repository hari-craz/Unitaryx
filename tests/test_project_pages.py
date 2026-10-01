import re

import pytest

from backend.app import Project, db, app as flask_app


@pytest.fixture
def project(client):
    with flask_app.app_context():
        p = Project(
            title="Smart Home Automation",
            description="Arduino & ESP8266 <controller> with mobile app.",
            category="hardware",
            tags="arduino,esp8266",
        )
        db.session.add(p)
        db.session.commit()
        return {"id": p.id, "slug": p.slug}


def test_project_page_has_own_server_rendered_meta(client, project):
    resp = client.get(f"/projects/{project['slug']}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.count('rel="canonical"') == 1
    assert f'href="https://unitaryx.org/projects/{project["slug"]}"' in html
    assert "<title>Smart Home Automation" in html
    assert html.count("<title>") == 1
    assert html.count('property="og:title"') == 1
    assert html.count('name="description"') == 1
    assert html.count("application/ld+json") == 1
    # homepage-only structured data must not leak onto the case-study page
    assert "FAQPage" not in html
    # description is HTML-escaped inside attributes
    assert "&lt;controller&gt;" in html
    assert "<controller>" not in html


def test_stale_slug_redirects_to_canonical(client, project):
    resp = client.get(f"/projects/old-name-{project['id']}")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith(f"/projects/{project['slug']}")


def test_unknown_project_is_a_real_404(client, project):
    assert client.get("/projects/nope-99999").status_code == 404
    assert client.get("/projects/no-digits-here").status_code == 404


def test_project_detail_api(client, project):
    ok = client.get(f"/api/projects/{project['id']}")
    assert ok.status_code == 200
    assert ok.get_json()["slug"] == project["slug"]
    assert client.get("/api/projects/99999").status_code == 404


def test_sitemap_lists_home_and_each_project(client, project):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/xml"
    locs = re.findall(r"<loc>(.*?)</loc>", resp.get_data(as_text=True))
    assert locs[0] == "https://unitaryx.org/"
    assert f"https://unitaryx.org/projects/{project['slug']}" in locs


def test_case_study_fields_round_trip_through_admin_api(superadmin_client):
    headers = superadmin_client.csrf_headers
    created = superadmin_client.post(
        "/api/admin/projects",
        json={
            "title": "Water Monitor",
            "description": "IoT leak detection.",
            "category": "hardware",
            "problem": "  Leaks went unnoticed for days.  ",
            "approach": "ESP32 sensors with a Flask backend.",
            "outcome": "Leaks flagged within minutes.",
            "stack": ["ESP32", "Flask", " PostgreSQL "],
        },
        headers=headers,
    )
    assert created.status_code == 201
    project = created.get_json()["project"]
    assert project["problem"] == "Leaks went unnoticed for days."
    assert project["stack"] == ["ESP32", "Flask", "PostgreSQL"]
    assert project["has_case_study"] is True

    updated = superadmin_client.put(
        f"/api/admin/projects/{project['id']}",
        json={"outcome": "", "stack": "Flask, React"},
        headers=headers,
    )
    body = updated.get_json()["project"]
    assert body["outcome"] is None
    assert body["stack"] == ["Flask", "React"]
    assert body["problem"] == "Leaks went unnoticed for days."


def test_long_case_text_is_capped(superadmin_client):
    resp = superadmin_client.post(
        "/api/admin/projects",
        json={"title": "T", "description": "d", "category": "web", "problem": "x" * 9000},
        headers=superadmin_client.csrf_headers,
    )
    assert len(resp.get_json()["project"]["problem"]) == 4000


def test_page_head_prefers_problem_and_lists_stack(client):
    with flask_app.app_context():
        p = Project(
            title="Robot",
            description="Generic description.",
            category="hardware",
            tags="arduino",
            problem="Warehouses needed line-following carts.",
            stack="Arduino,C++",
        )
        db.session.add(p)
        db.session.commit()
        slug = p.slug
    html = client.get(f"/projects/{slug}").get_data(as_text=True)
    assert 'content="Warehouses needed line-following carts."' in html
    assert "Arduino, C++, arduino" in html


def test_sitemap_deprioritises_projects_without_case_study(client):
    with flask_app.app_context():
        thin = Project(title="Thin", description="d", category="web")
        rich = Project(title="Rich", description="d", category="web", outcome="Shipped.")
        db.session.add_all([thin, rich])
        db.session.commit()
        thin_slug, rich_slug = thin.slug, rich.slug
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    assert re.search(rf"{thin_slug}</loc>\s*<changefreq>monthly</changefreq>\s*<priority>0.4", xml)
    assert re.search(rf"{rich_slug}</loc>\s*<changefreq>monthly</changefreq>\s*<priority>0.7", xml)


def test_privacy_page_has_its_own_canonical_and_is_in_the_sitemap(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.count('rel="canonical"') == 1
    assert 'href="https://unitaryx.org/privacy"' in html
    assert html.count("<title>") == 1 and "<title>Privacy notice" in html
    assert "FAQPage" not in html
    locs = re.findall(r"<loc>(.*?)</loc>", client.get("/sitemap.xml").get_data(as_text=True))
    assert "https://unitaryx.org/privacy" in locs


def test_terms_page_has_its_own_canonical_and_is_in_the_sitemap(client):
    resp = client.get("/terms")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.count('rel="canonical"') == 1
    assert 'href="https://unitaryx.org/terms"' in html
    assert html.count("<title>") == 1 and "<title>Terms" in html
    locs = re.findall(r"<loc>(.*?)</loc>", client.get("/sitemap.xml").get_data(as_text=True))
    assert "https://unitaryx.org/terms" in locs and "https://unitaryx.org/privacy" in locs
