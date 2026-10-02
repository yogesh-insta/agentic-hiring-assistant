from guardrails.output_scan import scan_output


def test_scan_redacts_email_and_phone():
    raw = "Write to avery@example.com or 0412345678 about the shift."
    cleaned = scan_output(raw)
    assert "avery@example.com" not in cleaned
    assert "0412345678" not in cleaned
    assert "[redacted-email]" in cleaned
    assert "[redacted-phone]" in cleaned
