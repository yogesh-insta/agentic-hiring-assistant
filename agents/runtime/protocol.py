from typing import Protocol

from agents.schema import AgentInput, AgentResult, AgentSpec, RunContext


class AgentRuntime(Protocol):
    async def run(self, agent: AgentSpec, data: AgentInput, ctx: RunContext) -> AgentResult:
        """Fill the agent's output schema. The caller validates it."""
