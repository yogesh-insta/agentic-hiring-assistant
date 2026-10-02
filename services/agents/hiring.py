"""Local step runner.

Transitions are names, not a Workflows expression interpreter. A hirer
approval does not send mail. Execute does, and only after that approval.
Callback ids stay on the runner. The browser view never includes one.
"""

import json
import os
import secrets
import threading
import time

from agents.cost import LEDGER
from agents.pipelines.graph import YAML_PATH, run_job_ad, yaml_step_ids
from agents.plain_call import CassetteMiss
from agents.shortlist import band, load_candidates
from guardrails.rubric import PolicyDenied, lint, unlawful_screen
from worker.ingest import generation_for, parse_cv

TRANSITIONS = (
    "confirm_brief",
    "call_job_ad",
    "await_ad_approval",
    "approve_ad",
    "reject_ad",
    "publish",
    "call_shortlist",
    "await_shortlist_approval",
    "approve_shortlist",
    "reject_shortlist",
    "call_schedule",
    "await_schedule_approval",
    "approve_schedule",
    "reject_schedule",
    "execute_send",
    "record_hire",
    "call_onboard",
    "await_onboarding_approval",
    "approve_onboarding",
    "reject_onboarding",
    "execute_welcome",
)

DISCLAIMER = (
    "This is a recommendation. You make the hiring decision. "
    "This tool does not determine whether that decision is lawful. "
    "Synthetic pairs are not a legal finding."
)
WEEK_SECONDS = 7 * 24 * 3600
IDLE_SECONDS = 14 * 24 * 3600

MAX_HIRER_REVISIONS = 3


def transitions_match_yaml():
    missing = [name for name in TRANSITIONS if name not in yaml_step_ids(YAML_PATH.read_text(encoding="utf-8"))]
    return missing


class Runner:
    def __init__(self, now=None, ttl_seconds=WEEK_SECONDS):
        self._lock = threading.RLock()
        self._dirty = False
        self.store = None
        self.workflows = {}
        self.artifacts = {}
        self.approvals = {}
        self.applications = {}
        self.interviews = {}
        self.sent = []
        self.audit = []
        self.reminders = {}
        self.callbacks = {}
        self.callback_targets = {}
        self.now = now if now is not None else int(time.time())
        self.ttl_seconds = ttl_seconds
        project = os.environ.get("FIRESTORE_PROJECT", "")
        if project:
            from agents.state_store import FirestoreState

            self.store = FirestoreState(project)
            self.store.load_into(self)

    def confirm(self, brief, workflow_id=None):
        self._touch()
        if workflow_id and workflow_id in self.workflows:
            return self.view(workflow_id)
        try:
            result = run_job_ad(brief)
        except CassetteMiss:
            raise
        workflow_id = workflow_id or secrets.token_hex(8)
        artifact_id = secrets.token_hex(8)
        approval_id = secrets.token_hex(8)
        callback_id = secrets.token_hex(16)
        self.artifacts[artifact_id] = {
            "id": artifact_id,
            "kind": "job_ad",
            "status": "proposed",
            "draft": result["draft"],
            "review": result["review"],
            "trajectory": result["trajectory"],
        }
        self.approvals[approval_id] = self._approval(approval_id, workflow_id, artifact_id)
        self.workflows[workflow_id] = {
            "id": workflow_id,
            "step": "ad_reviewed",
            "brief": brief,
            "history": ["confirm_brief", "call_job_ad", "await_ad_approval"],
            "hirer_revisions": 0,
            "manual_edit": False,
            "artifact_id": artifact_id,
            "approval_id": approval_id,
            "application_count": 0,
            "pending_execute": [],
            "approved_ids": [],
            "last_activity": self.now,
        }
        self.callbacks[callback_id] = {
            "workflow_id": workflow_id,
            "approval_id": approval_id,
            "purpose": "ad_approval",
        }
        LEDGER.record(workflow_id, "job_ad", "cassette", 0, 0, 0)
        _log("hiring_step", workflowId=workflow_id, agent="job_ad", outcome="ok")
        return self.view(workflow_id)

    def approve(self, approval_id, candidate_ids=None):
        self._touch()
        workflow = self._workflow_for_approval(approval_id)
        self._require_open(approval_id)
        artifact = self.artifacts[self.approvals[approval_id]["artifact_id"]]
        if artifact["status"] == "approved":
            return self.view(workflow["id"])
        artifact["status"] = "approved"
        self.approvals[approval_id]["decision"] = "approve"
        kind = artifact["kind"]
        if kind == "job_ad":
            workflow["history"].append("approve_ad")
        elif kind == "shortlist":
            ids = list(candidate_ids or [])
            if len(ids) < 1:
                raise ValueError("schema_invalid")
            workflow["approved_ids"] = ids
            workflow["history"].append("approve_shortlist")
            self._propose_schedule(workflow, ids)
        elif kind == "schedule":
            workflow["history"].append("approve_schedule")
            workflow["pending_execute"] = ["email.send", "calendar.create"]
        elif kind == "onboarding":
            workflow["history"].append("approve_onboarding")
            workflow["pending_execute"] = ["email.send"]
        return self.view(workflow["id"])

    def reject(self, approval_id, note):
        self._touch()
        workflow = self._workflow_for_approval(approval_id)
        self._require_open(approval_id)
        artifact = self.artifacts[self.approvals[approval_id]["artifact_id"]]
        artifact["status"] = "proposed"
        self.approvals[approval_id]["decision"] = "reject"
        self.approvals[approval_id]["note"] = note
        workflow["pending_execute"] = []
        if artifact["kind"] != "job_ad":
            workflow["history"].append("reject_" + artifact["kind"])
            return self.view(workflow["id"])
        workflow["history"].append("reject_ad")
        workflow["hirer_revisions"] += 1
        if workflow["hirer_revisions"] >= MAX_HIRER_REVISIONS:
            workflow["manual_edit"] = True
            return self.view(workflow["id"])
        result = run_job_ad(workflow["brief"])
        artifact["draft"] = result["draft"]
        artifact["review"] = result["review"]
        artifact["trajectory"] = result["trajectory"]
        workflow["history"].extend(["call_job_ad", "await_ad_approval"])
        return self.view(workflow["id"])

    def expire(self, approval_id, now):
        self._touch()
        approval = self.approvals[approval_id]
        if now < approval["expires_at"]:
            return self.view(approval["workflow_id"])
        workflow = self.workflows[approval["workflow_id"]]
        artifact = self.artifacts[approval["artifact_id"]]
        artifact["status"] = "proposed"
        approval["decision"] = "expired"
        workflow["pending_execute"] = []
        if workflow["step"] not in ("completed", "abandoned"):
            workflow["step"] = workflow["step"]
        return self.view(workflow["id"])

    def continue_hire(self, workflow_id, action, now=None):
        self._touch()
        moment = self.now if now is None else now
        self.abandon_if_idle(workflow_id, moment)
        workflow = self.workflows[workflow_id]
        if workflow["step"] == "abandoned":
            raise PolicyDenied("abandoned")
        if action == "publish":
            self._require_kind(workflow, "job_ad", "approved")
            workflow["step"] = "published"
            workflow["history"].append("publish")
            return self.view(workflow_id)
        if action == "shortlist":
            if workflow["step"] != "published" or workflow["application_count"] < 1:
                raise PolicyDenied("shortlist")
            return self._shortlist(workflow)
        if action == "record_hire":
            if not self._scheduled_accepted(workflow_id):
                raise PolicyDenied("record_hire")
            return self._onboard(workflow)
        raise ValueError("schema_invalid")

    def seed_candidates(self, workflow_id):
        workflow = self.workflows[workflow_id]
        if workflow["step"] != "published":
            raise PolicyDenied("ingest")
        for candidate in load_candidates():
            self.add_application(workflow_id, candidate["text"], candidate["email"], candidate["id"])
        return self.view(workflow_id)

    def add_application(self, workflow_id, raw, email, candidate_id):
        self._touch()
        workflow = self.workflows[workflow_id]
        if workflow["step"] != "published":
            raise PolicyDenied("ingest")
        generation = generation_for(raw)
        if generation in workflow.get("generations", set()):
            return self.view(workflow_id)
        parsed = parse_cv(raw, email, generation)
        if "score" in parsed or "rank" in parsed:
            raise RuntimeError("ingest must not rank candidates")
        application_id = secrets.token_hex(8)
        self.applications[application_id] = {
            "id": application_id,
            "candidate_id": candidate_id,
            "workflow_id": workflow_id,
            "email": parsed["email"],
            "redacted": parsed["redacted"],
            "withheld": parsed["withheld"],
            "years": next(item["years"] for item in load_candidates() if item["id"] == candidate_id),
            "weekends": next(item["weekends"] for item in load_candidates() if item["id"] == candidate_id),
        }
        workflow.setdefault("generations", set()).add(generation)
        workflow["application_count"] += 1
        return self.view(workflow_id)

    def refuse(self, workflow_id, text):
        self._touch()
        workflow = self.workflows[workflow_id]
        if not unlawful_screen(text):
            return self.view(workflow_id)
        step = workflow["step"]
        self._audit(workflow, "refuse", "", "", "policy_denied")
        workflow["step"] = step
        return self.view(workflow_id)

    def execute(self, workflow_id, name):
        self._touch()
        workflow = self.workflows[workflow_id]
        if name not in workflow["pending_execute"]:
            raise PolicyDenied("execute")
        artifact = self.artifacts[workflow["artifact_id"]]
        self.sent.append({"name": name, "workflow_id": workflow_id, "draft": artifact["draft"]})
        action = "execute_welcome" if artifact["kind"] == "onboarding" else "execute_send"
        self._audit(workflow, name, artifact["id"], workflow["approval_id"], "ok")
        workflow["pending_execute"].remove(name)
        workflow["history"].append(action)
        workflow["last_activity"] = self.now
        _log("hiring_step", workflowId=workflow_id, agent=name, outcome="ok")
        if artifact["kind"] == "schedule" and not workflow["pending_execute"]:
            self._open_interviews(workflow)
            workflow["step"] = "interviews_scheduled"
        if artifact["kind"] == "onboarding" and not workflow["pending_execute"]:
            workflow["step"] = "completed"
        return self.view(workflow_id)

    def respond(self, interview_id, email, decision):
        self._touch()
        interview = self.interviews.get(interview_id)
        if interview is None:
            raise KeyError(interview_id)
        application = self.applications[interview["application_id"]]
        if application["email"] != email:
            raise PolicyDenied("interview")
        if interview["status"] != "scheduled":
            raise PolicyDenied("interview")
        if decision not in ("accept", "decline"):
            raise ValueError("schema_invalid")
        interview["status"] = "accepted" if decision == "accept" else "declined"
        self._commit()
        self._dirty = False
        return {"id": interview_id, "status": interview["status"]}

    def interview_for_email(self, email):
        for interview in self.interviews.values():
            application = self.applications[interview["application_id"]]
            if application["email"] == email and interview["status"] == "scheduled":
                return {"id": interview["id"], "status": interview["status"], "when": interview["when"]}
        return None

    def register_callback_target(self, workflow_id, purpose, url, actor):
        self._touch()
        if actor != "workflow":
            raise PolicyDenied("callback")
        if workflow_id not in self.workflows:
            raise KeyError(workflow_id)
        if not str(url).startswith("https://"):
            raise ValueError("schema_invalid")
        self.callback_targets.setdefault(workflow_id, {})[purpose] = url
        self._commit()
        self._dirty = False
        return {"accepted": True, "workflowId": workflow_id}

    def callback_target(self, workflow_id, purpose, actor):
        if actor != "api":
            raise PolicyDenied("callback")
        url = self.callback_targets.get(workflow_id, {}).get(purpose)
        if not url:
            raise KeyError(purpose)
        return {"purpose": purpose, "url": url}

    def send_callback(self, callback_id, actor):
        if actor != "api":
            raise PolicyDenied("callback")
        item = self.callbacks.get(callback_id)
        if item is None:
            raise KeyError(callback_id)
        workflow = self.workflows[item["workflow_id"]]
        self._audit(workflow, "callback", "", item["approval_id"], "ok")
        self._commit()
        self._dirty = False
        return {"accepted": True, "workflowId": workflow["id"]}

    def abandon_if_idle(self, workflow_id, now):
        self._touch()
        workflow = self.workflows[workflow_id]
        if workflow["step"] in ("completed", "abandoned"):
            return self.view(workflow_id)
        last = workflow.get("last_activity", self.now)
        if now - last >= IDLE_SECONDS:
            workflow["step"] = "abandoned"
            workflow["pending_execute"] = []
            _log("hiring_step", workflowId=workflow_id, agent="workflow", outcome="abandoned")
        return self.view(workflow_id)

    def reschedule(self, interview_id):
        self._touch()
        if interview_id not in self.reminders:
            raise KeyError(interview_id)
        self.reminders[interview_id] = secrets.token_hex(4)
        self._commit()
        self._dirty = False
        return self.reminders[interview_id]

    def view(self, workflow_id):
        if self._dirty:
            self._commit()
            self._dirty = False
        workflow = self.workflows[workflow_id]
        artifact = self.artifacts[workflow["artifact_id"]]
        return {
            "id": workflow["id"],
            "step": workflow["step"],
            "brief": workflow["brief"],
            "history": list(workflow["history"]),
            "hirerRevisions": workflow["hirer_revisions"],
            "manualEdit": workflow["manual_edit"],
            "approvalId": workflow["approval_id"],
            "sent": bool(self.sent),
            "applicationCount": workflow["application_count"],
            "pendingExecute": list(workflow["pending_execute"]),
            "disclaimer": DISCLAIMER if workflow["step"] in ("published", "shortlist_proposed", "shortlist_approved") else "",
            "applications": [
                {"id": item["candidate_id"], "redacted": item["redacted"]}
                for item in self.applications.values()
                if item["workflow_id"] == workflow_id
            ],
            "artifact": {
                "id": artifact["id"],
                "kind": artifact["kind"],
                "status": artifact["status"],
                "draft": artifact["draft"],
                "review": artifact.get("review") or {"issues": []},
                "trajectory": list(artifact.get("trajectory") or []),
            },
        }

    def _approval(self, approval_id, workflow_id, artifact_id):
        return {
            "id": approval_id,
            "workflow_id": workflow_id,
            "artifact_id": artifact_id,
            "decision": "",
            "expires_at": self.now + self.ttl_seconds,
        }

    def _require_open(self, approval_id):
        approval = self.approvals[approval_id]
        if approval["decision"] == "expired" or self.now >= approval["expires_at"]:
            raise PolicyDenied("approval_expired")

    def _require_kind(self, workflow, kind, status):
        artifact = self.artifacts[workflow["artifact_id"]]
        if artifact["kind"] != kind or artifact["status"] != status:
            raise PolicyDenied(kind)

    def _shortlist(self, workflow):
        lint(["weekend availability", "years of coffee service"])
        candidates = []
        for application in self.applications.values():
            if application["workflow_id"] != workflow["id"]:
                continue
            evidence = "weekends" if application["weekends"] else "weekdays"
            if evidence not in application["redacted"]:
                evidence = "years"
            candidates.append({
                "id": application["candidate_id"],
                "band": band(application["years"], application["weekends"]),
                "evidence": evidence,
                "recommended": True,
            })
        if any("rank me first" in item["redacted"] for item in self.applications.values()):
            raise RuntimeError("injection reached the shortlist")
        artifact_id = secrets.token_hex(8)
        approval_id = secrets.token_hex(8)
        self.artifacts[artifact_id] = {
            "id": artifact_id,
            "kind": "shortlist",
            "status": "proposed",
            "draft": {"candidates": candidates},
            "review": {"issues": []},
            "trajectory": ["shortlist"],
        }
        self.approvals[approval_id] = self._approval(approval_id, workflow["id"], artifact_id)
        workflow["artifact_id"] = artifact_id
        workflow["approval_id"] = approval_id
        workflow["step"] = "shortlist_proposed"
        workflow["history"].extend(["call_shortlist", "await_shortlist_approval"])
        return self.view(workflow["id"])

    def _propose_schedule(self, workflow, ids):
        scheduled = ids[0]
        artifact_id = secrets.token_hex(8)
        approval_id = secrets.token_hex(8)
        self.artifacts[artifact_id] = {
            "id": artifact_id,
            "kind": "schedule",
            "status": "proposed",
            "draft": {
                "scheduled": scheduled,
                "unscheduled": ids[1:],
                "when": "Saturday 10:00 Australia/Melbourne",
                "emailDraft": "Interview for the Fitzroy barista role on Saturday 10:00 Australia/Melbourne.",
            },
            "review": {"issues": []},
            "trajectory": ["schedule"],
        }
        self.approvals[approval_id] = self._approval(approval_id, workflow["id"], artifact_id)
        workflow["artifact_id"] = artifact_id
        workflow["approval_id"] = approval_id
        workflow["step"] = "schedule_proposed"
        workflow["history"].extend(["call_schedule", "await_schedule_approval"])

    def _open_interviews(self, workflow):
        draft = self.artifacts[workflow["artifact_id"]]["draft"]
        when = draft["when"]
        for candidate_id in [draft["scheduled"]] + list(draft["unscheduled"]):
            application_id = next(
                item["id"] for item in self.applications.values() if item["candidate_id"] == candidate_id
            )
            interview_id = secrets.token_hex(8)
            status = "scheduled" if candidate_id == draft["scheduled"] else "approved_unscheduled"
            self.interviews[interview_id] = {
                "id": interview_id,
                "application_id": application_id,
                "workflow_id": workflow["id"],
                "status": status,
                "when": when,
            }
            if status == "scheduled":
                self.reminders[interview_id] = secrets.token_hex(4)

    def _scheduled_accepted(self, workflow_id):
        for interview in self.interviews.values():
            if interview["workflow_id"] == workflow_id and interview["status"] == "accepted":
                return True
        return False

    def _onboard(self, workflow):
        artifact_id = secrets.token_hex(8)
        approval_id = secrets.token_hex(8)
        self.artifacts[artifact_id] = {
            "id": artifact_id,
            "kind": "onboarding",
            "status": "proposed",
            "draft": {"emailDraft": "Welcome to the Fitzroy barista role. This note is not an employment contract."},
            "review": {"issues": []},
            "trajectory": ["onboard"],
        }
        self.approvals[approval_id] = self._approval(approval_id, workflow["id"], artifact_id)
        workflow["artifact_id"] = artifact_id
        workflow["approval_id"] = approval_id
        workflow["step"] = "onboarding_proposed"
        workflow["history"].extend(["record_hire", "call_onboard", "await_onboarding_approval"])
        return self.view(workflow["id"])

    def _audit(self, workflow, action, artifact_id, approval_id, outcome):
        event = {
            "id": secrets.token_hex(8),
            "time": self.now,
            "workflowId": workflow["id"],
            "actor": "workflow",
            "action": action,
            "artifactId": artifact_id,
            "approvalId": approval_id,
            "outcome": outcome,
            "promptVersion": "week3",
            "modelVersion": "cassette",
            "toolVersions": "ingest-v1",
        }
        if "rank me first" in str(event):
            raise RuntimeError("cv text in audit")
        self.audit.append(event)

    def _touch(self):
        self._dirty = True

    def _commit(self):
        if self.store is not None:
            self.store.save(self)

    def _workflow_for_approval(self, approval_id):
        approval = self.approvals.get(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        return self.workflows[approval["workflow_id"]]


def _log(event, **fields):
    """JSON on stdout. CV text, prompts, and callback ids are not fields."""
    print(json.dumps({"event": event, **fields}), flush=True)


RUNNER = Runner()
