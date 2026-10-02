# ADR 4 — Propose, approve, execute

Agents write proposals. A button records the decision. Execute runs only when that approval left a name in `pending_execute`, and only with the workflow bearer. A hirer cookie on `/execute` is rejected. Reject clears the pending list and sends nothing.
