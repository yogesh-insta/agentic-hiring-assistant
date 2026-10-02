# ADR 10 — Region

Cloud Run, Firestore, Pub/Sub, Workflows, and Vertex are set to `australia-southeast1` in Terraform. Identity Platform and Google sign-in are global. They receive the account email. CVs and prompts stay in the region. No Gemini SKU exception is recorded, because this build has not selected a live model endpoint.
