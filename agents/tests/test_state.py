import pytest

from agents.identity import actor
from agents.state_store import AuditLog


def test_audit_log_is_create_only():
    log = AuditLog()
    event = {"id": "a1", "action": "email.send", "outcome": "ok"}
    log.append_all([event])
    log.append_all([dict(event)])
    with pytest.raises(RuntimeError):
        log.append_all([{"id": "a1", "action": "email.send", "outcome": "tool_error"}])
    with pytest.raises(RuntimeError):
        log.append_all([{"action": "email.send"}])


def test_cloud_rejects_the_demo_bearer(monkeypatch):
    monkeypatch.setenv("ENV", "cloud")
    monkeypatch.delenv("WORKFLOW_TOKEN", raising=False)
    assert actor("Bearer local-workflow", "workflow") == ""


def test_local_accepts_the_demo_bearer(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    monkeypatch.delenv("WORKFLOW_TOKEN", raising=False)
    assert actor("Bearer local-workflow", "workflow") == "workflow"
