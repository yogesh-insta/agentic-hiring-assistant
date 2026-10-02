import json
from pathlib import Path

LABELS_PATH = Path(__file__).resolve().parents[1] / "datasets" / "judge_labels.json"
THRESHOLD = 0.8


def agreement(labels):
    if len(labels) != 15:
        raise ValueError("calibration set must hold 15 labels")
    matched = sum(1 for item in labels if item["human"] == item["judge"])
    return matched / len(labels)


def load_labels():
    return json.loads(LABELS_PATH.read_text(encoding="utf-8"))


def judge_is_trusted(labels=None):
    score = agreement(load_labels() if labels is None else labels)
    return score >= THRESHOLD, score
