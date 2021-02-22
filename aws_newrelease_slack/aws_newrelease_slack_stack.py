from aws_cdk import core
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_python as lambda_python
from aws_cdk import aws_logs as logs


class AwsNewreleaseSlackStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        """DynamoDB table which stores a history of messages sent"""
        ddb_table = dynamodb.Table(
            self, 'SlackMessageHistory',
            partition_key=dynamodb.Attribute(name='id', type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        """Lambda function that queries the AWS What's New RSS feed
        and sends each release to Slack if it has not already been sent.
        """
        new_release_function = lambda_python.PythonFunction(
            self, 'AWSReleasesFunction',
            entry='lambda',
            handler='main',
            index='new_releases.py',
            runtime=lambda_.Runtime.PYTHON_3_8,
            description='Queries https://aws.amazon.com/new/ and sends new release info to a Slack channel via AWS Chatbot',
            environment=dict(
                WHATS_NEW_URL=self.node.try_get_context('whats_new_url'),
                WEBHOOK_URL=self.node.try_get_context('slack_webhook_url'),
                DDB_TABLE=ddb_table.table_name
            ),
            memory_size=512,
            tracing=lambda_.Tracing.ACTIVE,
            timeout=core.Duration.seconds(60),
            log_retention=logs.RetentionDays.SIX_MONTHS
        )

        """Invoke this function every X minutes"""
        rule = events.Rule(
            self, 'AWSReleaseToSlackRule',
            description='Schedule to invoke Lambda function that sends new AWS releases to Slack',
            schedule=events.Schedule.rate(core.Duration.minutes(5))
        )
        rule.add_target(events_targets.LambdaFunction(new_release_function))

        """Grant the Lambda function read / write access to the DDB table"""
        ddb_table.grant_read_write_data(new_release_function)