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
