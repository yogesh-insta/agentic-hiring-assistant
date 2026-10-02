from pathlib import Path

# Named before the first module that writes a hire. Week 1 does not start one.
COLLECTIONS = (
    "workflows",
    "artifacts",
    "applications",
    "interviews",
    "approvals",
    "audit",
    "callbacks",
)

RULES_PATH = Path(__file__).resolve().parents[1] / "infra" / "firestore.rules"


def client_denied_collections(rules_text: str) -> set:
    """Collections whose rules contain an unconditional client deny."""
    denied = set()
    current = None
    for line in rules_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("match /") and "/{" in stripped:
            name = stripped.split("/")[1].split("{")[0]
            current = name
        elif current and "allow read, write: if false" in stripped:
            denied.add(current)
            current = None
    return denied
