# Cost model

## Measured

One completed cassette hire records:

| Outcome | AUD |
| --- | --- |
| Completed | 0.00 |
| Partial | 0.00 |
| Abandoned | 0.00 |

Vertex calls on that run: 0. The ledger row is the job-ad cassette with 0 tokens. That is the measurement. It is not an invoice and it is not a token-price estimate.

The same figure is in `evals/reports/latest.md`.

## Caps in code

- A model call above 8,000 tokens is refused.
- A demo workflow above AUD 1.00 is refused.
- Eval rows sit on a separate AUD 5.00 cap. They do not add to the demo total and they do not trip the kill switch.

## Caps in Terraform

The billing budget is AUD 50 at 50%, 90%, and 100%. The 100% notification publishes to `hiring-budget`. The kill switch function logs `kill_switch_tripped` and sets max instances to 0 on the three Cloud Run services. Waiting Workflows executions keep waiting. `restore()` in `infra/killswitch/main.py` puts the API back at 2, the agent service at 1, and the worker at 2. The steps are in `docs/RUNBOOK.md`.

## What this file does not do

There is no projected monthly cost at 10, 100, or 1,000 workflows a day. That projection needs token counts from a live Vertex run. Inventing them would make the headline look measured when it is not.
