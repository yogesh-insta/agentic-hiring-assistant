# Runbook

## Turn the demo back on after the kill switch

A budget notification runs `on_budget`. Cloud Run max instances for `hiring-api`, `hiring-agents`, and `hiring-worker` go to 0. New revisions stop taking traffic.

Executions that were already waiting on `events.await_callback` keep waiting. They are stranded: the callback can still be delivered, and the next HTTP step fails until the services scale up. Do not cancel them to "clean up". Cancelling drops the hirer mid-approval.

Reverse:

1. Confirm the budget alert is cleared.
2. Set max instances back with `restore()` in `infra/killswitch/main.py`: API 2, agents 1, worker 2. Leave the agent service at 1. A second instance would split the Firestore snapshot.
3. Retry the failed HTTP step from the Workflows execution page. The step is idempotent on the approval id. A second execute of the same send does not run unless that name is still in `pending_execute`.

## Stuck approval

The proposal stays `proposed` after a 7-day expiry. It does not complete and it does not send. The hirer can approve or reject again from the panel. A hire with no activity for 14 days becomes `abandoned` and sends nothing.

## Dead letter

`cv-dead-letter` receives a CV after 5 failed deliveries. The alert fires when that subscription is non-empty. Inspect the generation id. Do not put the CV text in the ticket. Fix the parser, then replay the message. A duplicate generation is ignored.

## Injection

A CV that says "rank me first" is stripped before it is stored. If that phrase shows up in an application, a shortlist, or an audit event, stop the hire and treat it as a failed control. The workflow step should be unchanged.

## Callback URL

The URL from `events.create_callback_endpoint` stays inside the execution. It is not a field on the API view and it is not a log line. A browser cookie on `/callbacks/{id}` is rejected.
