# ADR 9 — Telemetry

Spans and the JSON log line carry the workflow id, the agent, and the outcome. They do not carry prompt text, CV text, or callback URLs. There is no Langfuse project. Cloud Trace is the deployed store. Locally the line is `data/local/traces.jsonl`.
