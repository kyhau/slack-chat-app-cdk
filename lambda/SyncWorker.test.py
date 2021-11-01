"""
Unit tests for SyncWorker.py
"""
import os
import unittest
from unittest.mock import patch

os.environ["OAuthDynamoDBTable"] = "DummyDDB"

func = __import__("SyncWorker")


def mock_event(text_value=""):
    return {
        "app_id": "APIID123456",
        "channel_id": "C1111111111",
        "team_id": "T1111111111",
        "text": text_value,
        "ts": "1634873264.005100",
        "user_id": "test_user_id",
    }


class TestFunction(unittest.TestCase):
    def test_lambda_handler(self):
        with patch("SyncWorker.oauth_table.get_item") as mock_ddb_get_item, \
             patch("SyncWorker.call_slack_chat_post") as mock_post:

            mock_ddb_get_item.return_value = {"Item": {"access_token": "dummy-bot-token"}}

            ret = func.lambda_handler(mock_event(text_value="sync"), None)
            mock_post.assert_called_once_with(
                "C1111111111",
                "1634873264.005100",
                "dummy-bot-token",
                "SyncWorker: <@test_user_id> said `sync`"
            )
            self.assertEqual(ret, {"statusCode": 200})


if __name__ == "__main__":
    unittest.main()
