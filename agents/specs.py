"""Agent definitions. This module does not import Google ADK."""

AGENTS = {
    "coordinator": {
        "tier": "flash",
        "tools": (),
        "schema": "Reply",
    },
    "job_ad_writer": {
        "tier": "pro",
        "tools": ("role_templates.lookup", "award_rates.lookup"),
        "schema": "JobAd",
    },
    "job_ad_reviewer": {
        "tier": "pro",
        "tools": ("inclusive_language.check", "compliance_rules.check"),
        "schema": "ReviewReport",
    },
    "shortlister": {
        "tier": "pro",
        "tools": ("cv_store.read_redacted", "rubric.get"),
        "schema": "ShortlistProposal",
    },
    "scheduler": {
        "tier": "flash",
        "tools": ("calendar.free_busy", "calendar.propose", "email.draft"),
        "schema": "ScheduleProposal",
    },
    "onboarder": {
        "tier": "flash",
        "tools": ("checklist_templates.lookup", "email.draft"),
        "schema": "OnboardingPlan",
    },
}

EXECUTE_TOOLS = ("email.send", "calendar.create")


def allowed(agent, tool):
    return tool in AGENTS[agent]["tools"]
