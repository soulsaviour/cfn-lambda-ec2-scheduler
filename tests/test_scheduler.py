import boto3
import pytest
from moto import mock_aws

import scheduler

REGION = "ap-south-1"


@pytest.fixture
def ec2(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("TAG_VALUE", "office-hours")
    monkeypatch.delenv("DRY_RUN", raising=False)
    with mock_aws():
        yield boto3.client("ec2", region_name=REGION)


def launch(ec2, count=1, schedule=None):
    image_id = ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]
    kwargs = {}
    if schedule:
        kwargs["TagSpecifications"] = [
            {"ResourceType": "instance", "Tags": [{"Key": "Schedule", "Value": schedule}]}
        ]
    response = ec2.run_instances(ImageId=image_id, MinCount=count, MaxCount=count, **kwargs)
    return sorted(i["InstanceId"] for i in response["Instances"])


def state(ec2, instance_id):
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    return reservations[0]["Instances"][0]["State"]["Name"]


def test_stop_only_touches_tagged_running_instances(ec2):
    tagged = launch(ec2, 2, schedule="office-hours")
    other_schedule = launch(ec2, schedule="always-on")
    untagged = launch(ec2)

    result = scheduler.handler({"action": "stop"}, ec2=ec2)

    assert result["instances"] == tagged
    assert all(state(ec2, i) == "stopped" for i in tagged)
    assert state(ec2, other_schedule[0]) == "running"
    assert state(ec2, untagged[0]) == "running"


def test_start_only_picks_up_stopped_instances(ec2):
    stopped = launch(ec2, schedule="office-hours")
    running = launch(ec2, schedule="office-hours")
    ec2.stop_instances(InstanceIds=stopped)

    result = scheduler.handler({"action": "start"}, ec2=ec2)

    assert result["instances"] == stopped
    assert state(ec2, stopped[0]) == "running"
    assert state(ec2, running[0]) == "running"


def test_dry_run_changes_nothing(ec2, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    tagged = launch(ec2, schedule="office-hours")

    result = scheduler.handler({"action": "stop"}, ec2=ec2)

    assert result == {"action": "stop", "dry_run": True, "instances": tagged}
    assert state(ec2, tagged[0]) == "running"


def test_dry_run_can_be_requested_per_invocation(ec2):
    tagged = launch(ec2, schedule="office-hours")

    result = scheduler.handler({"action": "stop", "dry_run": True}, ec2=ec2)

    assert result["dry_run"] is True
    assert state(ec2, tagged[0]) == "running"


def test_handles_more_instances_than_one_batch(ec2):
    tagged = launch(ec2, scheduler.BATCH_SIZE + 10, schedule="office-hours")

    result = scheduler.handler({"action": "stop"}, ec2=ec2)

    assert len(result["instances"]) == len(tagged)
    assert all(state(ec2, i) == "stopped" for i in tagged)


def test_nothing_to_do(ec2):
    assert scheduler.handler({"action": "start"}, ec2=ec2)["instances"] == []


@pytest.mark.parametrize("event", [{}, {"action": "reboot"}, None])
def test_rejects_unknown_actions(ec2, event):
    with pytest.raises(ValueError):
        scheduler.handler(event, ec2=ec2)
