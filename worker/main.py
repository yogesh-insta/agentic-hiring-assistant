"""CV ingest. Listens on PORT for Cloud Run and pulls Pub/Sub when configured.

Parsing and redaction live in worker.ingest. This process does not score,
drop, or resume a hiring workflow.
"""

import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RANKS_CANDIDATES = False


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"ok": True, "ranks": RANKS_CANDIDATES}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def handle_message(payload):
    """Return ack or retry. A poison payload retries until the subscription dead-letters it."""
    if RANKS_CANDIDATES:
        raise RuntimeError("ingest must not rank candidates")
    if payload.get("poison"):
        return "retry"
    workflow_id = str(payload.get("workflowId") or "")
    raw = str(payload.get("raw") or "")
    email = str(payload.get("email") or "")
    candidate_id = str(payload.get("candidateId") or "")
    if not workflow_id or not raw or not email or not candidate_id:
        return "retry"
    if "score" in payload or "rank" in payload:
        raise RuntimeError("ingest must not rank candidates")
    return "ack"


def deliver(payload, agents_url, authorization):
    decision = handle_message(payload)
    if decision != "ack":
        return decision
    body = json.dumps({
        "raw": payload["raw"],
        "email": payload["email"],
        "candidateId": payload["candidateId"],
    }).encode("utf-8")
    request = urllib.request.Request(
        agents_url.rstrip("/") + "/v1/workflows/" + payload["workflowId"] + "/application",
        data=body,
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", authorization)
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()
    return "ack"


def metadata_identity(audience):
    import urllib.parse

    url = (
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
        "?audience=" + urllib.parse.quote(audience, safe="") + "&format=full"
    )
    request = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return "Bearer " + response.read().decode("utf-8")


def pull_once(subscriber, subscription, agents_url, authorization):
    response = subscriber.pull(request={"subscription": subscription, "max_messages": 5}, timeout=10)
    ack_ids = []
    for received in response.received_messages:
        try:
            payload = json.loads(received.message.data.decode("utf-8"))
            if deliver(payload, agents_url, authorization) == "ack":
                ack_ids.append(received.ack_id)
        except Exception:
            continue
    if ack_ids:
        subscriber.acknowledge(request={"subscription": subscription, "ack_ids": ack_ids})


def serve(port):
    ThreadingHTTPServer(("0.0.0.0", port), Health).serve_forever()


def main() -> None:
    if RANKS_CANDIDATES:
        raise RuntimeError("ingest must not rank candidates")
    port = int(os.environ.get("PORT", "8080"))
    subscription = os.environ.get("PUBSUB_SUBSCRIPTION", "")
    if subscription:
        from threading import Thread

        def pull_loop():
            from google.cloud import pubsub_v1

            subscriber = pubsub_v1.SubscriberClient()
            project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            name = subscription if subscription.startswith("projects/") else subscriber.subscription_path(project, subscription)
            agents = os.environ["AGENTS_URL"]
            while True:
                try:
                    pull_once(subscriber, name, agents, metadata_identity(agents))
                except Exception as exc:
                    print(json.dumps({"event": "ingest_pull_error", "error": type(exc).__name__}), flush=True)
                    time.sleep(5)

        Thread(target=pull_loop, daemon=True).start()
        print("ingest listening and pulling", flush=True)
    else:
        print("ingest listening; no subscription", flush=True)
    serve(port)


if __name__ == "__main__":
    main()
