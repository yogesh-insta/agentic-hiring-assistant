"""Hire state for Cloud Run.

The process loads one snapshot at startup and writes it back after a change.
Audit events are create-only: a second write with a different body fails.
"""


def encode(value):
    if isinstance(value, set):
        return {"__set__": sorted(value)}
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encode(item) for item in value]
    return value


def decode(value):
    if isinstance(value, dict) and set(value) == {"__set__"}:
        return set(value["__set__"])
    if isinstance(value, dict):
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


class AuditLog:
    """In-memory create-only check used before a Firestore create."""

    def __init__(self):
        self.events = {}

    def append_all(self, events):
        for event in events:
            event_id = event.get("id")
            if not event_id:
                raise RuntimeError("audit event has no id")
            prior = self.events.get(event_id)
            current = dict(event)
            if prior is None:
                self.events[event_id] = current
            elif prior != current:
                raise RuntimeError("audit is create-only")


class FirestoreState:
    def __init__(self, project):
        from google.cloud import firestore

        self.client = firestore.Client(project=project)
        self.doc = self.client.collection("runtime").document("state")
        self.audit = self.client.collection("audit")
        self.log = AuditLog()
        self.persisted = set()

    def load_into(self, runner):
        snapshot = self.doc.get()
        if not snapshot.exists:
            return
        data = decode(snapshot.to_dict() or {})
        runner.workflows = data.get("workflows") or {}
        runner.artifacts = data.get("artifacts") or {}
        runner.approvals = data.get("approvals") or {}
        runner.applications = data.get("applications") or {}
        runner.interviews = data.get("interviews") or {}
        runner.audit = data.get("audit") or []
        runner.reminders = data.get("reminders") or {}
        runner.callbacks = data.get("callbacks") or {}
        runner.callback_targets = data.get("callback_targets") or {}
        runner.sent = data.get("sent") or []
        self.log.append_all(runner.audit)
        self.persisted.update(event["id"] for event in runner.audit)

    def save(self, runner):
        from google.api_core.exceptions import AlreadyExists

        self.log.append_all(runner.audit)
        for event in runner.audit:
            if event["id"] in self.persisted:
                continue
            try:
                self.audit.document(event["id"]).create(encode(event))
            except AlreadyExists:
                pass
            self.persisted.add(event["id"])
        self.doc.set(encode({
            "workflows": runner.workflows,
            "artifacts": runner.artifacts,
            "approvals": runner.approvals,
            "applications": runner.applications,
            "interviews": runner.interviews,
            "audit": runner.audit,
            "reminders": runner.reminders,
            "callbacks": runner.callbacks,
            "callback_targets": runner.callback_targets,
            "sent": runner.sent,
        }))
