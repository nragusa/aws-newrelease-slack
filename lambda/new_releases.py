"""Sends a Slack message of articles that were posted in the AWS
'What's New' news feed.

This lambda function gets the search results that are resturned when
accessing https://aws.amazon.com/new/. It uses an API endpoint that is
not officially published to get this data. Because of that, this function
will fall back to the RSS feed if the API search result fails.

It then iterates over each article and checks if it exists in a DynamoDB 
table. If the url is not found, it will send a message to Slack with 
the new release title, link, and description.

The function is intended to run every 5 minutes. Since the feed doesn't 
change that often, when the script determines the url is already
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

WHATS_NEW_RSS_FEED = os.environ['WHATS_NEW_RSS_FEED']
WHATS_NEW_SEARCH_API = os.environ['WHATS_NEW_SEARCH_API']
WEBHOOK_SECRET_NAME = os.environ['WEBHOOK_SECRET_NAME']
DDB_TABLE = os.environ['DDB_TABLE']


class NewRelease(object):
    """Parent class of the NewRelease object. There are 2 classes
    that are a subclass of this one - one for releases that are
    returned from the search API url, and one for releases that
    are returned from the RSS feed.
    """

    def __init__(self, url, title, published_date, body):
        self.url = url
        self.title = title
        self.published_date = published_date
        self.body = body

    def in_slack_format(self):
        """Generates a JSON object that conforms to the Slack Bock Kit
        standard. See https://api.slack.com/reference/block-kit for
        details.

        Keyword arguments:
        entry -- A single item in the RSS feed that contains release info
        """
        message = dict(
            text=self.title,
            blocks=[
                dict(
                    type='section',
                    text=dict(
                        type='mrkdwn',
                        text=f':rocket: <{self.url}|{self.title}>'
                    )
                ),
                dict(
                    type='section',
                    text=dict(
                        type='plain_text',
                        text=self.body
                    ),
                    accessory=dict(
                        type='button',
                        text=dict(
                            type='plain_text',
                            text='Read More'
                        ),
                        style='primary',
                        url=self.url,
                        action_id='button-link'
                    )
                ),
                dict(
                    type='divider'
                )
            ]
        )
        return message


class APINewRelease(NewRelease):
    """Subclass of NewRelease that creates an object returned
    from the search API
    """

    def __init__(self, release):
        self.url = f'https://aws.amazon.com{release["additionalFields"]["headlineUrl"]}'
        self.title = release['additionalFields']['headline'].strip()
        self.published_date = release['additionalFields']['postDateTime']
        self.body = BeautifulSoup(
            release['additionalFields']['postSummary'], 'html.parser').get_text()
        NewRelease.__init__(self, self.url, self.title,
                            self.published_date, self.body)

    def __str__(self):
        return self.title


class RSSNewRelease(NewRelease):
    """Subclass of NewRelease that creates an object returned
    from the RSS feed
    """

    def __init__(self, release):
        self.url = release['link']
        self.title = release['title']
        self.published_date = datetime.strptime(
            release['published'], '%a, %d %b %Y %H:%M:%S %z').isoformat().split('+')[0] + 'Z'
        self.body = BeautifulSoup(
            release['description'], 'html.parser').get_text()
        NewRelease.__init__(self, self.url, self.title,
                            self.published_date, self.body)

    def __str__(self):
        return self.title


def has_been_slacked(url):
    """Returns true if the post ID is found in DDB table"""
    logger.debug(f'Querying DDB for url = {url}')
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(DDB_TABLE)
    response = table.query(KeyConditionExpression=Key('url').eq(url))
    if response['Count'] != 0:
        return True
    else:
        return False


def post_slack(slack_msg, urls, connection):
    """Posts the message to Slack webhook endpoint"""
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


def log_slack(release):
    """Adds the new release entry to DynamoDB. This will serve
    as both a history of all the releases that were sent
    and is also checked before each message is sent to avoid
    sending duplicates.

    Keyword arguments:
    release -- An object that contains information about the release
    """
    ddb_client = boto3.client('dynamodb')
    slack_date = datetime.now(timezone.utc).isoformat(' ').split('.')[0]
    try:
        response = ddb_client.put_item(TableName=DDB_TABLE,
                                       Item={
                                           'url': {
                                               'S': release.url
                                           },
                                           'title': {
                                               'S': release.title
                                           },
                                           'pub_date': {
                                               'S': release.published_date
                                           },
                                           'slack_date': {
                                               'S': slack_date
                                           }
                                       })
        logger.info(f'Added {release} to DDB table')
    except ClientError as error:
        logger.error(f'Problem adding history to slack: {error}')


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


def format_date(date_string):
    return datetime.strptime(date_string, '%a, %d %b %Y %H:%M:%S %z')


@tracer.capture_lambda_handler
def main(event, context):
    """Iterates over each new release and checks if the URL is already
    in the DynamoDB history table. If not, creates a slack message
    and posts it. Otherwise, the release is ignored and is assumed to
    have already been sent.
    """
    http_connection = urllib3.PoolManager()
    try:
        # Gets the latest 25 releases from the search API
        logger.info('Getting releases from search API')
        http_response = http_connection.request('GET', WHATS_NEW_SEARCH_API)
        items = json.loads(http_response.data.decode('utf-8'))['items']
        releases = [APINewRelease(item['item']) for item in reversed(items)]
    except Exception as error:
        # Fall back to RSS feed if search API fails
        logger.warn(f'Problem getting releases from search API: {error}')
        logger.info('Falling back to RSS feed')
        try:
            items = feedparser.parse(WHATS_NEW_RSS_FEED)
            logger.info('Parsing RSS feed')
            twelve_hours_ago = timedelta(hours=12)
            now = datetime.now(timezone.utc)
            # Only look at entries that were published 12 hours ago
            releases = [RSSNewRelease(item) for item in items['entries'] if (
                now - format_date(item['published'])) < twelve_hours_ago]
        except Exception as error:
            logger.error(f'Problem getting RSS feed: {error}')
            raise

    """Iterate over the releases, check if each has been sent, and send 
    to Slack webhook URL if it's new.
    """
    logger.debug('Releases received', extra={
        'releases': [r for r in releases]})
    slack_webhook_urls = get_webhook_urls()
    logger.info('Checking each release')
    for release in releases:
        if has_been_slacked(release.url):
            logger.debug('Already sent link to slack',
                         extra={'title': release})
            continue
        else:
            logger.debug('Found release to send to slack')
            post_slack(
                release.in_slack_format(),
                slack_webhook_urls,
                http_connection
            )
            log_slack(release)

    logger.info('Done!')
    return
