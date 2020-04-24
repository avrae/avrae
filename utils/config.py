import os
import sys

import credentials

# ==== bot config constants / env vars ====
TESTING = os.environ.get("TESTING") or 'test' in sys.argv
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production' if not TESTING else 'development')
ALPHA_TOKEN = os.environ.get("ALPHA_TOKEN")  # optional - if not supplied, will use credentials file
GIT_COMMIT_SHA = os.getenv('GIT_COMMIT_SHA')
NUM_CLUSTERS = int(os.getenv('NUM_CLUSTERS')) if 'NUM_CLUSTERS' in os.environ else None
NUM_SHARDS = int(os.getenv('NUM_SHARDS')) if 'NUM_SHARDS' in os.environ else None
RELOAD_INTERVAL = os.getenv('RELOAD_INTERVAL', '0')  # compendium static data reload interval
ECS_METADATA_ENDPT = os.getenv('ECS_CONTAINER_METADATA_URI')  # set by ECS

# ---- mongo/redis ----
MONGO_URL = os.getenv('MONGO_URL', "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'avrae')
REDIS_URL = os.getenv('REDIS_URL', '127.0.0.1')
REDIS_DB_NUM = int(os.getenv('REDIS_DB_NUM', 0))

# ---- user ----
DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX', '!')

# ---- monitoring ----
SENTRY_DSN = os.getenv('SENTRY_DSN') or None
# NEW_RELIC_LICENSE_KEY = os.getenv('NEW_RELIC_LICENSE_KEY')  # commented - set in newrelic.py because of import order

# ---- 3pp auth ----
NO_DICECLOUD = os.environ.get("NO_DICECLOUD", False)
DICECLOUD_USER = os.getenv('DICECLOUD_USER', 'avrae') if not TESTING else credentials.test_dicecloud_user
DICECLOUD_PASS = credentials.dicecloud_pass.encode() if not TESTING else credentials.test_dicecloud_pass.encode()
DICECLOUD_API_KEY = credentials.dicecloud_token if not TESTING else credentials.test_dicecloud_token
GOOGLE_SERVICE_ACCOUNT = os.getenv('GOOGLE_SERVICE_ACCOUNT')  # optional - if not supplied, uses avrae-google.json

# ---- ddb auth ----
# if environment is development, DDB auth is skipped unless auth service url is not null
DDB_AUTH_SECRET = os.getenv('DDB_AUTH_SECRET')
DDB_AUTH_AUDIENCE = os.getenv('DDB_AUTH_AUDIENCE', 'avrae.io')
DDB_AUTH_ISSUER = os.getenv('DDB_AUTH_ISSUER', 'dndbeyond.com')
DDB_AUTH_EXPIRY_SECONDS = int(os.getenv('DDB_AUTH_EXPIRY_SECONDS', 5 * 60))
DDB_AUTH_SERVICE_URL = os.getenv('DDB_AUTH_SERVICE_URL')
DYNAMO_REGION = os.getenv('DYNAMO_REGION', 'us-east-1')
DYNAMO_USER_TABLE = os.getenv('DYNAMO_USER_TABLE')
DYNAMO_ENTITY_TABLE = os.getenv('DYNAMO_ENTITY_TABLE')
# env: AWS_ACCESS_KEY_ID
# env: AWS_SECRET_ACCESS_KEY

# ---- launchdarkly ----
LAUNCHDARKLY_SDK_KEY = os.getenv('LAUNCHDARKLY_SDK_KEY')