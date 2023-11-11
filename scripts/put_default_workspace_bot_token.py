"""
Insert the bot token details of the Workspace that owns the Slack Bot to the DynamoDB table.
"""
import json
import os
from datetime import datetime

import boto3

# TODO
BOT_TOKEN = os.environ["BOT_TOKEN"]
ENV_STAGE = os.environ.get("ENV_STAGE", "dev")
TARGET_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

with open(f"settings_{ENV_STAGE}.json") as json_file:
    stage_settings = json.load(json_file)

APP_ID = stage_settings["slack_app_id"]
TEAM_ID = stage_settings["slack_app_owner_team_id"]
DDB_TABLE_NAME = f'{stage_settings["name"]}-SlackChatApp-OAuth'

DEFAULT_ITEM = {
    "app_id": APP_ID,
    "team_id": TEAM_ID,
    "access_token": BOT_TOKEN,
}

table = boto3.resource("dynamodb", region_name=TARGET_REGION).Table(DDB_TABLE_NAME)


def put_data_to_dynamodb():
    try:
        data = {"request_utc": datetime.utcnow().isoformat()}  # Add current timestamp
        for k, v in DEFAULT_ITEM.items():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    data[f"{k}_{k2}"] = v2
            elif k not in ["ok"]:
                data[k] = v

        table.put_item(TableName=DDB_TABLE_NAME, Item=data)
    except Exception as e:
        print(e)


def get_item_from_dynamodb():
    return table.get_item(
        Key={
            "app_id": APP_ID,
            "team_id": TEAM_ID,
        }
    )["Item"]


def main():
    put_data_to_dynamodb()
    print(get_item_from_dynamodb())


if __name__ == "__main__":
    main()
