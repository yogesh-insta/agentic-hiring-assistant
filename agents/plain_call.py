"""One structured model call with no agent framework.

Week 2 replaces the cassette body with the job-ad graph. This module must
not import Google ADK.
"""

import json
from pathlib import Path

from agents.runtime.trace import record
from agents.schema import JobAd

ROOT = Path(__file__).resolve().parents[1]
CASSETTE_PATH = ROOT / "evals" / "cassettes" / "job_ad.json"


class CassetteMiss(Exception):
    """The brief does not match the recorded cassette."""


def load_job_ad_cassette() -> dict:
    return json.loads(CASSETTE_PATH.read_text(encoding="utf-8"))


def fill_job_ad(brief: dict) -> JobAd:
    cassette = load_job_ad_cassette()
    if brief != cassette["brief"]:
        raise CassetteMiss(cassette["id"])
    ad = JobAd.model_validate(cassette["output"])
    record("plain.job_ad", {"agent": "plain", "outcome": "ok", "schema": "JobAd"})
    return ad
