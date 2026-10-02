"""ADK adapter boundary.

Week 1 returns the same cassette schema as the plain call so the two sides
can be compared. Week 2 compiles the job-ad graph here. This module does not
call Vertex.
"""

from agents.pipelines.graph import run_job_ad
from agents.plain_call import fill_job_ad
from agents.schema import AgentInput, AgentResult, AgentSpec, RunContext


class AdkRuntime:
    async def run(self, agent: AgentSpec, data: AgentInput, ctx: RunContext) -> AgentResult:
        del agent, ctx
        ad = fill_job_ad(data.brief)
        return AgentResult(output=ad.model_dump(), framework="adk")

    async def run_graph(self, brief: dict) -> dict:
        result = run_job_ad(brief)
        result["framework"] = "adk"
        return result
