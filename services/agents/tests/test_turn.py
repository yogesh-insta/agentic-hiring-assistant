from services.agents.turn import chunk_text, coordinator_events, events_for_reply


def test_done_event_is_scanned_and_tokens_are_only_a_preview():
    raw = "Email avery@example.com to confirm."
    events = events_for_reply("m1", raw)
    token_text = "".join(data["text"] for name, data in events if name == "token")
    done = [data for name, data in events if name == "done"]
    assert token_text == raw
    assert done == [{"messageId": "m1", "text": "Email [redacted-email] to confirm."}]
    assert "".join(chunk_text(raw)) == raw


def test_empty_message_is_schema_invalid():
    assert coordinator_events("m1", "  ") == [("error", {"failureClass": "schema_invalid"})]


def test_turn_trace_omits_reply_text(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    coordinator_events("m9", "hello")
    text = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert "m9" in text
    assert "does not start a hire" not in text


def test_a_question_does_not_carry_a_brief():
    events = coordinator_events("m3", "what award applies to a barista in Fitzroy?")
    done = events[-1][1]
    assert "brief" not in done
    assert "does not start a hire" in done["text"]


def test_a_statement_can_offer_a_brief_without_starting():
    events = coordinator_events("m4", "I need a part-time barista in Fitzroy, weekends, about $32 an hour.")
    done = events[-1][1]
    assert done["brief"]["role"] == "barista"
    assert done["brief"]["location"] == "Fitzroy"
    assert "workflow" not in done


def test_coordinator_cassette_streams_then_finishes():
    events = coordinator_events("m2", "I need a barista")
    names = [name for name, _ in events]
    assert names[0] == "token"
    assert names[-1] == "done"
    done = events[-1][1]["text"]
    assert "".join(data["text"] for name, data in events if name == "token") == done
    assert "does not start a hire" in done
