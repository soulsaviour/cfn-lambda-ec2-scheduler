STACK  ?= ec2-scheduler
REGION ?= ap-south-1
BUCKET ?=
PARAMS ?=

.PHONY: lint test package deploy invoke-dry-run

lint:
	cfn-lint template.yaml
	ruff check .

test:
	pytest -q

# Uploads src/ to S3 and writes packaged.yaml pointing at it.
package:
	@test -n "$(BUCKET)" || (echo "usage: make deploy BUCKET=<artifact bucket>" && exit 1)
	aws cloudformation package --region $(REGION) --template-file template.yaml \
	  --s3-bucket $(BUCKET) --s3-prefix $(STACK) --output-template-file packaged.yaml

deploy: package
	aws cloudformation deploy --region $(REGION) --stack-name $(STACK) \
	  --template-file packaged.yaml --capabilities CAPABILITY_IAM \
	  $(if $(PARAMS),--parameter-overrides $(PARAMS))

# See what a stop would do right now, without stopping anything.
invoke-dry-run:
	aws lambda invoke --region $(REGION) \
	  --function-name $$(aws cloudformation describe-stacks --region $(REGION) --stack-name $(STACK) \
	    --query 'Stacks[0].Outputs[?OutputKey==`FunctionName`].OutputValue' --output text) \
	  --cli-binary-format raw-in-base64-out \
	  --payload '{"action": "stop", "dry_run": true}' /dev/stdout
