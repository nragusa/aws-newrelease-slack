#!/usr/bin/env python3

from aws_cdk import core
from aws_newrelease_slack.aws_newrelease_slack_stack import AwsNewreleaseSlackStack

app = core.App()
new_releases_stack = AwsNewreleaseSlackStack(app, 'aws-newrelease-slack')
core.Tags.of(new_releases_stack).add('Project', 'AWS New Releases Chatbot')
core.Tags.of(new_releases_stack).add('Environment', 'Development')

app.synth()
