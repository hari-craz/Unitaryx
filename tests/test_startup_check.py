import pytest
from sqlalchemy import create_engine

import backend.app as appmod


def test_no_tables_missing_after_normal_startup():
    with appmod.app.app_context():
        assert appmod._missing_tables(appmod.db.engine) == []


def test_missing_tables_detected_on_empty_database():
    empty = create_engine("sqlite://")
    with appmod.app.app_context():
        missing = appmod._missing_tables(empty)
    assert "users" in missing and "projects" in missing and "founders" in missing


def test_verify_schema_raises_when_tables_missing(monkeypatch):
    monkeypatch.setattr(appmod, "_missing_tables", lambda engine: ["users"])
    with appmod.app.app_context():
        with pytest.raises(RuntimeError, match="missing tables: users"):
            appmod._verify_schema(retries=1, delay=0)


def test_verify_schema_recovers_if_another_worker_finishes(monkeypatch):
    answers = iter([["users"], []])
    monkeypatch.setattr(appmod, "_missing_tables", lambda engine: next(answers))
    with appmod.app.app_context():
        appmod._verify_schema(retries=3, delay=0)
