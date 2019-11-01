import os
import sys

from utils.functions import get_positivity

# ==== bot config constants / env vars ====
TESTING = get_positivity(os.environ.get("TESTING", False))
if 'test' in sys.argv:
    TESTING = True
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production' if not TESTING else 'development')
GIT_COMMIT_SHA = os.getenv('GIT_COMMIT_SHA')
MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'avrae')
REDIS_DB_NUM = int(os.getenv('REDIS_DB_NUM', 0))
DEFAULT_PREFIX = os.getenv('DEFAULT_PREFIX', '!')
SENTRY_DSN = os.getenv('SENTRY_DSN') or None
NUM_CLUSTERS = int(os.getenv('NUM_CLUSTERS')) if 'NUM_CLUSTERS' in os.environ else None
NUM_SHARDS = int(os.getenv('NUM_SHARDS')) if 'NUM_SHARDS' in os.environ else None
NO_DICECLOUD = os.environ.get("NO_DICECLOUD", False)
ECS_METADATA_ENDPT = os.getenv('ECS_CONTAINER_METADATA_URI')  # set by ECS
