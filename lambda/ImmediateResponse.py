"""
ImmediateResponse aims to do
- authentication and authorization,
- invoke AsyncWorker or SyncWorker
- return an immedate response to caller within 3 seconds
"""
import json
import logging
import os
from urllib.parse import urlencode

import boto3
import urllib3

logging.getLogger().setLevel(logging.INFO)

SLACK_API_CHAT_POST_URL = "https://slack.com/api/chat.postMessage"
SLACK_APP_ID = os.environ.get("SlackAppId")
SLACK_CHANNEL_IDS = list(map(str.strip, os.environ.get("SlackChannelIds", "").split(",")))
SLACK_TEAM_IDS = list(map(str.strip, os.environ.get("SlackTeamIds", "").split(",")))
SLACK_VERIFICATION_TOKEN_SSM_PARAMETER_KEY = os.environ.get("SlackVerificationTokenParameterKey")

CHILD_ASYNC_FUNCTION_NAME = os.environ.get("AsyncWorkerLambdaFunctionName")
CHILD_SYNC_FUNCTION_NAME = os.environ.get("SyncWorkerLambdaFunctionName")
OAUTH_DDB_TABLE_NAME = os.environ.get("OAuthDynamoDBTable")

IS_AWS_SAM_LOCAL = os.environ.get("AWS_SAM_LOCAL") == "true"
TARGET_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

lambda_client = boto3.client("lambda", region_name=TARGET_REGION)
oauth_table = boto3.resource("dynamodb", region_name=TARGET_REGION).Table(OAUTH_DDB_TABLE_NAME)
ssm_client = boto3.client("ssm", region_name=TARGET_REGION)
http = urllib3.PoolManager()


def authenticate(token):
    """Verify the token passed in"""
    if IS_AWS_SAM_LOCAL is True:
        return True

    try:
        expected_token = ssm_client.get_parameter(
            Name=SLACK_VERIFICATION_TOKEN_SSM_PARAMETER_KEY, WithDecryption=True
        )["Parameter"]["Value"]
    except Exception as e:
        logging.error(f"Unable to retrieve data from parameter store: {e}")
        return False

    if token != expected_token:
        logging.error(f"Request token ({token}) does not match expected")
        return False

    return True


def authorize(app_id, channel_id, team_id):
    """Just double check if this app is invoked from the expected app/channel/team"""

    if app_id != SLACK_APP_ID:
        return f"app ID {app_id}"

    if team_id not in SLACK_TEAM_IDS:
        return f"team ID {team_id}"

    if channel_id not in SLACK_CHANNEL_IDS:
        return f"channel ID {channel_id}"


def invoke_lambda(function_namme, payload_json, is_async):
    payload_str = json.dumps(payload_json)
    payload_bytes_arr = bytes(payload_str, encoding="utf8")
    return lambda_client.invoke(
        FunctionName=function_namme,
        InvocationType="Event" if is_async else "RequestResponse",
        Payload=payload_bytes_arr,
    )


def get_bot_token(app_id, team_id):
    try:
        return oauth_table.get_item(Key={"app_id": app_id, "team_id": team_id})["Item"][
            "access_token"
        ]
    except Exception as e:
        logging.error(e)


def call_slack_chat_post(channel_id, thread_ts, bot_token, response_text):
    logging.info("Started call_slack_chat_post")

    if IS_AWS_SAM_LOCAL is True:
        return

    data = urlencode(
        (
            ("token", bot_token),
            ("channel", channel_id),
            ("thread_ts", thread_ts),
            ("text", response_text),
        )
    ).encode("ascii")
    resp = http.request(
        "POST",
        SLACK_API_CHAT_POST_URL,
        body=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    logging.info(resp.read())


def create_immediate_response(body):
    resp = {"statusCode": 200}
    if body:
        resp["body"] = body

    logging.info(f"Sending immediate response: {resp}")
    return resp


def app_mention_handler(slack_msg):
    """app_mentions:read handler"""
    try:
        token = slack_msg["token"]
        team_id = slack_msg["team_id"]
        app_id = slack_msg["api_app_id"]
        channel_id = slack_msg["event"]["channel"]
        user_id = slack_msg["event"]["user"]
        thread_ts = slack_msg["event"]["ts"]

        bot_token = get_bot_token(app_id, team_id)

        if authenticate(token) is False:
            call_slack_chat_post(
                channel_id,
                thread_ts,
                bot_token,
                f"Sorry <@{user_id}>, an authentication error occurred. Please contact your admin.",
            )
            return False

        result = authorize(app_id, channel_id, team_id)
        if result is not None:
            call_slack_chat_post(
                channel_id,
                thread_ts,
                bot_token,
                f"Sorry <@{user_id}>, this app does not support this {result}.",
            )
            return False

        try:
            text_msg = slack_msg["event"]["blocks"][0]["elements"][0]["elements"][1]["text"]
        except Exception:
            text_msg = None

        logging.info(
            f"{user_id} invoked {app_id} in {channel_id} with the following text: {text_msg}"
        )

        message = None

        if text_msg:
            payload = {
                "app_id": app_id,
                "channel_id": channel_id,
                "team_id": team_id,
                "text": text_msg,
                "ts": thread_ts,
                "user_id": user_id,
            }

            resp = invoke_lambda(CHILD_ASYNC_FUNCTION_NAME, payload, is_async=True)
            if resp["ResponseMetadata"]["HTTPStatusCode"] not in [200, 201, 202]:
                logging.error(resp)
                message = (
                    f"<@{user_id}>, your request ({text_msg}) cannot be"
                    " processed at the moment. Please try again later."
                )

        else:
            message = f"Hello <@{user_id}>!"

        if message:
            call_slack_chat_post(channel_id, thread_ts, bot_token, message)

    except Exception as e:
        logging.error(e)
        return False
    return True


def lambda_handler(event, context):
    event_body = event.get("body")
    logging.info(f"Received event[body]: {event_body}")

    slack_msg = json.loads(event_body)

    resp_body = None

    if slack_msg.get("challenge"):
        # Only received the first time when adding/updating Request URL of Event Subscriptions
        resp_body = slack_msg.get("challenge")

    else:
        app_mention_handler(slack_msg)

    return create_immediate_response(resp_body)
