import os
import sys

# This method will load the variables from .env into the environment for running in local
# from dotenv import load_dotenv
# load_dotenv()


# ==== bot config constants / env vars ====
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
TESTING = bool(os.environ.get("TESTING")) or "test" in sys.argv
ENVIRONMENT = os.getenv("ENVIRONMENT", "production" if not TESTING else "development")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA")
NUM_CLUSTERS = int(os.getenv("NUM_CLUSTERS")) if "NUM_CLUSTERS" in os.environ else None
NUM_SHARDS = int(os.getenv("NUM_SHARDS")) if "NUM_SHARDS" in os.environ else None
RELOAD_INTERVAL = os.getenv("RELOAD_INTERVAL", "0")  # compendium static data reload interval
ECS_METADATA_ENDPT = os.getenv("ECS_CONTAINER_METADATA_URI")  # set by ECS
MONSTER_TOKEN_ENDPOINT = os.getenv("MONSTER_TOKEN_ENDPOINT")  # S3: monster tokens
# secret for the draconic signature() function
DRACONIC_SIGNATURE_SECRET = os.getenv("DRACONIC_SIGNATURE_SECRET", "secret").encode()

# ---- mongo/redis ----
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "avrae")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_DB_NUM = int(os.getenv("REDIS_DB_NUM", 0))

# ---- user ----
DEFAULT_PREFIX = os.getenv("DEFAULT_PREFIX", "!")

# ---- monitoring ----
SENTRY_DSN = os.getenv("SENTRY_DSN")
DD_SERVICE = os.getenv("DD_SERVICE")

# ---- character sheets ---
NO_DICECLOUD = os.environ.get("NO_DICECLOUD", "DICECLOUD_USER" not in os.environ)
DICECLOUD_USER = os.getenv("DICECLOUD_USER")
DICECLOUD_PASS = os.getenv("DICECLOUD_PASS", "").encode()
DICECLOUD_API_KEY = os.getenv("DICECLOUD_TOKEN")

DCV2_NO_AUTH = os.getenv("DCV2_NO_AUTH", "DICECLOUDV2_USER" not in os.environ)
NO_DICECLOUDV2 = os.environ.get("NO_DICECLOUDV2")
DICECLOUDV2_USER = os.getenv("DICECLOUDV2_USER")
DICECLOUDV2_PASS = os.getenv("DICECLOUDV2_PASS", "")

GOOGLE_SERVICE_ACCOUNT = os.getenv("GOOGLE_SERVICE_ACCOUNT")  # optional - if not supplied, uses avrae-google.json

# ---- ddb entitlements ----
# if environment is development, DDB auth is skipped unless auth service url is not null
DDB_AUTH_SECRET = os.getenv("DDB_AUTH_SECRET")
DDB_WATERDEEP_SECRET = os.getenv("DDB_AUTH_WATERDEEP_SECRET")
DDB_AUTH_AUDIENCE = os.getenv("DDB_AUTH_AUDIENCE", "avrae.io")
DDB_AUTH_ISSUER = os.getenv("DDB_AUTH_ISSUER", "dndbeyond.com")
DDB_AUTH_EXPIRY_SECONDS = int(os.getenv("DDB_AUTH_EXPIRY_SECONDS", 5 * 60))
DDB_AUTH_SERVICE_URL = os.getenv("DDB_AUTH_SERVICE_URL")
DYNAMO_REGION = os.getenv("DYNAMO_REGION", "us-east-1")  # actually AWS_REGION for all resources :p
DYNAMO_ENTITLEMENTS_TABLE = os.getenv("DYNAMO_ENTITLEMENTS_TABLE", "entitlements-live")
NLP_KINESIS_DELIVERY_STREAM = os.getenv("NLP_KINESIS_DELIVERY_STREAM")
# env: AWS_ACCESS_KEY_ID
# env: AWS_SECRET_ACCESS_KEY

# ---- ddb other ----
# optional - if not set, DDB import disabled locally
DDB_CHAR_COMPUTATION_ENDPT = os.getenv("CHARACTER_COMPUTATION_ENDPOINT")
# used to override waterdeep URL in dev/stg
DDB_WATERDEEP_URL = os.getenv("DDB_WATERDEEP_URL", "https://www.dndbeyond.com")
# game log base endpoint
DDB_GAMELOG_ENDPOINT = os.getenv("DDB_GAMELOG_ENDPOINT", "https://game-log-rest-live.dndbeyond.com/v1")
DDB_CHARACTER_SERVICE_URL = os.getenv(
    "DDB_CHARACTER_SERVICE_URL", "https://character-service.dndbeyond.com/character/v5"
)
DDB_SCDS_SERVICE_URL = os.getenv("DDB_SCDS_SERVICE_URL", "https://character-service-scds.dndbeyond.com/v2")
DDB_MEDIA_S3_BUCKET_DOMAIN = os.getenv("DDB_MEDIA_S3_BUCKET_DOMAIN", "www.dndbeyond.com")  # used for !token

# ---- launchdarkly ----
LAUNCHDARKLY_SDK_KEY = os.getenv("LAUNCHDARKLY_SDK_KEY")

# ---- discord bot list ----
DBL_TOKEN = os.getenv("DBL_TOKEN")  # optional
