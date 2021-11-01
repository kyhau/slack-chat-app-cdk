"""
Unit tests for handling Slack Chat in ImmediateResponse.py
"""
import json
import os
import unittest
from unittest.mock import patch

os.environ["SlackAppId"] = "APIID123456"
os.environ["SlackChannelIds"] = "C1111111111,C2222222222"
os.environ["SlackTeamIds"] = "T1111111111,T2222222222"
os.environ["SlackVerificationTokenParameterKey"] = "/apps/slack_app/dummy/token"
os.environ["AsyncWorkerLambdaFunctionName"] = "Dummy-AsyncWorker"
os.environ["SyncWorkerLambdaFunctionName"] = "Dummy-SyncWorker"
os.environ["OAuthDynamoDBTable"] = "DummyDDB"

func = __import__("ImmediateResponse")


def mock_event(custom_data={}, channel="C1111111111"):
    data = {
        "token": "dummy-token",
        "team_id": "T1111111111",
        "api_app_id": "APIID123456",
        "event": {
            "client_msg_id": "b03d5869-53c0-4287-a711-0e7d34a8c001",
            "type": "app_mention",
            "text": "<@UB111111111>",
            "user": "U2222222222",
            "ts": "1634873264.005100",
            "team": "T1111111111",
            "blocks": [
                {
                    "type": "rich_text",
                    "block_id": "Cj64",
                    "elements": [
                        {
                            "type": "rich_text_section",
                            "elements": [
                                {
                                    "type": "user",
                                    "user_id": "UB111111111"
                                },
                                {
                                    "type": "text",
                                    "text": " what\nline 2\nline 3"
                                }
                            ]
                        }
                    ]
                }
            ],
            "channel": channel,
            "event_ts": "1634873264.005100"
        },
        "type": "event_callback",
        "event_id": "Ev02JGDEJTCN",
        "event_time": 1634873264,
        "authed_users": [
            "UB111111111"
        ],
        "authorizations": [
            {
                "enterprise_id": "null",
                "team_id": "T1111111111",
                "user_id": "UB111111111",
                "is_bot": "true",
                "is_enterprise_install": "false"
            }
        ],
        "is_ext_shared_channel": "false",
        "event_context": "xxx"
    }
    data.update(custom_data)

    return {
        "body": json.dumps(data)
    }


def payload_in_bytes():
    payload_json = {
        "app_id": "APIID123456",
        "channel_id": "C1111111111",
        "team_id": "T1111111111",
        "text": " what\nline 2\nline 3",
        "ts": "1634873264.005100",
        "user_id": "U2222222222",
    }
    payload_str = json.dumps(payload_json)
    return bytes(payload_str, encoding="utf8")


MOCK_LAMBDA_INVOKE_RESPONSE = {
    "ResponseMetadata": {
        "HTTPStatusCode": 200,
    }
}


class TestFunction(unittest.TestCase):

    def test_lambda_handler_all_good(self):
        with patch("ImmediateResponse.ssm_client.get_parameter", return_value={"Parameter": {"Value": "dummy-token"}}), \
             patch("ImmediateResponse.oauth_table.get_item") as mock_ddb_get_item, \
             patch("ImmediateResponse.lambda_client.invoke") as mock_lambda_invoke:

            mock_ddb_get_item.return_value = {"Item": {"access_token": "dummy-bot-token"}}
            mock_lambda_invoke.return_value = MOCK_LAMBDA_INVOKE_RESPONSE

            ret = func.lambda_handler(mock_event(), None)

            mock_ddb_get_item.assert_called_once_with(Key={"app_id": "APIID123456", "team_id": "T1111111111"})

            mock_lambda_invoke.assert_called_once_with(
                FunctionName="Dummy-AsyncWorker",
                InvocationType="Event",
                Payload=payload_in_bytes(),
            )

            self.assertDictEqual(ret, {"statusCode": 200})

    def test_lambda_handler_failed_invalid_token(self):
        with patch("ImmediateResponse.ssm_client.get_parameter", return_value={"Parameter": {"Value": "dummy-token"}}), \
             patch("ImmediateResponse.oauth_table.get_item") as mock_ddb_get_item, \
             patch("ImmediateResponse.call_slack_chat_post") as mock_chat_post:

            mock_ddb_get_item.return_value = {"Item": {"access_token": "dummy-bot-token"}}

            ret = func.lambda_handler(mock_event({"token": "invalid-token"}), None)

            mock_ddb_get_item.assert_called_once_with(Key={"app_id": "APIID123456", "team_id": "T1111111111"})

            mock_chat_post.assert_called_once_with(
                "C1111111111",
                "1634873264.005100",
                "dummy-bot-token",
                "Sorry <@U2222222222>, an authentication error occurred. Please contact your admin."
            )

            self.assertDictEqual(ret, {"statusCode": 200})

    def test_lambda_handler_failed_no_bot_token(self):
        with patch("ImmediateResponse.ssm_client.get_parameter", return_value={"Parameter": {"Value": "dummy-token"}}), \
             patch("ImmediateResponse.oauth_table.get_item") as mock_ddb_get_item, \
             patch("ImmediateResponse.call_slack_chat_post") as mock_chat_post:

            # No item found for that team_id
            mock_ddb_get_item.return_value = {"Item": None}

            ret = func.lambda_handler(mock_event(), None)

            mock_ddb_get_item.assert_called_once_with(Key={"app_id": "APIID123456", "team_id": "T1111111111"})

            mock_chat_post.assert_not_called()

            self.assertDictEqual(ret, {"statusCode": 200})

    def test_lambda_handler_failed_invalid_app_id(self):
        with patch("ImmediateResponse.ssm_client.get_parameter", return_value={"Parameter": {"Value": "dummy-token"}}), \
             patch("ImmediateResponse.oauth_table.get_item") as mock_ddb_get_item, \
             patch("ImmediateResponse.call_slack_chat_post") as mock_chat_post:

            mock_ddb_get_item.return_value = {"Item": {"access_token": "dummy-bot-token"}}

            ret = func.lambda_handler(mock_event({"api_app_id": "invalid-app-id"}), None)

            mock_ddb_get_item.assert_called_once_with(Key={"app_id": "invalid-app-id", "team_id": "T1111111111"})

            mock_chat_post.assert_called_once_with(
                "C1111111111",
                "1634873264.005100",
                "dummy-bot-token",
                "Sorry <@U2222222222>, this app does not support this app ID invalid-app-id."
            )

            self.assertDictEqual(ret, {"statusCode": 200})

    def test_lambda_handler_failed_invalid_team_id(self):
        with patch("ImmediateResponse.ssm_client.get_parameter", return_value={"Parameter": {"Value": "dummy-token"}}), \
             patch("ImmediateResponse.oauth_table.get_item") as mock_ddb_get_item, \
             patch("ImmediateResponse.call_slack_chat_post") as mock_chat_post:

            mock_ddb_get_item.return_value = {"Item": {"access_token": "dummy-bot-token"}}

            ret = func.lambda_handler(mock_event({"team_id": "invalid-team-id"}), None)

            mock_ddb_get_item.assert_called_once_with(Key={"app_id": "APIID123456", "team_id": "invalid-team-id"})

            mock_chat_post.assert_called_once_with(
                "C1111111111",
                "1634873264.005100",
                "dummy-bot-token",
                "Sorry <@U2222222222>, this app does not support this team ID invalid-team-id."
            )

            self.assertDictEqual(ret, {"statusCode": 200})

    def test_lambda_handler_failed_invalid_channel_id(self):
        with patch("ImmediateResponse.ssm_client.get_parameter", return_value={"Parameter": {"Value": "dummy-token"}}), \
             patch("ImmediateResponse.oauth_table.get_item") as mock_ddb_get_item, \
             patch("ImmediateResponse.call_slack_chat_post") as mock_chat_post:

            mock_ddb_get_item.return_value = {"Item": {"access_token": "dummy-bot-token"}}

            ret = func.lambda_handler(mock_event(channel="invalid-channel-id"), None)

            mock_ddb_get_item.assert_called_once_with(Key={"app_id": "APIID123456", "team_id": "T1111111111"})

            mock_chat_post.assert_called_once_with(
                "invalid-channel-id",
                "1634873264.005100",
                "dummy-bot-token",
                "Sorry <@U2222222222>, this app does not support this channel ID invalid-channel-id."
            )

            self.assertDictEqual(ret, {"statusCode": 200})


if __name__ == "__main__":
    unittest.main()
