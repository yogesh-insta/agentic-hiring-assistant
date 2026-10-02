PROHIBITED = (
    "name",
    "photo",
    "age",
    "date of birth",
    "address",
    "postcode",
    "school",
    "religion",
    "race",
    "national origin",
    "sex",
    "gender",
    "sexual orientation",
    "disability",
    "pregnancy",
    "parental",
    "carer",
    "industrial activity",
    "women",
    "men",
)


class PolicyDenied(Exception):
    pass


def lint(criteria):
    """Reject a rubric that encodes a protected attribute or a proxy."""
    for criterion in criteria:
        lowered = criterion.lower()
        for term in PROHIBITED:
            if term in lowered:
                raise PolicyDenied(term)
    return list(criteria)


def unlawful_screen(text: str) -> bool:
    lowered = text.lower()
    return "only women" in lowered or "only men" in lowered
