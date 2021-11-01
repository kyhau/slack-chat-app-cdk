0.1.0 - 2021-11-01
==================
Initial version of Slack Chat App.

The Slack App can handle requests triggered from a `app_mentions:read` event, which will take longer than [3 seconds](https://api.slack.com/events-api) to process, and posts the details back to the user using `chat:write` API.

Two components (APIs) created:
1. A Slack Chat App/Bot with AWS API Gateway, Lambda Functions, and DynamoDB table, being deployed with [CDK v2](https://docs.aws.amazon.com/cdk/latest/guide/work-with-cdk-v2.html) and tested wth SAM CLI ([sam-beta-cdk](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-cdk-getting-started.html)).

2. An OAuth 2.0 authorization flow service for sharing the Slack App with other Workspaces without registering in the public Slack App Directory. For details see "Apps distributed to multiple workspaces" in [Distributing Slack apps](https://api.slack.com/start/distributing#multi_workspace_apps). This stack includes an AWS API Gateway, and a Lambda Function with AWS WAF (optional).
