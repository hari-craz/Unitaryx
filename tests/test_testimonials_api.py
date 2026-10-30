REVIEW = "Delivered the project on time and explained every part of the code."


def _create(client, **overrides):
    payload = {"name": "Asha", "role": "Client", "review": REVIEW, "rating": 5}
    payload.update(overrides)
    return client.post("/api/admin/testimonials", json=payload, headers=client.csrf_headers)


def test_public_list_returns_only_active(superadmin_client):
    _create(superadmin_client, name="Visible")
    _create(superadmin_client, name="Hidden", active=False)

    resp = superadmin_client.get("/api/testimonials")
    assert resp.status_code == 200
    assert [t["name"] for t in resp.get_json()] == ["Visible"]


def test_create_update_delete_roundtrip(superadmin_client):
    headers = superadmin_client.csrf_headers
    created = _create(superadmin_client)
    assert created.status_code == 201
    item_id = created.get_json()["testimonial"]["id"]

    resp = superadmin_client.put(
        f"/api/admin/testimonials/{item_id}", json={"rating": 4, "active": False}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.get_json()["testimonial"]
    assert body["rating"] == 4 and body["active"] is False
    assert body["name"] == "Asha"  # partial update leaves other fields alone

    assert superadmin_client.delete(f"/api/admin/testimonials/{item_id}", headers=headers).status_code == 200
    assert superadmin_client.delete(f"/api/admin/testimonials/{item_id}", headers=headers).status_code == 404
    assert superadmin_client.put(
        f"/api/admin/testimonials/{item_id}", json={"rating": 3}, headers=headers
    ).status_code == 404


def test_validation_rejects_bad_input(superadmin_client):
    assert _create(superadmin_client, name="").status_code == 400
    assert _create(superadmin_client, review="too short").status_code == 400
    assert _create(superadmin_client, review="x" * 801).status_code == 400
    assert _create(superadmin_client, rating=0).status_code == 400
    assert _create(superadmin_client, rating=6).status_code == 400
    assert _create(superadmin_client, rating="five").status_code == 400
    assert superadmin_client.get("/api/testimonials").get_json() == []


def test_admin_routes_are_superadmin_only(admin_client, client):
    assert admin_client.get("/api/admin/testimonials").status_code == 403
    resp = admin_client.post(
        "/api/admin/testimonials",
        json={"name": "X", "review": REVIEW},
        headers=admin_client.csrf_headers,
    )
    assert resp.status_code == 403
    # Anonymous writes are stopped by CSRF before they reach the view.
    assert client.post("/api/admin/testimonials", json={"name": "X", "review": REVIEW}).status_code == 403


def test_startup_does_not_reseed_deleted_testimonials(superadmin_client):
    assert superadmin_client.get("/api/testimonials").get_json() == []


def test_active_flag_is_parsed_not_truthy(superadmin_client):
    """bool("false") is True in Python; a string "false" must still hide the entry."""
    created = _create(superadmin_client, active="false")
    assert created.status_code == 201
    assert created.get_json()["testimonial"]["active"] is False
    assert superadmin_client.get("/api/testimonials").get_json() == []

    item_id = created.get_json()["testimonial"]["id"]
    headers = superadmin_client.csrf_headers
    resp = superadmin_client.put(f"/api/admin/testimonials/{item_id}", json={"active": "true"}, headers=headers)
    assert resp.get_json()["testimonial"]["active"] is True
    resp = superadmin_client.put(f"/api/admin/testimonials/{item_id}", json={"active": "off"}, headers=headers)
    assert resp.get_json()["testimonial"]["active"] is False
    assert superadmin_client.put(
        f"/api/admin/testimonials/{item_id}", json={"active": "maybe"}, headers=headers
    ).status_code == 400
