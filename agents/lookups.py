"""In-process lookups. They return a versioned snapshot, not a model call."""

AWARD = {
    "source": "data/synthetic/hospitality_award.json",
    "version": "week4",
    "summary": "Hospitality Award, level 2, about $32 an hour in the pinned snapshot.",
}

TEMPLATE = {
    "source": "data/synthetic/barista_brief.json",
    "version": "week4",
    "summary": "Part-time weekend barista.",
}


def award_rates_lookup(role):
    found = dict(AWARD)
    found["role"] = role
    return found


def role_templates_lookup(role):
    found = dict(TEMPLATE)
    found["role"] = role
    return found
