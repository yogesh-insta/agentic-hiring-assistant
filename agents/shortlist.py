"""Score weekend availability and years. Names and hidden instructions are not inputs."""

import json
from pathlib import Path

from agents.plain_call import CassetteMiss

ROOT = Path(__file__).resolve().parents[1]
CASSETTE_PATH = ROOT / "evals" / "cassettes" / "shortlist.json"
CANDIDATES_PATH = ROOT / "data" / "synthetic" / "candidates.json"
PROMPT = "Score only weekend availability and years of coffee service. Cite a phrase from the redacted CV. Do not drop a candidate."
RECOMMEND_AT = 3


def band(years: int, weekends: bool) -> int:
    value = 1
    if weekends:
        value += 2
    if years >= 2:
        value += 2
    return min(5, value)


def validate_shortlist(data):
    if data.get("prompt") != PROMPT:
        raise CassetteMiss("prompt")
    if len(data.get("cases") or []) != 10:
        raise CassetteMiss("golden-count")
    return data


def load_shortlist_cassette():
    return validate_shortlist(json.loads(CASSETTE_PATH.read_text(encoding="utf-8")))


def load_candidates():
    return json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))


def score_case(case: dict) -> dict:
    value = band(case["years"], case["weekends"])
    evidence = case["evidence"]
    if evidence not in case["redacted"]:
        raise CassetteMiss("evidence")
    return {
        "id": case["id"],
        "band": value,
        "evidence": evidence,
        "recommended": value >= RECOMMEND_AT,
    }


def check_golden_cases():
    cassette = load_shortlist_cassette()
    scored = []
    for case in cassette["cases"]:
        result = score_case(case)
        if result["band"] != case["band"]:
            raise CassetteMiss(case["id"])
        scored.append(result)
    return scored
