import datetime
import json
import logging
import os

import boto3
import pymongo
from pymongo import MongoClient

MONGO_URL_SECRET_ARN = os.getenv('MONGO_URL_SECRET_ARN')
MONGO_DB = os.getenv('MONGO_DB_NAME', 'avrae')

# init logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_mongo_url():
    session = boto3.session.Session()
    secrets_client = session.client('secretsmanager')
    get_secret_value_response = secrets_client.get_secret_value(
        SecretId=MONGO_URL_SECRET_ARN
    )
    return get_secret_value_response['SecretString']


# init mongo
MONGO_URL = get_mongo_url()
client = MongoClient(MONGO_URL)
db = client[MONGO_DB]


# helpers
def get_statistic(key):
    try:
        value = int(
            db.random_stats.find_one({"key": key}).get("value", 0)
        )
    except AttributeError:
        value = 0
    return value


# calculators

# each of these return (total_today, total_life) [dict<int, int>, dict<int, int>]
def calculate_command_activity(last_to_date):
    commands_to_date = {}
    last_commands_to_date = last_to_date.get("command_activity", {})
    for doc in db.analytics_command_activity.find():
        commands_to_date[doc['name']] = doc['num_invocations']

    commands_today = {}
    for command, to_date in commands_to_date.items():
        commands_today[command] = to_date - last_commands_to_date.get(command, 0)

    return commands_today, commands_to_date


# each of these should return (total_today, total_life) [int, int]
def calculate_num_commands(last_to_date):
    num_commands_now = get_statistic("commands_used_life")
    delta = num_commands_now - last_to_date.get("num_commands", 0)
    return delta, num_commands_now


def calculate_num_characters(last_to_date):
    num_characters_now = db.characters.estimated_document_count()
    delta = num_characters_now - last_to_date.get("num_characters", 0)
    return delta, num_characters_now


# returns {day: int, week: int, month: int}
def calculate_num_active_users():
    now = datetime.datetime.now()
    out = {
        "day": db.analytics_user_activity.count_documents({"last_command_time":
                                                               {"$gt": now - datetime.timedelta(days=1)}}),
        "week": db.analytics_user_activity.count_documents({"last_command_time":
                                                                {"$gt": now - datetime.timedelta(days=7)}}),
        "month": db.analytics_user_activity.count_documents({"last_command_time":
                                                                 {"$gt": now - datetime.timedelta(days=30)}})
    }
    return out


def calculate_num_active_guilds():
    now = datetime.datetime.now()
    out = {
        "day": db.analytics_guild_activity.count_documents({"last_command_time":
                                                                {"$gt": now - datetime.timedelta(days=1)}}),
        "week": db.analytics_guild_activity.count_documents({"last_command_time":
                                                                 {"$gt": now - datetime.timedelta(days=7)}}),
        "month": db.analytics_guild_activity.count_documents({"last_command_time":
                                                                  {"$gt": now - datetime.timedelta(days=30)}})
    }
    return out


# main
def calculate_daily():
    try:
        last = next(db.analytics_daily.find().sort("timestamp", pymongo.DESCENDING).limit(1))
    except StopIteration:
        last = {}
    last_to_date = last.get("to_date", {})

    # setup
    out = {"timestamp": datetime.datetime.now()}
    to_date = dict()

    # --- calculations ---

    # -- deltas --
    # most popular commands today
    # fixme: how does this work in a columnal data store?
    # out['command_activity'], to_date['command_activity'] = calculate_command_activity(last_to_date)

    # commands called today
    out['num_commands'], to_date['num_commands'] = calculate_num_commands(last_to_date)
    # characters imported today
    out['num_characters'], to_date['num_characters'] = calculate_num_characters(last_to_date)

    # -- timeframed --
    # users active today/this week/this month (have called a command in the last 24h/1w/1mo)
    out['num_active_users'] = calculate_num_active_users()
    # guilds active today/this week/this month (have called a command in the last 24h/1w/1mo)
    out['num_active_guilds'] = calculate_num_active_guilds()

    # to date, for delta calcs
    out['to_date'] = to_date

    return out


def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))

    db.analytics_daily.insert_one(calculate_daily())

    logger.info("Done!")
