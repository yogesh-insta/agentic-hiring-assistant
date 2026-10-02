# ADR 2 — Two deterministic layers

Cloud Workflows owns the hire across days: approvals, expiry, and send. The ADK graph owns writer, reviewer, and the revise back-edge inside one HTTP call. The coordinator answers and starts neither. The model does not pick the next step or the next graph node.
