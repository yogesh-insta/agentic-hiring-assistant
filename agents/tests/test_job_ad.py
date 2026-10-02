import ast
import asyncio
import json
from pathlib import Path

import pytest

from agents.plain_call import CassetteMiss, fill_job_ad, load_job_ad_cassette
from agents.runtime.adk import AdkRuntime
from agents.runtime.fake import FakeRuntime
from agents.runtime.trace import memory_exporter, setup_tracing
from agents.schema import JOB_AD_SPEC, AgentInput, JobAd, RunContext

ROOT = Path(__file__).resolve().parents[2]


def test_plain_call_does_not_import_adk():
    source = (ROOT / "agents" / "plain_call.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name.startswith("google.adk") or name == "google.adk" for name in imported)
    assert "google.adk" not in source


def test_cassette_matches_the_synthetic_brief():
    brief = json.loads((ROOT / "data" / "synthetic" / "barista_brief.json").read_text(encoding="utf-8"))
    assert load_job_ad_cassette()["brief"] == brief


def test_schema_filled_with_and_without_the_runtime():
    setup_tracing()
    memory_exporter.clear()
    brief = load_job_ad_cassette()["brief"]
    plain = fill_job_ad(brief)
    data = AgentInput(brief=brief)
    ctx = RunContext()
    fake = asyncio.run(FakeRuntime().run(JOB_AD_SPEC, data, ctx))
    adk = asyncio.run(AdkRuntime().run(JOB_AD_SPEC, data, ctx))

    assert isinstance(plain, JobAd)
    assert JobAd.model_validate(fake.output) == plain
    assert JobAd.model_validate(adk.output) == plain
    assert fake.framework == "fake"
    assert adk.framework == "adk"
    names = [span.name for span in memory_exporter.get_finished_spans()]
    assert names.count("plain.job_ad") == 3
    for span in memory_exporter.get_finished_spans():
        assert "body" not in span.attributes
        assert span.attributes["schema"] == "JobAd"


def test_unknown_brief_misses_the_cassette():
    with pytest.raises(CassetteMiss):
        fill_job_ad({"role": "baker", "location": "Fitzroy", "hours": "days", "pay": "$30"})


def test_local_trace_file_omits_the_ad_body(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    fill_job_ad(load_job_ad_cassette()["brief"])
    text = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert "plain.job_ad" in text
    assert "coffee service" not in text
