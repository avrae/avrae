import os
import sys

# ==== bot config constants / env vars ====
TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
TESTING = os.environ.get("TESTING") or 'test' in sys.argv
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production' if not TESTING else 'development')
GIT_COMMIT_SHA = os.getenv('GIT_COMMIT_SHA')
NUM_CLUSTERS = int(os.getenv('NUM_CLUSTERS')) if 'NUM_CLUSTERS' in os.environ else None
NUM_SHARDS = int(os.getenv('NUM_SHARDS')) if 'NUM_SHARDS' in os.environ else None
RELOAD_INTERVAL = os.getenv('RELOAD_INTERVAL', '0')  # compendium static data reload interval
ECS_METADATA_ENDPT = os.getenv('ECS_CONTAINER_METADATA_URI')  # set by ECS
OWNER_ID = int(os.getenv('DISCORD_OWNER_USER_ID', 0))
MONSTER_TOKEN_ENDPOINT = os.getenv('MONSTER_TOKEN_ENDPOINT')  # S3: monster tokens

# ---- mongo/redis ----
MONGO_URL = os.getenv('MONGO_URL', "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'avrae')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
REDIS_DB_NUM = int(os.getenv('REDIS_DB_NUM', 0))

# ---- user ----
DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX', '!')

# ---- monitoring ----
SENTRY_DSN = os.getenv('SENTRY_DSN') or None
# NEW_RELIC_LICENSE_KEY = os.getenv('NEW_RELIC_LICENSE_KEY')  # commented - set in newrelic.py because of import order

# ---- character sheets ---
NO_DICECLOUD = os.environ.get('NO_DICECLOUD', 'DICECLOUD_USER' not in os.environ)
DICECLOUD_USER = os.getenv('DICECLOUD_USER')
DICECLOUD_PASS = os.getenv('DICECLOUD_PASS', '').encode()
DICECLOUD_API_KEY = os.getenv('DICECLOUD_TOKEN')

GOOGLE_SERVICE_ACCOUNT = os.getenv('GOOGLE_SERVICE_ACCOUNT')  # optional - if not supplied, uses avrae-google.json

DDB_CHAR_COMPUTATION_ENDPT = os.getenv('CHARACTER_COMPUTATION_ENDPOINT')  # optional - if not set, DDB import disabled locally

# ---- ddb auth ----
# if environment is development, DDB auth is skipped unless auth service url is not null
DDB_AUTH_SECRET = os.getenv('DDB_AUTH_SECRET')
DDB_WATERDEEP_SECRET = os.getenv('DDB_AUTH_WATERDEEP_SECRET')
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

# ---- discord bot list ----
DBL_TOKEN = os.getenv('DBL_TOKEN')  # optional
