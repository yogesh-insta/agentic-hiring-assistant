# ADR 11 — Identity Platform, not IAP

People sign in through Identity Platform. Services sign in through IAM. The API service account may send a callback. The workflow service account may execute. A candidate is not an IAM user.

The client cannot grant itself `role=hirer`. After a verified token, the role comes from the server allowlist. `ENV=local` accepts two fixed users and mints an HMAC session cookie. An email with no ID token is rejected when `ENV` is not `local`. IAP is not used, because candidates are external.
