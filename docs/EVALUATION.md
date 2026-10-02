# Evaluation

Golden sets are 10 cases each, in `evals/cassettes/job_ad_graph.json` and `evals/cassettes/shortlist.json`. A changed prompt raises `CassetteMiss`. Tests do not call Vertex.

| Agent | Cases | What the gate checks |
| --- | --- | --- |
| Job-ad graph | 10 | Trajectory, review schema, revise cap |
| Shortlister | 10 | Band from weekends and years, evidence is a substring of the redacted CV |
| Coordinator | cassette | A question has no brief. A Fitzroy barista sentence does |

Judge calibration is 15 labels in `evals/datasets/judge_labels.json`. Agreement is 14/15, above the 0.8 threshold. The stored judge is the cassette label, not a live model. A set below 0.8 is not trusted.

Fairness: one counterfactual pair changes the name and leaves years and weekends alone. The band does not move, and the recommended set does not gain or lose a person. These are synthetic pairs. They are not a study of real applicants, and they are not a defence under the Fair Work Act, the federal anti-discrimination acts, or the Victorian Equal Opportunity Act.

The unlawful set is `interview only women`. The step stays put and the audit outcome is `policy_denied`.
