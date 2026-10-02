"""Parse and redact a CV. No score, no rank, no workflow callback."""

import hashlib

from guardrails.injection import strip_instructions
from guardrails.output_scan import scan_output

RANKS_CANDIDATES = False
DEAD_LETTER_AFTER = 5


def parse_cv(raw: str, email: str, generation: str) -> dict:
    if RANKS_CANDIDATES:
        raise RuntimeError("ingest must not rank candidates")
    if not raw.strip() or not email.strip() or not generation.strip():
        raise ValueError("schema_invalid")
    redacted = scan_output(strip_instructions(raw))
    return {
        "generation": generation,
        "email": email,
        "redacted": redacted,
        "withheld": {"email": email},
    }


def generation_for(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class Inbox:
    """At-least-once delivery. The fifth failure is the dead letter."""

    def __init__(self):
        self.dead = []
        self.done = set()

    def deliver(self, message: dict) -> str:
        generation = message["generation"]
        if generation in self.done:
            return "duplicate"
        if message.get("poison"):
            message["attempts"] = int(message.get("attempts") or 0) + 1
            if message["attempts"] >= DEAD_LETTER_AFTER:
                self.dead.append(generation)
                return "dead"
            return "retry"
        if "score" in message or "rank" in message:
            raise RuntimeError("ingest must not rank candidates")
        self.done.add(generation)
        return "ok"
