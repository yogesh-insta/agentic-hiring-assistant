# Agentic Hiring Assistant

A hiring product for small-business hirers, built on Google Cloud (Vertex AI, Cloud Run, Firestore, Pub/Sub, Cloud Workflows). Python and Google ADK run the agents. Go is the public API and the chat stream. TypeScript is the hirer chat and the candidate page.

Specialist agents help a hirer write and improve a job ad, shortlist candidates fairly, schedule interviews, and onboard a new hire. The focus is the engineering around the agents: evaluation, security, cost control, reliability, observability, and framework independence.

**Status:** week 4, not deployed. The local hire runs from a brief to a welcome email on the same step ids as `workflow/hiring.yaml`. Cloud mode signs in with an Identity Platform token, stores the hire in Firestore, and lets Cloud Workflows own the pauses. Terraform for `australia-southeast1` is in `infra/terraform` and has not been applied. Build images with `cloudbuild.yaml` before apply. The measured cost of one completed cassette workflow is **AUD 0.00**, because that run does not call Vertex. See [docs/PLAN.md](docs/PLAN.md).

```mermaid
flowchart LR
  hirerUI[Hirer chat] --> api[Go API]
  candidateUI[Candidate page] --> api
  api --> hiring[hiring.yaml]
  hiring --> graph[Job-ad graph]
  hiring --> execute[Execute]
  api --> worker[Ingest]
```

## Scores

Cassette gate, no Vertex call. Judge calibration is 14/15 on 15 labels, threshold 0.8. Details in [docs/EVALUATION.md](docs/EVALUATION.md).

| Check | Result |
| --- | --- |
| Job-ad graph, 10 cases | Pass |
| Shortlist, 10 cases | Pass |
| Completed workflow | AUD 0.00 |
| Partial workflow | AUD 0.00 |
| Abandoned workflow | AUD 0.00 |

## Run

```bash
make test
```

Then, from the repo root, in two terminals:

```bash
make agents
make api
```

Open http://127.0.0.1:8080 and sign in as the hirer. The candidate page is http://127.0.0.1:8080/interview. `make up` starts the same services in Docker with the Firestore emulator, the Pub/Sub emulator, and a trace collector. `make trace` writes one local job-ad trace under `data/local/traces.jsonl`.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Runbook](docs/RUNBOOK.md)
- [Cost model](docs/COST_MODEL.md)
- [Evaluation](docs/EVALUATION.md)
- [Concepts](docs/CONCEPTS.md)
- [ADRs](docs/adr/0001-agent-runtime.md)

## Clean-room notice

This is an independent personal project. All data is synthetic. It contains no code, data, prompts, or designs from any employer.

## License

[MIT](LICENSE)
