# Threat model

Controls in this repo, and the tests that exercise them. This is not a penetration test.

| Threat | Example | Control | Test |
| --- | --- | --- | --- |
| Indirect prompt injection | CV says "rank me first" | Strip the instruction before redact and score | `worker/tests/test_ingest.py`, `services/agents/tests/test_hire.py` |
| Tool misuse | A writer calls `email.send` | Execute tools are absent from agent specs. Execute checks the workflow bearer | `agents/tests/test_week4.py`, `services/api/server_test.go` |
| Data leakage | Email or CV text in a trace or audit event | Output scan, audit rejects the injection phrase, traces record ids | `guardrails/tests/test_output_scan.py` |
| Unlawful instruction | "interview only women" | Refuse, leave the step, audit `policy_denied` | `services/agents/tests/test_hire.py` |
| Excessive agency | Revise loop or a 14-day idle hire | Gate cap 3. Idle hire becomes `abandoned` and sends nothing | `agents/tests/test_graph.py`, `agents/tests/test_week4.py` |
| Audit tampering | Update an audit row | The runner only appends | `services/agents/hiring.py` |
| Forged execute or callback | Hirer cookie posts `/execute` or `/callbacks/{id}` | Cookie is 403. Callback send requires the API bearer. The view has no callback URL | `TestHirerCookieCannotExecute`, `TestForgedCallbackDoesNotReachTheAgent` |
| Privilege escalation | Client sets `role=hirer` | Role comes from the server allowlist | `TestClaimedRoleCannotGrantHirer` |
| Real data in the demo | A visitor pastes a CV | Banner on both pages. Seed login exists only when `ENV=local` | Pages and `TestSeedLoginIsAbsentOutsideLocal` |
| Cross-candidate access | Avery accepts Blake's interview | Email must match the application | `test_hire_runs_from_brief_to_welcome_email` |

Firestore client rules deny every collection, including `callbacks` and `audit`.
