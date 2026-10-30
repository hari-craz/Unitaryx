def _create(client, **overrides):
    payload = {
        "name": "Acme Labs",
        "kind": "startup",
        "founder_name": "Asha Rao",
        "goals": "Ship a payments tool for small shops.",
        "website_url": "https://acme.example.com",
    }
    payload.update(overrides)
    return client.post("/api/admin/collaborators", json=payload, headers=client.csrf_headers)


def test_public_list_only_returns_active_in_display_order(superadmin_client):
    _create(superadmin_client, name="Second", display_order=2)
    _create(superadmin_client, name="First", display_order=1)
    _create(superadmin_client, name="Hidden", active=False, display_order=0)

    resp = superadmin_client.get("/api/collaborators")
    assert resp.status_code == 200
    assert [c["name"] for c in resp.get_json()] == ["First", "Second"]


def test_new_collaborators_go_to_the_end_by_default(superadmin_client):
    _create(superadmin_client, name="One")
    _create(superadmin_client, name="Two")
    assert [c["name"] for c in superadmin_client.get("/api/collaborators").get_json()] == ["One", "Two"]


def test_create_update_delete_roundtrip(superadmin_client):
    headers = superadmin_client.csrf_headers
    created = _create(superadmin_client)
    assert created.status_code == 201
    body = created.get_json()["collaborator"]
    assert body["kind"] == "startup" and body["founder_name"] == "Asha Rao" and body["active"] is True

    resp = superadmin_client.put(
        f"/api/admin/collaborators/{body['id']}",
        json={"kind": "freelancer", "goals": "Open to design work."},
        headers=headers,
    )
    assert resp.status_code == 200
    updated = resp.get_json()["collaborator"]
    assert updated["kind"] == "freelancer" and updated["goals"] == "Open to design work."
    assert updated["name"] == "Acme Labs"  # partial update leaves other fields alone

    assert superadmin_client.delete(f"/api/admin/collaborators/{body['id']}", headers=headers).status_code == 200
    assert superadmin_client.delete(f"/api/admin/collaborators/{body['id']}", headers=headers).status_code == 404
    assert superadmin_client.put(f"/api/admin/collaborators/{body['id']}", json={}, headers=headers).status_code == 404


def test_validation_rejects_bad_input(superadmin_client):
    assert _create(superadmin_client, name="").status_code == 400
    assert _create(superadmin_client, name="x" * 121).status_code == 400
    assert _create(superadmin_client, kind="agency").status_code == 400
    assert _create(superadmin_client, goals="x" * 301).status_code == 400
    assert _create(superadmin_client, website_url="").status_code == 400
    assert _create(superadmin_client, logo_url="https://x.example/logo.png").status_code == 201  # allowed
    assert _create(superadmin_client, logo_url="javascript:alert(1)").status_code == 400
    assert _create(superadmin_client, active="maybe").status_code == 400


def test_website_link_must_be_http_or_https(superadmin_client):
    """The link becomes a clickable button, so script and data URLs must never get in."""
    for bad in ("javascript:alert(1)", "data:text/html,hi", "ftp://x.example", "//evil.example", "acme.example.com", "https://"):
        assert _create(superadmin_client, website_url=bad).status_code == 400, bad
    assert _create(superadmin_client, website_url="http://acme.example.com/path?x=1").status_code == 201


def test_active_flag_is_parsed_not_truthy(superadmin_client):
    created = _create(superadmin_client, active="false")
    assert created.get_json()["collaborator"]["active"] is False
    assert superadmin_client.get("/api/collaborators").get_json() == []


def test_reorder(superadmin_client):
    headers = superadmin_client.csrf_headers
    a = _create(superadmin_client, name="A").get_json()["collaborator"]["id"]
    b = _create(superadmin_client, name="B").get_json()["collaborator"]["id"]
    resp = superadmin_client.post("/api/admin/collaborators/reorder", json={"order": [b, a]}, headers=headers)
    assert resp.status_code == 200
    assert [c["name"] for c in superadmin_client.get("/api/collaborators").get_json()] == ["B", "A"]
    assert superadmin_client.post(
        "/api/admin/collaborators/reorder", json={"order": [b, 9999]}, headers=headers
    ).status_code == 400
    assert superadmin_client.post("/api/admin/collaborators/reorder", json={"order": []}, headers=headers).status_code == 400


def test_admin_routes_are_superadmin_only(admin_client, client):
    assert admin_client.get("/api/admin/collaborators").status_code == 403
    resp = admin_client.post(
        "/api/admin/collaborators",
        json={"name": "X", "kind": "startup", "website_url": "https://x.example.com"},
        headers=admin_client.csrf_headers,
    )
    assert resp.status_code == 403
    # Anonymous writes are stopped by CSRF before they reach the view.
    assert client.post("/api/admin/collaborators", json={"name": "X"}).status_code == 403


def test_logo_upload_kind_is_accepted(superadmin_client, tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image
    import backend.app as app_module

    monkeypatch.setattr(app_module, "PROJECT_ROOT", str(tmp_path))
    buf = BytesIO()
    Image.new("RGB", (40, 40), (10, 20, 30)).save(buf, format="PNG")
    buf.seek(0)
    resp = superadmin_client.post(
        "/api/admin/upload",
        data={"kind": "collaborators", "file": (buf, "logo.png")},
        headers=superadmin_client.csrf_headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    assert resp.get_json()["url"].startswith("/static/uploads/collaborators/")


def test_collaborators_page_is_served_with_its_own_meta_and_listed_in_sitemap(client):
    resp = client.get("/collaborators")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<title>Collaborators | Unitary X</title>" in html
    assert 'rel="canonical" href="https://unitaryx.org/collaborators"' in html

    assert "https://unitaryx.org/collaborators" in client.get("/sitemap.xml").get_data(as_text=True)
