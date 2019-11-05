import os
import sys

import credentials

# ==== bot config constants / env vars ====
TESTING = os.environ.get("TESTING") or 'test' in sys.argv
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production' if not TESTING else 'development')
ALPHA_TOKEN = os.environ.get("ALPHA_TOKEN")  # optional - if not supplied, will use credentials file
GIT_COMMIT_SHA = os.getenv('GIT_COMMIT_SHA')
MONGO_URL = os.getenv('MONGO_URL', "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'avrae')
REDIS_URL = os.getenv('REDIS_URL', '127.0.0.1')
REDIS_DB_NUM = int(os.getenv('REDIS_DB_NUM', 0))
DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX', '!')
SENTRY_DSN = os.getenv('SENTRY_DSN') or None
# NEW_RELIC_LICENSE_KEY = os.getenv('NEW_RELIC_LICENSE_KEY')  # commented - set in newrelic.py because of import order
NUM_CLUSTERS = int(os.getenv('NUM_CLUSTERS')) if 'NUM_CLUSTERS' in os.environ else None
NUM_SHARDS = int(os.getenv('NUM_SHARDS')) if 'NUM_SHARDS' in os.environ else None
NO_DICECLOUD = os.environ.get("NO_DICECLOUD", False)
DICECLOUD_USER = os.getenv('DICECLOUD_USER', 'avrae') if not TESTING else credentials.test_dicecloud_user
DICECLOUD_PASS = credentials.dicecloud_pass.encode() if not TESTING else credentials.test_dicecloud_pass.encode()
DICECLOUD_API_KEY = credentials.dicecloud_token if not TESTING else credentials.test_dicecloud_token
GOOGLE_SERVICE_ACCOUNT = os.getenv('GOOGLE_SERVICE_ACCOUNT')  # optional - if not supplied, uses avrae-google.json
RELOAD_INTERVAL = os.getenv('RELOAD_INTERVAL', '3600')  # compendium static data reload interval
ECS_METADATA_ENDPT = os.getenv('ECS_CONTAINER_METADATA_URI')  # set by ECS
