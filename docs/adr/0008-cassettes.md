# ADR 8 — Cassettes

Tests and the PR gate replay `evals/cassettes`. A prompt or brief mismatch raises `CassetteMiss`. Regenerating a cassette would be a separate live run on the eval budget. The demo kill switch does not see that budget.
