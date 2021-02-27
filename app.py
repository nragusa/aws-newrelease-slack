#!/usr/bin/env python3

from aws_cdk import core
from aws_newrelease_slack.aws_newrelease_slack_stack import AwsNewreleaseSlackStack

app = core.App()
dev_new_releases_stack = AwsNewreleaseSlackStack(app, 'aws-newrelease-slack-dev')
core.Tags.of(dev_new_releases_stack).add('Project', 'AWS New Releases Chatbot')
core.Tags.of(dev_new_releases_stack).add('Environment', 'Dev')

prod_new_releases_stack = AwsNewreleaseSlackStack(app, 'aws-newrelease-slack-prod')
core.Tags.of(prod_new_releases_stack).add('Project', 'AWS New Releases Chatbot')
core.Tags.of(prod_new_releases_stack).add('Environment', 'Prod')
app.synth()
