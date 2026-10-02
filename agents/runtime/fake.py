from agents.pipelines.graph import run_job_ad
from agents.plain_call import fill_job_ad
from agents.schema import AgentInput, AgentResult, AgentSpec, RunContext


class FakeRuntime:
    """Walks a pipeline spec in plain Python. Week 1 has a single call."""

    async def run(self, agent: AgentSpec, data: AgentInput, ctx: RunContext) -> AgentResult:
        del ctx
        if agent.output_schema != "JobAd":
            raise ValueError(agent.output_schema)
        ad = fill_job_ad(data.brief)
        return AgentResult(output=ad.model_dump(), framework="fake")

    async def run_graph(self, brief: dict) -> dict:
        result = run_job_ad(brief)
        result["framework"] = "fake"
        return result
