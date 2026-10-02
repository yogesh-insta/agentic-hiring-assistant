from guardrails.injection import strip_instructions
from guardrails.output_scan import scan_output


def read_redacted(raw: str) -> dict:
    """Names and contact details do not leave this function."""
    return {
        "source": "cv_store",
        "version": "ingest-v1",
        "summary": scan_output(strip_instructions(raw)),
    }
