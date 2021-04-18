from aws_cdk import core as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_python as lambda_python
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager


class AwsNewreleaseSlackStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        """Default values if not specified via context variables from CLI
        logging_level = 'INFO'
        slack_webhook_secret_name = 'aws-to-slack/dev/webhooks'
        """
        if self.node.try_get_context('logging_level') is None:
            LOGGING_LEVEL = 'INFO'
        else:
            LOGGING_LEVEL = self.node.try_get_context('logging_level')
        if self.node.try_get_context('slack_webhook_secret_name') is None:
            WEBHOOK_SECRET_NAME = 'aws-to-slack/dev/webhooks'
        else:
            WEBHOOK_SECRET_NAME = self.node.try_get_context(
                'slack_webhook_secret_name')

        """Create CloudFormation parameters so we can easily use the
        template this CDK app generates and convert it to a SAM
        application.
        """
        webhook_secret_name_param = cdk.CfnParameter(
            self, 'WebhookSecretName',
            description=('The name of the Secrets Manager secret '
                         'which stores the Slack webhook URL'),
            type='String',
            default=WEBHOOK_SECRET_NAME,
            allowed_pattern='[a-zA-Z0-9/_+=.@-]+',
            min_length=1,
            max_length=512
        ).value_as_string
        whats_new_rss_feed = cdk.CfnParameter(
            self, 'WhatsNewRSSFeed',
            description='The RSS feed of all AWS new releases',
            type='String',
            default=self.node.try_get_context(
                'whats_new_rss_feed')
        ).value_as_string
        whats_new_search_api = cdk.CfnParameter(
            self, 'WhatsNewSearchAPI',
            description='The search API url of new releases',
            type='String',
            default=self.node.try_get_context(
                'whats_new_search_api')
        ).value_as_string
        logging_level = cdk.CfnParameter(
            self, 'LoggingLevel',
            description='The verbosity of the logs in the Lambda function',
            type='String',
            allowed_values=['INFO', 'ERROR', 'DEBUG', 'WARN'],
            default=LOGGING_LEVEL,
        ).value_as_string

        """DynamoDB table which stores a history of messages sent"""
        ddb_table = dynamodb.Table(
            self, 'SlackMessageHistory',
            partition_key=dynamodb.Attribute(
                name='url', type=dynamodb.AttributeType.STRING),
            read_capacity=1,
            write_capacity=1
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
                WHATS_NEW_RSS_FEED=whats_new_rss_feed,
                WHATS_NEW_SEARCH_API=whats_new_search_api,
                WEBHOOK_SECRET_NAME=webhook_secret_name_param,
                DDB_TABLE=ddb_table.table_name,
                LOG_LEVEL=logging_level,
                POWERTOOLS_SERVICE_NAME='aws-to-slack'
            ),
            memory_size=512,
            tracing=lambda_.Tracing.ACTIVE,
            timeout=cdk.Duration.seconds(30),
            log_retention=logs.RetentionDays.SIX_MONTHS
        )
        """Imports the SecretsManager secret which contains the Slack webhook url(s)
        and adds read access to the Lambda execution role
        """
        slack_webhook_urls = secretsmanager.Secret.from_secret_name_v2(
            self, "SlackWebhookURLSecrets",
            secret_name=webhook_secret_name_param
        )
        slack_webhook_urls.grant_read(new_release_function.role)

        """Invoke this function every X minutes"""
        rule = events.Rule(
            self, 'AWSReleaseToSlackRule',
            description='Schedule to invoke Lambda function that sends new AWS releases to Slack',
            schedule=events.Schedule.rate(cdk.Duration.minutes(5))
        )
        rule.add_target(events_targets.LambdaFunction(new_release_function))

        """Grant the Lambda function Query and PutItem access to the DDB table"""
        ddb_table.grant(
            new_release_function,
            'dynamodb:Query',
            'dynamodb:PutItem'
        )
