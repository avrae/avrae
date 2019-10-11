import json
import logging
import os

import boto3
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


def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))

    logger.info(f"I can see {db.characters.estimated_document_count()} characters")
