from agents.pipelines.graph import load_graph_cassette
from guardrails.rubric import PolicyDenied
from services.agents.hiring import Runner


def barista_brief():
    return next(case["brief"] for case in load_graph_cassette()["cases"] if case["id"] == "barista-fitzroy")


def test_confirm_with_the_same_workflow_id_does_not_duplicate():
    runner = Runner()
    first = runner.confirm(barista_brief(), workflow_id="fixed-hire")
    second = runner.confirm(barista_brief(), workflow_id="fixed-hire")
    assert first["id"] == "fixed-hire"
    assert second["approvalId"] == first["approvalId"]
    assert second["history"].count("confirm_brief") == 1


def test_callback_url_stays_out_of_the_view():
    runner = Runner()
    view = runner.confirm(barista_brief(), workflow_id="fixed-hire")
    stored = runner.register_callback_target(
        view["id"], "ad_approval", "https://workflow.example/callback", "workflow"
    )
    assert "url" not in stored
    again = runner.view(view["id"])
    assert "callback" not in again
    assert "https://workflow.example/callback" not in str(again)
    found = runner.callback_target(view["id"], "ad_approval", "api")
    assert found["url"] == "https://workflow.example/callback"


def test_callback_target_requires_the_workflow_actor_and_https():
    runner = Runner()
    view = runner.confirm(barista_brief(), workflow_id="fixed-hire")
    try:
        runner.register_callback_target(view["id"], "ad_approval", "https://workflow.example/callback", "api")
    except PolicyDenied:
        pass
    else:
        raise AssertionError("api actor must not register a callback")
    try:
        runner.register_callback_target(view["id"], "ad_approval", "http://workflow.example/callback", "workflow")
    except ValueError:
        pass
    else:
        raise AssertionError("callback url must be https")
