"""HTTP front for the agent library. Week 1 streams a cassette."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agents.identity import actor
from agents.plain_call import CassetteMiss, fill_job_ad
from guardrails.rubric import PolicyDenied
from services.agents.hiring import RUNNER
from services.agents.turn import coordinator_events, format_sse


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Token text is not a log line. The default logger prints the path only.
        return super().log_message(fmt, *args)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True})
            return
        if self.path == "/v1/interviews/mine":
            email = self.headers.get("X-Actor-Email", "")
            found = RUNNER.interview_for_email(email)
            if found is None:
                self._json(404, {"failureClass": "tool_error"})
                return
            self._json(200, found)
            return
        if self.path.startswith("/v1/internal/callback-target"):
            self._read_callback_target()
            return
        if self.path.startswith("/v1/workflows/"):
            workflow_id = self.path.split("/")[-1]
            try:
                self._json(200, RUNNER.view(workflow_id))
            except KeyError:
                self._json(404, {"failureClass": "tool_error"})
            return
        self._json(404, {"failureClass": "tool_error"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"failureClass": "schema_invalid"})
            return
        if self.path == "/v1/turns":
            self._stream_turn(body)
            return
        if self.path == "/v1/job-ad":
            self._job_ad(body)
            return
        if self.path == "/v1/workflows":
            self._confirm(body)
            return
        if self.path.startswith("/v1/approvals/") and self.path.endswith("/approve"):
            self._decide(self.path.split("/")[3], "approve", body)
            return
        if self.path.startswith("/v1/approvals/") and self.path.endswith("/reject"):
            self._decide(self.path.split("/")[3], "reject", body)
            return
        if self.path.startswith("/v1/workflows/") and self.path.endswith("/continue"):
            self._continue(self.path.split("/")[3], body)
            return
        if self.path.startswith("/v1/workflows/") and self.path.endswith("/applications"):
            self._seed(self.path.split("/")[3])
            return
        if self.path.startswith("/v1/workflows/") and self.path.endswith("/refuse"):
            self._refuse(self.path.split("/")[3], body)
            return
        if self.path == "/v1/internal/callback-target":
            self._register_callback_target(body)
            return
        if self.path.startswith("/v1/workflows/") and self.path.endswith("/application"):
            self._one_application(self.path.split("/")[3], body)
            return
        if self.path.startswith("/v1/execute/"):
            self._execute(self.path.split("/")[-1], body)
            return
        if self.path.startswith("/v1/callbacks/"):
            self._callback(self.path.split("/")[-1])
            return
        if self.path == "/v1/interviews/respond":
            self._respond(body)
            return
        self._json(404, {"failureClass": "tool_error"})

    def _stream_turn(self, body):
        events = coordinator_events(str(body.get("messageId", "")), str(body.get("text", "")))
        payload = "".join(format_sse(name, data) for name, data in events).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _confirm(self, body):
        try:
            view = RUNNER.confirm(body.get("brief") or {}, body.get("workflowId") or None)
        except CassetteMiss:
            self._json(422, {"failureClass": "schema_invalid"})
            return
        self._json(200, view)

    def _guard(self, call):
        try:
            self._json(200, call())
        except KeyError:
            self._json(404, {"failureClass": "tool_error"})
        except PolicyDenied:
            self._json(403, {"failureClass": "policy_denied"})
        except (ValueError, CassetteMiss):
            self._json(422, {"failureClass": "schema_invalid"})

    def _decide(self, approval_id, decision, body):
        if decision == "approve":
            self._guard(lambda: RUNNER.approve(approval_id, body.get("candidateIds")))
            return
        self._guard(lambda: RUNNER.reject(approval_id, str(body.get("note") or "")))

    def _continue(self, workflow_id, body):
        self._guard(lambda: RUNNER.continue_hire(workflow_id, str(body.get("action") or "")))

    def _seed(self, workflow_id):
        self._guard(lambda: RUNNER.seed_candidates(workflow_id))

    def _refuse(self, workflow_id, body):
        self._guard(lambda: RUNNER.refuse(workflow_id, str(body.get("text") or "")))

    def _execute(self, name, body):
        if actor(self.headers.get("Authorization", ""), "workflow") != "workflow":
            self._json(403, {"failureClass": "policy_denied"})
            return
        self._guard(lambda: RUNNER.execute(str(body.get("workflowId") or ""), name))

    def _callback(self, callback_id):
        if actor(self.headers.get("Authorization", ""), "api") != "api":
            self._json(403, {"failureClass": "policy_denied"})
            return
        self._guard(lambda: RUNNER.send_callback(callback_id, "api"))

    def _register_callback_target(self, body):
        if actor(self.headers.get("Authorization", ""), "workflow") != "workflow":
            self._json(403, {"failureClass": "policy_denied"})
            return
        self._guard(lambda: RUNNER.register_callback_target(
            str(body.get("workflowId") or ""),
            str(body.get("purpose") or ""),
            str(body.get("url") or ""),
            "workflow",
        ))

    def _read_callback_target(self):
        if actor(self.headers.get("Authorization", ""), "api") != "api":
            self._json(403, {"failureClass": "policy_denied"})
            return
        query = self.path.split("?", 1)[-1] if "?" in self.path else ""
        fields = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
        self._guard(lambda: RUNNER.callback_target(
            fields.get("workflowId", ""),
            fields.get("purpose", ""),
            "api",
        ))

    def _one_application(self, workflow_id, body):
        header = self.headers.get("Authorization", "")
        if actor(header, "workflow") != "workflow" and actor(header, "worker") != "worker":
            self._json(403, {"failureClass": "policy_denied"})
            return
        self._guard(lambda: RUNNER.add_application(
            workflow_id,
            str(body.get("raw") or ""),
            str(body.get("email") or ""),
            str(body.get("candidateId") or ""),
        ))

    def _respond(self, body):
        email = self.headers.get("X-Actor-Email", "")
        self._guard(lambda: RUNNER.respond(str(body.get("interviewId") or ""), email, str(body.get("decision") or "")))

    def _job_ad(self, body):
        try:
            ad = fill_job_ad(body.get("brief") or {})
        except CassetteMiss:
            self._json(422, {"failureClass": "schema_invalid"})
            return
        self._json(200, ad.model_dump())

    def _json(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    port = int(os.environ.get("PORT", "8090"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("agents listening on {0}".format(port), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
