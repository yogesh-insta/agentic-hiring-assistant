"""Budget consumer. A trip pins Cloud Run at zero instances.

Waiting Workflows executions are not cancelled. The runbook owns the reverse.
"""

import json
import os

SERVICES = ("hiring-api", "hiring-agents", "hiring-worker")
DEMO_MAX = {"hiring-api": 2, "hiring-agents": 1, "hiring-worker": 2}


def scale_to_zero(services=SERVICES):
    return [{"service": name, "maxInstanceCount": 0} for name in services]


def restore(max_instances=None):
    chosen = DEMO_MAX if max_instances is None else max_instances
    return [{"service": name, "maxInstanceCount": count} for name, count in chosen.items()]


def apply_scaling(plan):
    """Set Cloud Run max instances. Tests do not call this."""
    from google.cloud import run_v2

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    region = os.environ["REGION"]
    client = run_v2.ServicesClient()
    for item in plan:
        name = client.service_path(project, region, item["service"])
        service = client.get_service(name=name)
        from google.protobuf import field_mask_pb2

        service.template.scaling.max_instance_count = int(item["maxInstanceCount"])
        service.template.scaling.min_instance_count = 0
        client.update_service(
            service=service,
            update_mask=field_mask_pb2.FieldMask(paths=[
                "template.scaling.max_instance_count",
                "template.scaling.min_instance_count",
            ]),
        )


def on_budget(event, context=None):
    plan = scale_to_zero(tuple(filter(None, os.environ.get("SERVICES", ",".join(SERVICES)).split(","))))
    print(json.dumps({"event": "kill_switch_tripped", "services": plan}), flush=True)
    if os.environ.get("KILLSWITCH_APPLY", "1") != "0":
        apply_scaling(plan)
    return plan
