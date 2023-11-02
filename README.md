# cfn-lambda-ec2-scheduler

A CloudFormation stack that stops non-production EC2 instances in the evening
and starts them again in the morning. Instances opt in with a tag, so nothing
is touched unless someone asked for it.

```
EventBridge Scheduler ──{"action": "stop"}──▶ Lambda ──▶ EC2 instances tagged
   (local time zone)    {"action": "start"}            Schedule=office-hours
```

Stopping dev and test instances outside working hours is one of the easiest
cost cuts on AWS: a fleet that runs 12 hours on weekdays instead of 24x7 pays
for roughly a third of the compute hours.

## What the stack creates

| Resource | Purpose |
|----------|---------|
| Lambda function (Python 3.13, arm64) | Finds instances tagged `Schedule=<TagValue>` in the right state and starts or stops them |
| Two EventBridge Scheduler schedules | Invoke the function with `stop` and `start`, evaluated in your time zone |
| IAM role for the function | `DescribeInstances`, plus `StartInstances`/`StopInstances` only on instances carrying the tag |
| IAM role for the scheduler | Allowed to invoke this function only |
| Log group | Function logs with a fixed retention |
| CloudWatch alarm | Fires if the function errors, optionally notifying an SNS topic |

## Opting instances in

```bash
aws ec2 create-tags --resources i-0123456789abcdef0 --tags Key=Schedule,Value=office-hours
```

Use different tag values (and a second stack) for different schedules.

## Deploying

The function code lives in `src/`; `aws cloudformation package` uploads it to
an S3 bucket you own and rewrites the template to point at it.

```bash
make deploy BUCKET=my-artifacts-bucket
make deploy BUCKET=my-artifacts-bucket \
  PARAMS="Timezone=Europe/London StopScheduleExpression='cron(0 19 ? * MON-FRI *)'"
```

| Parameter | Default | |
|-----------|---------|-|
| `TagValue` | `office-hours` | Value of the `Schedule` tag this stack manages |
| `StopScheduleExpression` | `cron(0 20 ? * MON-FRI *)` | When to stop |
| `StartScheduleExpression` | `cron(0 8 ? * MON-FRI *)` | When to start |
| `Timezone` | `Asia/Kolkata` | Time zone for both schedules |
| `DryRun` | `false` | Log what would happen instead of acting |
| `LogRetentionDays` | `30` | Log retention |
| `AlarmTopicArn` | empty | SNS topic for the error alarm |

## Checking it safely

`make invoke-dry-run` invokes the deployed function with
`{"action": "stop", "dry_run": true}` and prints the instances it would stop,
without stopping them.

## How it behaves

- Only instances in the matching state are acted on: `stop` looks at
  `running` instances, `start` at `stopped` ones. Instances that are pending,
  stopping or terminated are skipped.
- Instance lookups are paginated and start/stop calls are batched, so large
  fleets are fine.
- Even if the function were invoked with an unexpected payload, its IAM role
  cannot start or stop an instance that doesn't carry the schedule tag.
- Each run logs one JSON line with the action, dry-run flag and instance IDs,
  which is easy to query in CloudWatch Logs Insights.

## Development

```bash
pip install -r requirements-dev.txt
make lint test
```

Tests run the handler against moto's EC2 mock: tagged versus untagged
instances, state filtering, dry runs and multi-batch fleets.
