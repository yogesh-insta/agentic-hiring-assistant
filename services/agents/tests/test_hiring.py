from agents.pipelines.graph import load_graph_cassette
from services.agents.hiring import Runner


def barista_brief():
    return next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "barista-fitzroy")


def test_confirm_stores_a_validated_ad_and_sends_nothing():
    view = Runner().confirm(barista_brief())
    assert view["step"] == "ad_reviewed"
    assert view["artifact"]["status"] == "proposed"
    assert view["artifact"]["draft"]["title"] == "Part-time barista"
    assert view["sent"] is False
    assert view["history"] == ["confirm_brief", "call_job_ad", "await_ad_approval"]


def test_approve_is_idempotent_and_does_not_send():
    runner = Runner()
    started = runner.confirm(barista_brief())
    first = runner.approve(started["approvalId"])
    second = runner.approve(started["approvalId"])
    assert first["artifact"]["status"] == "approved"
    assert second["artifact"]["status"] == "approved"
    assert second["history"].count("approve_ad") == 1
    assert runner.sent == []


def test_reject_leaves_the_proposal_open():
    runner = Runner()
    started = runner.confirm(barista_brief())
    rejected = runner.reject(started["approvalId"], "Say weekend shifts.")
    assert rejected["artifact"]["status"] == "proposed"
    assert rejected["hirerRevisions"] == 1
    assert rejected["sent"] is False
    assert "reject_ad" in rejected["history"]


def test_third_reject_stops_for_a_manual_edit():
    runner = Runner()
    started = runner.confirm(barista_brief())
    approval_id = started["approvalId"]
    runner.reject(approval_id, "once")
    runner.reject(approval_id, "twice")
    stopped = runner.reject(approval_id, "three")
    assert stopped["manualEdit"] is True
    assert stopped["hirerRevisions"] == 3
    assert stopped["artifact"]["status"] == "proposed"
