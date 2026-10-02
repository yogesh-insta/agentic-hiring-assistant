"""Job-ad graph shape.

Nodes are writer, reviewer, a function-node gate, and reviser. The revise
route is a back-edge, taken at most three times. The model does not choose it.
"""

WRITER_PROMPT = "Write a JobAd from the brief. Do not add a protected attribute."
REVIEWER_PROMPT = "Review the JobAd. Return a ReviewReport. Blocking issues are biased language and a missing pay line."
REVISER_PROMPT = "Revise the JobAd using the ReviewReport. Return a JobAd."

JOB_AD_TIMEOUT_SECONDS = 180
COORDINATOR_TIMEOUT_SECONDS = 60
WORKFLOW_HTTP_TIMEOUT_SECONDS = 200

EDGES = (
    ("START", "writer"),
    ("writer", "reviewer"),
    ("reviewer", "gate"),
    ("gate", "done", "END"),
    ("gate", "revise", "reviser"),
    ("reviser", "reviewer"),
)

MAX_REVISE = 3
