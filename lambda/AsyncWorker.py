"""
For processing requests that will take longer than 3 seconds to process.
"""
import json
import logging
import os
from urllib.parse import urlencode

import boto3
import urllib3

logging.getLogger().setLevel(logging.INFO)

SLACK_API_CHAT_POST_URL = "https://slack.com/api/chat.postMessage"
OAUTH_DDB_TABLE_NAME = os.environ.get("OAuthDynamoDBTable")

oauth_table = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")).Table(OAUTH_DDB_TABLE_NAME)
http = urllib3.PoolManager()


def get_bot_token(app_id, team_id):
    try:
        return oauth_table.get_item(Key={"app_id": app_id, "team_id": team_id})["Item"]["access_token"]
    except Exception as e:
        logging.error(e)


def call_slack_chat_post(channel_id, thread_ts, bot_token, response_text):
    data = urlencode(
        (
            ("token", bot_token),
            ("channel", channel_id),
            ("thread_ts", thread_ts),
            ("text", response_text)
        )
    ).encode("ascii")
    resp = http.request("POST", SLACK_API_CHAT_POST_URL, body=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    logging.info(resp.read())


def lambda_handler(event, context):
    logging.info(json.dumps(event, indent=2))

    app_id = event["app_id"]
    channel_id = event["channel_id"]
    team_id = event["team_id"]
    text_msg = event.get("text")
    thread_ts = event["ts"]
    user_id = event["user_id"]

    message = f"AsyncWorker: <@{user_id}> said `{text_msg}`"
    logging.info(message)
    call_slack_chat_post(channel_id, thread_ts, get_bot_token(app_id, team_id), message)

    return {
        "statusCode": 200,
    }
