import asyncio
import copy

import pytest
from pydantic import ValidationError

from agents.pipelines.graph import case_for_brief, load_graph_cassette, run_job_ad, validate_cassette, yaml_step_ids
from agents.pipelines.graph import YAML_PATH
from agents.pipelines.job_ad import (
    COORDINATOR_TIMEOUT_SECONDS,
    JOB_AD_TIMEOUT_SECONDS,
    WORKFLOW_HTTP_TIMEOUT_SECONDS,
)
from agents.plain_call import CassetteMiss
from agents.runtime.adk import AdkRuntime
from agents.runtime.fake import FakeRuntime
from agents.schema import ReviewReport
from services.agents.hiring import TRANSITIONS, transitions_match_yaml


def test_timeouts_leave_room_for_the_graph():
    assert JOB_AD_TIMEOUT_SECONDS == 180
    assert COORDINATOR_TIMEOUT_SECONDS == 60
    assert WORKFLOW_HTTP_TIMEOUT_SECONDS > JOB_AD_TIMEOUT_SECONDS


def test_runner_transitions_are_yaml_step_ids():
    assert transitions_match_yaml() == []
    assert set(TRANSITIONS) <= yaml_step_ids(YAML_PATH.read_text(encoding="utf-8"))


def test_prompt_change_misses_the_cassette():
    cassette = load_graph_cassette()
    changed = copy.deepcopy(cassette)
    changed["prompts"]["writer"] = cassette["prompts"]["writer"] + " extra"
    with pytest.raises(CassetteMiss):
        validate_cassette(changed)


def test_ten_golden_cases_run():
    cassette = load_graph_cassette()
    assert len(cassette["cases"]) == 10
    for case in cassette["cases"]:
        result = run_job_ad(case["brief"])
        assert result["trajectory"][0] == "writer"
        assert "reviewer" in result["trajectory"]
        assert result["trajectory"][-1] == "gate:done"
        assert "title" in result["draft"]


def test_barista_revises_once_and_stops_on_a_clean_review():
    brief = next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "barista-fitzroy")
    result = run_job_ad(brief)
    assert result["trajectory"] == [
        "writer",
        "reviewer",
        "gate:revise",
        "reviser",
        "reviewer",
        "gate:done",
    ]
    assert result["review"]["issues"] == []
    assert "young, energetic team" not in result["draft"]["body"]


def test_stubborn_case_stops_at_three_revises_with_open_issues():
    brief = next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "cook-carlton")
    result = run_job_ad(brief)
    assert result["trajectory"].count("gate:revise") == 3
    assert result["trajectory"][-1] == "gate:done"
    assert result["review"]["issues"][0]["blocking"] is True


def test_clean_case_does_not_revise():
    brief = next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "clerk-richmond")
    result = run_job_ad(brief)
    assert result["trajectory"] == ["writer", "reviewer", "gate:done"]


def test_gate_rejects_prose():
    with pytest.raises(ValidationError):
        ReviewReport.model_validate("no blocking issues")


def test_unknown_brief_misses_the_graph_cassette():
    with pytest.raises(CassetteMiss):
        case_for_brief({"role": "baker", "location": "Fitzroy", "hours": "days", "pay": "$30"})


def test_both_runtimes_record_the_same_trajectory():
    brief = next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "barista-fitzroy")
    fake = asyncio.run(FakeRuntime().run_graph(brief))
    adk = asyncio.run(AdkRuntime().run_graph(brief))
    assert fake["trajectory"] == adk["trajectory"]
    assert fake["framework"] == "fake"
    assert adk["framework"] == "adk"


def test_graph_trace_omits_the_ad_body(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    brief = next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "barista-fitzroy")
    run_job_ad(brief)
    text = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert "job_ad.graph" in text
    assert "young, energetic team" not in text
