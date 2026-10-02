import pytest

from worker.main import RANKS_CANDIDATES, handle_message


def test_ingest_does_not_rank():
    assert RANKS_CANDIDATES is False


def test_incomplete_or_poison_messages_are_not_acked():
    payload = {
        "workflowId": "hire-1",
        "raw": "Avery, three years, weekends",
        "email": "avery@example.com",
        "candidateId": "avery",
    }
    assert handle_message(payload) == "ack"
    assert handle_message({"poison": True}) == "retry"
    assert handle_message({"workflowId": "hire-1"}) == "retry"
    with pytest.raises(RuntimeError):
        handle_message(dict(payload, score=1))
