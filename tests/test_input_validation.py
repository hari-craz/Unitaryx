"""Admin input validation for founders/projects and backup-restore safety."""
import pytest

from backend.app import _restore_backup_payload, AdminAuditLog, app as flask_app, db


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "A", "role": "Dev", "display_order": "abc"},
        {"name": "A", "role": "Dev", "photo_url": "javascript:alert(1)"},
        {"name": "A", "role": "Dev", "socials": {"x": "javascript:alert(1)"}},
    ],
)
def test_founder_rejects_bad_input(superadmin_client, payload):
    resp = superadmin_client.post("/api/admin/founders", json=payload, headers=superadmin_client.csrf_headers)
    assert resp.status_code == 400


def test_founder_accepts_upload_path_and_https_social(superadmin_client):
    resp = superadmin_client.post(
        "/api/admin/founders",
        json={"name": "A", "role": "Dev", "photo_url": "/static/uploads/founders/x.jpg",
              "socials": {"github": "https://github.com/x"}},
        headers=superadmin_client.csrf_headers,
    )
    assert resp.status_code == 201


def test_project_rating_is_clamped_and_bad_values_rejected(superadmin_client):
    base = {"title": "T", "description": "D", "category": "web"}
    ok = superadmin_client.post("/api/admin/projects", json={**base, "rating": 99}, headers=superadmin_client.csrf_headers)
    assert ok.status_code == 201 and ok.get_json()["project"]["rating"] == 5.0
    bad = superadmin_client.post("/api/admin/projects", json={**base, "rating": "nan"}, headers=superadmin_client.csrf_headers)
    assert bad.status_code == 400


def test_restore_rejects_payload_without_known_tables():
    with flask_app.app_context():
        with pytest.raises(ValueError):
            _restore_backup_payload({"tables": {}})


def test_restore_never_replaces_audit_log():
    with flask_app.app_context():
        db.session.add(AdminAuditLog(actor_email="a@b.c", action="X"))
        db.session.commit()
        before = AdminAuditLog.query.count()
        _restore_backup_payload({"tables": {"admin_audit_logs": [], "testimonials": []}})
        db.session.commit()
        assert AdminAuditLog.query.count() == before
