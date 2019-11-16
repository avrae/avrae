import os

# Empty string.
# - Actually the Discord token to use in non-testing
officialToken = ''

# The Discord User ID of the bot owner (you, if testing).
owner_id = int(os.getenv('DISCORD_OWNER_USER_ID', '0'))

# A valid Discord Bot token.
# - Overwrites officialToken if TESTING (environment variable set, or bot run with "test" parameter)
testToken = os.getenv('DISCORD_BOT_TOKEN', '')

# The URI of a MongoDB instance. (e.g. mongodb://localhost:27017)
test_mongo_url = 'mongodb://root:topsecret@mongo:27017'

# The URI of a Redis cache (e.g. redis://localhost:6379/0)
test_redis_url = 'redis://redis:6379/0'

# A Dicecloud username.
test_dicecloud_user = os.getenv('DICECLOUD_USER', '')

# The Dicecloud password of the Dicecloud user.
test_dicecloud_pass = os.getenv('DICECLOUD_PASS', '')

# A Dicecloud API token.
test_dicecloud_token = os.getenv('DICECLOUD_TOKEN', '')
