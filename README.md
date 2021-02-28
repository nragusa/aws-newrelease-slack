
## AWS New Releases to Slack

Get the latest AWS service and feature announcements delivered directly into the Slack channel of your choice.

![Example Screenshot](docs/images/screenshot.png)

All of this is powered by a simple Lambda function and a DynamoDB table to maintain a history of what was already sent:

![Architecture](https://lucid.app/publicSegments/view/c662d7e1-955e-43bf-9f35-ea4908a066c3/image.png)

### Pre-Reqs
#### Slack App
You'll need to create a [Slack app](https://api.slack.com/start) in your workspace first. If you don't know how, ask your Slack administrator for help.

Once you have the app created, you'll need to [activate incoming webhooks](https://slack.com/help/articles/115005265063-Incoming-webhooks-for-Slack). Once activated, grab the [incoming webhook URL](https://api.slack.com/start/planning/communicating#communicating-with-users__incoming-webhooks) and save it for later.

#### Add Slack WebhookURLs to Secrets Manager
Since these URL(s) contain sensitive information, you should store them in [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/) with encryption. 

First, come up with a sensible name for this secret within AWS Secrets Manager. As a best practice, use a naming scheme that uses a hierarchy so you can easily restrict access by their ARNs. Once you have a name, export it into your environment as we'll reference it a few times:

```bash
export SLACK_WEBHOOK_SECRET_NAME=your/path/to/slack/webhooks
```

Now run the following to create and store the secret:

```bash
# Write a file locally with the URLs in this format
cat > secret.json
{
    "urls": [
        "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
    ]
}
# Store this in AWS Secrets Manager
aws secretsmanager create-secret \
    --name ${SLACK_WEBHOOK_SECRET_NAME} \
    --description "The Slack Webhook URL(s) for the AWS New Releases Slack app" \
    --secret-string file://secret.json
    --tags Key=Project,Value="AWS New Releases Chatbot"
# Overwrite + delete the file
shred -u secret.json
# OS X users can use 'rm -P secret.json'
```

This will use the default KMS key for encryption. If you wish to use your own key, you'll need to make sure the Lambda execution role has access to use this key as well.

#### AWS CDK
This application was built with the [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html). You'll need to [install the AWS CDK Toolkit](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) before moving on.

### Installation

Now that you have a Slack app configured and the AWS CDK Toolkit installed, you'll need to deploy this application into your AWS account. Clone this project, `cd` into the project directory and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Deploy the application and enjoy!

```bash
cdk deploy aws-newrelease-slack-dev -c slack_webhook_secret_name=${SLACK_WEBHOOK_SECRET_NAME}
```

If you'd like to have a production environment, create a production version of the Slack webhooks in AWS Secrets Manager, then run:
```bash
cdk deploy aws-newrelease-slack-prod -c slack_webhook_secret_name=your/prod/webhooks-name
```