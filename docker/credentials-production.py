import os

# Empty string.
# - Actually the Discord token to use in non-testing
officialToken = os.environ['DISCORD_BOT_TOKEN']

# The Discord User ID of the bot owner (you, if testing).
owner_id = int(os.getenv('DISCORD_OWNER_USER_ID', '0'))

# A valid Discord Bot token.
# - Overwrites officialToken if TESTING (environment variable set, or bot run with "test" parameter)
testToken = ''

# The URI of a MongoDB instance. (e.g. mongodb://localhost:27017)
mongo_url = os.environ['MONGO_URL']

# The URI of a Redis cache (e.g. redis://localhost:6379/0)
redis_url = os.environ['REDIS_URL']

# A Dicecloud username.
dicecloud_user = os.environ['DICECLOUD_USER']

# The Dicecloud password of the Dicecloud user.
dicecloud_pass = os.environ['DICECLOUD_PASS']

# A Dicecloud API token.
dicecloud_token = os.environ['DICECLOUD_TOKEN']

# Discord Bot List token (only needed in prod)
dbl_token = os.getenv('DBL_TOKEN')


# - Should probably fix the code to not demand these
test_mongo_url = ''
test_redis_url = ''
