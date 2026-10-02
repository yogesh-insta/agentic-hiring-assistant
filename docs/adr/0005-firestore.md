# ADR 5 — Firestore

Seven collections hold the hire. Client rules deny all of them. Firestore was chosen over Cloud SQL because the demo should scale to zero and the documents are the workflow, the artifact, and the audit event. There is no relational reporting workload in this build.
