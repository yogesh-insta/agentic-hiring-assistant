"""Walk the job-ad graph from a cassette.

The gate is code. It reads a ReviewReport. It does not read prose.
Live Vertex is not called. Week 4 can compile these same edges into an ADK
Workflow object.
"""

import json
from pathlib import Path

from pydantic import TypeAdapter

from agents.pipelines.job_ad import MAX_REVISE, REVIEWER_PROMPT, REVISER_PROMPT, WRITER_PROMPT
from agents.plain_call import CassetteMiss
from agents.runtime.trace import record
from agents.schema import JobAd, ReviewIssue, ReviewReport

ROOT = Path(__file__).resolve().parents[2]
CASSETTE_PATH = ROOT / "evals" / "cassettes" / "job_ad_graph.json"
YAML_PATH = ROOT / "workflow" / "hiring.yaml"

_issues = TypeAdapter(list[ReviewIssue])


def expected_prompts():
    return {
        "writer": WRITER_PROMPT,
        "reviewer": REVIEWER_PROMPT,
        "reviser": REVISER_PROMPT,
    }


def validate_cassette(data):
    if data.get("prompts") != expected_prompts():
        raise CassetteMiss("prompt")
    if len(data.get("cases") or []) != 10:
        raise CassetteMiss("golden-count")
    return data


def load_graph_cassette():
    return validate_cassette(json.loads(CASSETTE_PATH.read_text(encoding="utf-8")))


def yaml_step_ids(text):
    found = set()
    for line in text.splitlines():
        if not line.startswith("    - ") or not line.rstrip().endswith(":"):
            continue
        name = line.strip()[2:-1]
        if name.isidentifier():
            found.add(name)
    return found


def case_for_brief(brief):
    for case in load_graph_cassette()["cases"]:
        if case["brief"] == brief:
            return case
    raise CassetteMiss("brief")


def run_job_ad(brief):
    case = case_for_brief(brief)
    steps = case["iterations"]
    trajectory = []
    revise_count = 0
    node = "writer"
    draft = None
    review = None
    index = 0
    while True:
        if node in ("writer", "reviser"):
            if index >= len(steps):
                raise CassetteMiss(case["id"])
            draft = JobAd.model_validate(steps[index]["draft"])
            trajectory.append(node)
            index += 1
            node = "reviewer"
            continue
        if node == "reviewer":
            review = ReviewReport(
                issues=_issues.validate_python(steps[index - 1]["review"]["issues"]),
                suggested_edits=list(steps[index - 1]["review"].get("suggested_edits") or []),
            )
            trajectory.append("reviewer")
            node = "gate"
            continue
        blocked = review.blocking_issues()
        if not blocked or revise_count >= MAX_REVISE:
            trajectory.append("gate:done")
            break
        revise_count += 1
        trajectory.append("gate:revise")
        node = "reviser"
    record(
        "job_ad.graph",
        {
            "agent": "job_ad",
            "outcome": "ok",
            "route": "done",
            "nodes": ",".join(trajectory),
        },
    )
    return {
        "draft": draft.model_dump(),
        "review": review.model_dump(),
        "trajectory": trajectory,
    }
