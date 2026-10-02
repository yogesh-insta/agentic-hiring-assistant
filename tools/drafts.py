"""Draft tools. They do not send mail or create calendar events."""


def email_draft(text: str) -> dict:
    return {"source": "email", "version": "draft-v1", "summary": text, "sent": False}


def calendar_propose(when: str) -> dict:
    return {"source": "calendar", "version": "draft-v1", "summary": when, "created": False}
