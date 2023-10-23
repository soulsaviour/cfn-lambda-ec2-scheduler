"""Start or stop EC2 instances tagged Schedule=<TAG_VALUE>.

Invoked with {"action": "start"} or {"action": "stop"}.
"""

import json
import logging
import os

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

TAG_KEY = "Schedule"


def handler(event, context=None):
    action = (event or {}).get("action")
    if action not in ("start", "stop"):
        raise ValueError(f"action must be 'start' or 'stop', got {action!r}")

    ec2 = boto3.client("ec2")
    response = ec2.describe_instances(
        Filters=[{"Name": f"tag:{TAG_KEY}", "Values": [os.environ["TAG_VALUE"]]}]
    )
    instance_ids = [
        instance["InstanceId"]
        for reservation in response["Reservations"]
        for instance in reservation["Instances"]
    ]

    if instance_ids:
        if action == "stop":
            ec2.stop_instances(InstanceIds=instance_ids)
        else:
            ec2.start_instances(InstanceIds=instance_ids)

    log.info(json.dumps({"action": action, "instances": instance_ids}))
    return {"action": action, "instances": instance_ids}
