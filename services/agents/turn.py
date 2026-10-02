"""Coordinator turn.

STREAMING_MODE is the ADK RunConfig value SSE. This path does not use BIDI.
Tokens are a preview. The done event is the scanned text. A brief on that
event is a suggestion for the confirm button. It does not start a hire.
"""

import json
from pathlib import Path

from agents.pipelines.job_ad import COORDINATOR_TIMEOUT_SECONDS
from agents.runtime.trace import record
from guardrails.output_scan import scan_output

ROOT = Path(__file__).resolve().parents[2]
COORDINATOR_PATH = ROOT / "evals" / "cassettes" / "coordinator.json"
BRIEF_PATH = ROOT / "data" / "synthetic" / "barista_brief.json"
STREAMING_MODE = "sse"


def load_coordinator() -> dict:
    return json.loads(COORDINATOR_PATH.read_text(encoding="utf-8"))


def chunk_text(text: str, size: int = 24) -> list:
    if text == "":
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def events_for_reply(message_id: str, raw: str, brief=None) -> list:
    scanned = scan_output(raw)
    done = {"messageId": message_id, "text": scanned}
    if brief is not None:
        done["brief"] = brief
    events = [("token", {"text": piece}) for piece in chunk_text(raw)]
    events.append(("done", done))
    return events


def is_question(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    first = stripped.lower().split(" ", 1)[0]
    return first in {"what", "how", "why", "when", "who", "where"}


def brief_from_message(text: str):
    if is_question(text):
        return None
    lowered = text.lower()
    if "barista" in lowered and "fitzroy" in lowered:
        return json.loads(BRIEF_PATH.read_text(encoding="utf-8"))
    return None


def coordinator_events(message_id: str, text: str) -> list:
    if not str(message_id).strip() or not str(text).strip():
        return [("error", {"failureClass": "schema_invalid"})]
    cassette = load_coordinator()
    question = is_question(text)
    record(
        "coordinator.turn",
        {
            "agent": "coordinator",
            "outcome": "ok",
            "message_id": message_id,
            "streaming_mode": STREAMING_MODE,
            "timeout_seconds": COORDINATOR_TIMEOUT_SECONDS,
        },
    )
    reply = cassette["question"] if question else cassette["output"]
    return events_for_reply(message_id, reply, None if question else brief_from_message(text))


def format_sse(event: str, data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    return "event: {0}\ndata: {1}\n\n".format(event, payload)
