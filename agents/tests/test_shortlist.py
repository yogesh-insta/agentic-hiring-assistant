import copy

import pytest

from agents.plain_call import CassetteMiss
from agents.shortlist import band, check_golden_cases, load_shortlist_cassette, validate_shortlist
from guardrails.rubric import PolicyDenied, lint


def test_ten_cases_match_the_band():
    scored = check_golden_cases()
    assert len(scored) == 10
    assert [item["band"] for item in scored] == [case["band"] for case in load_shortlist_cassette()["cases"]]


def test_prompt_change_misses_the_cassette():
    changed = copy.deepcopy(load_shortlist_cassette())
    changed["prompt"] = changed["prompt"] + " extra"
    with pytest.raises(CassetteMiss):
        validate_shortlist(changed)


def test_counterfactual_name_does_not_move_the_band():
    left = {"id": "avery", "name": "Avery", "pronoun": "she", "years": 3, "weekends": True}
    right = {"id": "jordan", "name": "Jordan", "pronoun": "they", "years": 3, "weekends": True}
    left_band = band(left["years"], left["weekends"])
    right_band = band(right["years"], right["weekends"])
    assert abs(left_band - right_band) <= 1
    recommended = {person["id"] for person in (left, right) if band(person["years"], person["weekends"]) >= 3}
    assert recommended == {"avery", "jordan"}


def test_biased_rubric_is_refused():
    with pytest.raises(PolicyDenied):
        lint(["prefer women"])
