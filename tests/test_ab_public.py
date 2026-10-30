"""Public A/B testing: exposure and conversion tracking, and the admin results."""
import pytest

KEY = "hero_primary_cta"
VISITOR = "visitor-abcdef12"


@pytest.fixture
def visitor(client):
    client.set_cookie("ux_vid", VISITOR)
    return client


def _event(client, event, key=KEY, **extra):
    return client.post("/api/ab-tests/event", json={"test_key": key, "event": event, **extra})


def _set_allocation(superadmin_client, allocation):
    tests = superadmin_client.get("/api/admin/ab-tests").get_json()["tests"]
    test = next(t for t in tests if t["test_key"] == KEY)
    resp = superadmin_client.put(
        f"/api/admin/ab-tests/{test['id']}",
        json={"allocation_b": allocation, "enabled": True},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 200
    return test["id"]


def test_event_requires_visitor_cookie_and_known_event(client):
    resp = client.post("/api/ab-tests/event", json={"test_key": KEY, "event": "exposure"})
    assert resp.status_code == 400  # no ux_vid cookie yet

    client.set_cookie("ux_vid", VISITOR)
    resp = client.post("/api/ab-tests/event", json={"test_key": KEY, "event": "hover"})
    assert resp.status_code == 400


def test_exposure_is_recorded_once_per_visitor(visitor):
    assert _event(visitor, "exposure").get_json()["recorded"] is True
    assert _event(visitor, "exposure").get_json()["recorded"] is False


def test_unknown_test_is_ignored(visitor):
    assert _event(visitor, "exposure", key="no_such_test").get_json()["recorded"] is False


def test_conversion_needs_a_prior_exposure(visitor):
    assert _event(visitor, "conversion").get_json()["recorded"] is False
    assert _event(visitor, "exposure").get_json()["recorded"] is True
    assert _event(visitor, "conversion").get_json()["recorded"] is True
    assert _event(visitor, "conversion").get_json()["recorded"] is False


def test_client_cannot_choose_its_variant(superadmin_client):
    _set_allocation(superadmin_client, 0)  # everyone is A
    superadmin_client.set_cookie("ux_vid", VISITOR)
    _event(superadmin_client, "exposure", variant="B")
    stats = superadmin_client.get("/api/admin/ab-tests").get_json()["stats"][KEY]
    assert stats["A"]["exposures"] == 1 and stats["B"]["exposures"] == 0


def test_stats_follow_the_variant_seen_at_exposure(superadmin_client):
    test_id = _set_allocation(superadmin_client, 100)  # everyone is B
    superadmin_client.set_cookie("ux_vid", VISITOR)
    _event(superadmin_client, "exposure")
    _set_allocation(superadmin_client, 0)  # allocation changes before they convert
    _event(superadmin_client, "conversion")

    stats = superadmin_client.get("/api/admin/ab-tests").get_json()["stats"][KEY]
    assert stats["B"] == {"exposures": 1, "conversions": 1}
    assert stats["A"] == {"exposures": 0, "conversions": 0}

    resp = superadmin_client.delete(f"/api/admin/ab-tests/{test_id}/results", headers=superadmin_client.csrf_headers)
    assert resp.get_json()["removed"] == 2
    assert KEY not in superadmin_client.get("/api/admin/ab-tests").get_json()["stats"]


def test_reset_is_superadmin_only(admin_client):
    tests = admin_client.get("/api/admin/ab-tests").get_json()["tests"]
    resp = admin_client.delete(f"/api/admin/ab-tests/{tests[0]['id']}/results", headers=admin_client.csrf_headers)
    assert resp.status_code == 403
