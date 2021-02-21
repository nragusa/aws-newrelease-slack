
## AWS New Releases to Slack

Get the latest AWS service and feature announcements delivered directly into the Slack channel of your choice.

![Example Screenshot](docs/images/screenshot.png)

### Pre-Reqs
#### Slack App
You'll need to create a [Slack app](https://api.slack.com/start) in your workspace first. If you don't know how, ask your Slack administrator for help.

Once you have the app created, you'll need the [incoming webhook URL](https://api.slack.com/start/planning/communicating#communicating-with-users__incoming-webhooks). This is the endpoint used to push the messages into your Slack channel. Save this URL!

#### AWS CDK
This application was built with the [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html). You'll need to [install the AWS CDK Toolkit](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) before moving on.

### Installation

Now that you have a Slack app configured and the AWS CDK Toolkit installed, you'll need to deploy this appplication into your AWS account. Clone this project, `cd` into the project directory and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Rename the file `cdk.json.example` to `cdk.json`. Update the value of __slack_webhook_url__ to the URL specific to the Slack app you created earlier. 

Deploy the application and enjoy!

```bash
cdk deploy
```