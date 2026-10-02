from agents.cost import measured_summary


def render_report(summary=None):
    summary = summary or measured_summary()
    return "\n".join([
        "# Latest eval",
        "",
        "Cassette gate only. This run did not call Vertex.",
        "",
        "| Workflow outcome | AUD |",
        "| --- | --- |",
        "| Completed | {0} |".format(summary["completed_aud"]),
        "| Partial | {0} |".format(summary["partial_aud"]),
        "| Abandoned | {0} |".format(summary["abandoned_aud"]),
        "",
        "Vertex calls: {0}.".format(summary["vertex_calls"]),
        "",
        summary["source"],
        "",
        "Judge calibration is 15 labels. Synthetic pairs are not a legal finding.",
        "",
    ])
