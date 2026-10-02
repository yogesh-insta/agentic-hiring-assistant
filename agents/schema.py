from pydantic import BaseModel, ConfigDict, Field


class JobAd(BaseModel):
    """Structured ad. Week 1 fills this from a cassette, not from a graph."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    pay: str = Field(min_length=1)
    hours: str = Field(min_length=1)
    body: str = Field(min_length=1)


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str = ""
    kind: str = Field(min_length=1)
    blocking: bool = True


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[ReviewIssue]
    suggested_edits: list[str] = []

    def blocking_issues(self):
        return [issue for issue in self.issues if issue.blocking]


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    prompt: str
    model_tier: str
    output_schema: str


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: dict


class RunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal: str = "local"


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: dict
    framework: str


JOB_AD_SPEC = AgentSpec(
    name="job_ad_plain",
    prompt="Write a job ad from the confirmed brief. Return only the JobAd fields.",
    model_tier="strong",
    output_schema="JobAd",
)
