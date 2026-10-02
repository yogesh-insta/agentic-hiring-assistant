from agents.records import COLLECTIONS, RULES_PATH, client_denied_collections


def test_seven_collections_are_named():
    assert COLLECTIONS == (
        "workflows",
        "artifacts",
        "applications",
        "interviews",
        "approvals",
        "audit",
        "callbacks",
    )


def test_client_rules_deny_callbacks_and_audit():
    denied = client_denied_collections(RULES_PATH.read_text(encoding="utf-8"))
    assert "callbacks" in denied
    assert "audit" in denied
    assert denied == set(COLLECTIONS)
