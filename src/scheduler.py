"""Start or stop EC2 instances tagged Schedule=<TAG_VALUE>.

Invoked by EventBridge Scheduler with {"action": "start"} or {"action": "stop"}.
Set DRY_RUN=true to log what would happen without touching any instance.
"""

import json
import logging
import os

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

TAG_KEY = "Schedule"

# The state an instance must be in for each action. Instances that are
# pending, stopping, shutting down or terminated are left alone.
ACTIONABLE_STATE = {"stop": "running", "start": "stopped"}

# StartInstances/StopInstances take many IDs per call; keep batches modest.
BATCH_SIZE = 50


def find_instances(ec2, tag_value, state):
    """Sorted IDs of instances tagged for the schedule and in the given state."""
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[
            {"Name": f"tag:{TAG_KEY}", "Values": [tag_value]},
            {"Name": "instance-state-name", "Values": [state]},
        ]
    )
    return sorted(
        instance["InstanceId"]
        for page in pages
        for reservation in page["Reservations"]
        for instance in reservation["Instances"]
    )


def handler(event, context=None, ec2=None):
    action = (event or {}).get("action")
    if action not in ACTIONABLE_STATE:
        raise ValueError(f"action must be 'start' or 'stop', got {action!r}")

    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    ec2 = ec2 or boto3.client("ec2")

    instance_ids = find_instances(ec2, os.environ["TAG_VALUE"], ACTIONABLE_STATE[action])
    result = {"action": action, "dry_run": dry_run, "instances": instance_ids}

    if instance_ids and not dry_run:
        call = ec2.stop_instances if action == "stop" else ec2.start_instances
        for start in range(0, len(instance_ids), BATCH_SIZE):
            call(InstanceIds=instance_ids[start : start + BATCH_SIZE])

    log.info(json.dumps(result))
    return result
