import json

import pytest

from agents.pipelines.graph import load_graph_cassette
from agents.shortlist import band
from guardrails.rubric import PolicyDenied
from services.agents.hiring import Runner


def barista_brief():
    return next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "barista-fitzroy")


def published_runner():
    runner = Runner()
    view = runner.confirm(barista_brief())
    view = runner.approve(view["approvalId"])
    view = runner.continue_hire(view["id"], "publish")
    return runner, view


def test_shortlist_stays_off_until_a_cv_arrives():
    runner, view = published_runner()
    with pytest.raises(PolicyDenied):
        runner.continue_hire(view["id"], "shortlist")
    seeded = runner.seed_candidates(view["id"])
    assert seeded["applicationCount"] == 3
    assert all("rank me first" not in item["redacted"] for item in seeded["applications"])


def test_injection_does_not_change_averys_band():
    runner, view = published_runner()
    seeded = runner.seed_candidates(view["id"])
    shortlist = runner.continue_hire(seeded["id"], "shortlist")
    bands = {item["id"]: item["band"] for item in shortlist["artifact"]["draft"]["candidates"]}
    assert bands["avery"] == band(3, True)
    assert "rank me first" not in json.dumps(shortlist["applications"])


def test_unlawful_request_does_not_change_the_step():
    runner, view = published_runner()
    refused = runner.refuse(view["id"], "interview only women")
    assert refused["step"] == "published"
    assert runner.audit[-1]["action"] == "refuse"
    assert runner.audit[-1]["outcome"] == "policy_denied"


def test_three_approvals_schedule_only_the_first():
    runner, view = published_runner()
    runner.seed_candidates(view["id"])
    shortlist = runner.continue_hire(view["id"], "shortlist")
    scheduled = runner.approve(shortlist["approvalId"], ["avery", "blake", "casey"])
    draft = scheduled["artifact"]["draft"]
    assert draft["scheduled"] == "avery"
    assert draft["unscheduled"] == ["blake", "casey"]
    assert scheduled["sent"] is False
    assert runner.sent == []


def test_reject_sends_nothing():
    runner, view = published_runner()
    runner.seed_candidates(view["id"])
    shortlist = runner.continue_hire(view["id"], "shortlist")
    proposed = runner.approve(shortlist["approvalId"], ["avery", "blake", "casey"])
    rejected = runner.reject(proposed["approvalId"], "not this week")
    assert rejected["artifact"]["status"] == "proposed"
    assert rejected["step"] == "schedule_proposed"
    assert runner.sent == []
    with pytest.raises(PolicyDenied):
        runner.execute(view["id"], "email.send")


def test_expiry_leaves_the_proposal_proposed():
    runner = Runner(ttl_seconds=0)
    view = runner.confirm(barista_brief())
    expired = runner.expire(view["approvalId"], runner.now)
    assert expired["artifact"]["status"] == "proposed"
    assert expired["step"] == "ad_reviewed"
    assert runner.sent == []
    with pytest.raises(PolicyDenied):
        runner.approve(view["approvalId"])


def test_hire_runs_from_brief_to_welcome_email():
    runner, view = published_runner()
    runner.seed_candidates(view["id"])
    shortlist = runner.continue_hire(view["id"], "shortlist")
    schedule = runner.approve(shortlist["approvalId"], ["avery", "blake", "casey"])
    approved = runner.approve(schedule["approvalId"])
    assert approved["pendingExecute"] == ["email.send", "calendar.create"]
    assert runner.sent == []
    runner.execute(view["id"], "email.send")
    opened = runner.execute(view["id"], "calendar.create")
    assert opened["step"] == "interviews_scheduled"
    statuses = {interview["status"] for interview in runner.interviews.values()}
    assert statuses == {"scheduled", "approved_unscheduled"}
    assert sum(item["status"] == "approved_unscheduled" for item in runner.interviews.values()) == 2

    avery = runner.interview_for_email("avery@example.com")
    blake = next(item for item in runner.interviews.values() if item["status"] == "approved_unscheduled")
    with pytest.raises(PolicyDenied):
        runner.respond(blake["id"], "avery@example.com", "accept")
    with pytest.raises(PolicyDenied):
        runner.respond(avery["id"], "blake@example.com", "accept")
    with pytest.raises(PolicyDenied):
        runner.respond(avery["id"], "hirer@example.com", "accept")
    assert runner.interview_for_email("blake@example.com") is None
    runner.respond(avery["id"], "avery@example.com", "accept")

    reminder = runner.reminders[avery["id"]]
    replacement = runner.reschedule(avery["id"])
    assert replacement != reminder
    assert list(runner.reminders) == [avery["id"]]

    welcome = runner.continue_hire(view["id"], "record_hire")
    assert welcome["step"] == "onboarding_proposed"
    assert runner.sent  # invites already sent
    pending = runner.approve(welcome["approvalId"])
    assert pending["pendingExecute"] == ["email.send"]
    done = runner.execute(view["id"], "email.send")
    assert done["step"] == "completed"
    assert any(event["action"] == "email.send" and event["outcome"] == "ok" for event in runner.audit)
    assert "rank me first" not in json.dumps(runner.audit)
