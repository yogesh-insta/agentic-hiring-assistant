"""Cost ledger for one hiring workflow.

The cassette path records zero tokens and AUD 0.00 because it does not call
Vertex. Eval spend is a separate list and cannot fill the demo ceiling.
"""

from decimal import Decimal

TOKEN_BUDGET = 8000
CEILING_AUD = Decimal("1.00")
EVAL_CAP_AUD = Decimal("5.00")


class CostCeiling(Exception):
    pass


class Ledger:
    def __init__(self):
        self.rows = []
        self.eval_rows = []

    def record(self, workflow_id, agent, model, tokens_in, tokens_out, aud, bucket="demo"):
        incoming = int(tokens_in)
        outgoing = int(tokens_out)
        amount = Decimal(str(aud))
        if incoming + outgoing > TOKEN_BUDGET:
            raise CostCeiling("token_budget")
        target = self.eval_rows if bucket == "eval" else self.rows
        cap = EVAL_CAP_AUD if bucket == "eval" else CEILING_AUD
        spent = sum((row["aud"] for row in target if row["workflow_id"] == workflow_id), Decimal("0"))
        if spent + amount > cap:
            raise CostCeiling("workflow_ceiling")
        target.append({
            "workflow_id": workflow_id,
            "agent": agent,
            "model": model,
            "tokens_in": incoming,
            "tokens_out": outgoing,
            "aud": amount,
            "bucket": bucket,
        })
        return target[-1]

    def total(self, workflow_id):
        return sum((row["aud"] for row in self.rows if row["workflow_id"] == workflow_id), Decimal("0"))


LEDGER = Ledger()


def measured_summary():
    """The completed-workflow number from the offline hire, not a price guess."""
    return {
        "completed_aud": "0.00",
        "partial_aud": "0.00",
        "abandoned_aud": "0.00",
        "vertex_calls": 0,
        "source": "One completed cassette hire. No Vertex request was made, so the ledger is AUD 0.00.",
    }
