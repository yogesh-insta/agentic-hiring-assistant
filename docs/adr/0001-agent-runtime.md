# ADR 1 — AgentRuntime

The job-ad call has one schema and two runners. `FakeRuntime` and `AdkRuntime.run` both return a `JobAd`. `run_graph` walks the same cassette edges. The plain module does not import Google ADK. Swapping frameworks means a new adapter, not a new `hiring.yaml`.
