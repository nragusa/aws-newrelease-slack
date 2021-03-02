"""Sends a Slack message of articles that were posted in the AWS 
'What's New' news feed.

This lambda function grabs an RSS feed that is generated at
http://aws.amazon.com/new/feed/. It iterates over each article and
checks if the ID of the article exists in a DynamoDB table. If the
ID is not found, it will send a message to Slack with the new release
title, link, and description.

The function is intended to run every 5 minutes. Since the
feed doesn't change that often, when the script determines the ID is already
in DynamoDB it ignores it and moves on.
"""
import boto3
import feedparser
import json
import os
import urllib3
from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.utilities import parameters
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

logger = Logger()
tracer = Tracer(patch_modules=['boto3', 'httplib'])

WHATS_NEW_URL = os.environ['WHATS_NEW_URL']
WEBHOOK_SECRET_NAME = os.environ['WEBHOOK_SECRET_NAME']
DDB_TABLE = os.environ['DDB_TABLE']

def has_been_slacked(entry_id):
    """Returns true if the post ID is found in DDB table"""
    logger.debug(f'Querying DDB for id = {entry_id}')
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(DDB_TABLE)
    response = table.query(KeyConditionExpression=Key('id').eq(entry_id))
    if response['Count'] != 0:
        return True
    else:
        return False

def post_slack(slack_msg, urls, connection):
    """Posts the message to Slack webhook endpoint"""
    logger.debug(f'{json.dumps(slack_msg)}')
    try:
        logger.info(f'Posting to Slack: {slack_msg["text"]}')
        for url in urls:
            post = connection.request(
                'POST',
                url,
                body=json.dumps(slack_msg).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
    except urllib3.exceptions.HTTPError as error:
        logger.error(f'Problem posting release to slack: {error}')


def log_slack(entry_id, title, pub_date, url):
    """Adds the new release entry to DynamoDB. This will serve
    as both a history of all the releases that were sent
    and is also checked before each message is sent to avoid
    sending duplicates.

    Keyword arguments:
    entry_id -- the ID of the entry in the news feed
    title -- the title of the news article
    pub_date -- the publish date of the news article in UTC
    url -- the URL for this announcement
    """
    ddb_client = boto3.client('dynamodb')
    slack_date = datetime.now(timezone.utc).isoformat(' ').split('.')[0]
    published_date = format_date(pub_date).isoformat(' ').split('+')[0]
    try:
        response = ddb_client.put_item(TableName=DDB_TABLE,
                                    Item={
                                        'id': {
                                            'S': entry_id
                                        },
                                        'title': {
                                            'S': title
                                        },
                                        'pub_date': {
                                            'S': published_date
                                        },
                                        'slack_date': {
                                            'S': slack_date
                                        },
                                        'url': {
                                            'S': url
                                        }
                                    })
        logger.info(f'Added {title} to DDB table')
    except ClientError as error:
        logger.error(f'Problem adding history to slack: {error}')

def make_slack_msg(entry):
    """Generates a JSON object that conforms to the Slack Bock Kit
    standard. See https://api.slack.com/reference/block-kit for
    details.

    Keyword arguments:
    entry -- A single item in the RSS feed that contains release info
    """
    description = BeautifulSoup(entry['description'], 'html.parser')
    message = dict(
        text=entry['title'],
        blocks=[
            dict(
                type='section',
                text=dict(
                    type='mrkdwn',
                    text=f':rocket: <{entry["link"]}|{entry["title"]}>'
                )
            ),
            dict(
                type='section',
                text=dict(
                        type='plain_text',
                        text=description.get_text()
                ),
                accessory=dict(
                    type='button',
                    text=dict(
                        type='plain_text',
                        text='Read More'
                    ),
                    style='primary',
                    url=entry['link'],
                    action_id='button-link'
                )
            ),
            dict(
                type='divider'
            )
        ]
    )
    return message

def get_webhook_urls():
    """Retrieves the Slack Webhook URLs that are stored in Secrets Manager.
    Uses the AWS Secrets Manager caching library to cache locally
    so each invocation doesn't need to perform a GetSecretValue call.
    """
    logger.info('Getting Slack webhook URL(s) from AWS Secrets Manager')
    try:
        # If not already in cache, keep urls in cache for 4 hours before re-calling
        secret_urls = parameters.get_secret(WEBHOOK_SECRET_NAME, max_age=14400)
        slack_urls = json.loads(secret_urls)
    except parameters.exceptions.GetParameterError as error:
        logger.error(f'Problem getting the Slack Webhook URLs: {error}')
        raise
    except json.JSONDecodeError as error:
        logger.error(f'Problem decoding JSON: {error}')
        raise
    else:
        return slack_urls['urls']

def format_date(d):
    return datetime.strptime(d, '%a, %d %b %Y %H:%M:%S %z')

@tracer.capture_lambda_handler
def main(event, context):
    """Iterates over each entry in the news feed, checks if the ID
    is already in the DynamoDB history table. If not, creates a slack message
    and posts it. Otherwise, the article is ignored and is assumed to
    have already been sent.
    """
    try:
        feed = feedparser.parse(WHATS_NEW_URL)
    except Exception as error:
        logger.error(f'Problem getting feed: {error}')
        raise
    else:
        urls = get_webhook_urls()
        http_connection = urllib3.PoolManager()
        logger.info('Parsing RSS feed')
        twelve_hours_ago = timedelta(hours=12)
        now = datetime.now(timezone.utc)
        # Only look at entries that were published 12 hours ago
        for entry in [x for x in feed['entries'] if (now - format_date(x['published'])) < twelve_hours_ago]:
            # check if entry has already been sent
            if has_been_slacked(entry['id']):
                logger.debug(f'Already sent message with ID {entry["id"]}')
                continue
            else:
                slack_msg = make_slack_msg(entry)
                post_slack(slack_msg, urls, http_connection)
                log_slack(entry['id'], entry['title'], 
                            entry['published'], entry['link'])
    logger.info('Done!')
    return
