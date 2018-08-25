# avrae
[![Build Status](https://travis-ci.org/avrae/avrae.svg?branch=master)](https://travis-ci.org/avrae/avrae)

Avrae is a bot to facilitate running Dungeons & Dragons 5e online over Discord.

You can join the Avrae Development Discord [here](https://discord.gg/pQbd4s6)!

## Contributing

#### How to run Avrae locally
###### OS Requirements
Avrae runs best on Ubuntu 16.04.4, but should be fully compatible with any UNIX-based system.
It is possible to run Avrae on Windows, but is not recommended.
###### Support File Package
You can download templates of all the required files at https://andrew-zhu.com/avrae/avrae-files.zip.
##### Creating Support Files
Avrae is a large project, and can be a bit daunting to get running.
You'll need to create a few files first.

`credentials.py` should include, at the very least, variables as such:
- `officialToken` - Empty string.
- `owner_id` - The Discord User ID of the bot owner (you, if testing).
- `test_redis_url` - The URI of a Redis cache (probably `redis://localhost:6379/0`)
- `test_mongo_url` - The URI of a MongoDB instance. (e.g. `mongodb+srv://user:pass@localhost/test`)
- `testToken` - A valid Discord Bot token.
- `test_dicecloud_user` - A Dicecloud username.
- `test_dicecloud_pass` - The Dicecloud password of the Dicecloud user.
- `test_dicecloud_token` - A Dicecloud API token.

You'll also need to create a Google Drive Service Account. You can find instructions on how to do this [here](http://pygsheets.readthedocs.io/en/latest/authorizing.html).
Follow steps 1-4, then follow the **Signed Credentials** portion. Rename the JSON `avrae-google.json` and put it in the project root.

After creating the credential files, you'll have to create a few files so that Lookup doesn't break:
- `res/conditions.json`
- `res/rules.json`
- `res/feats.json`
- `res/races.json`*
- `res/classes.json`
- `res/bestiary.json`*
- `res/spells.json`
- `res/items.json`*
- `res/auto_spells.json`
- `res/backgrounds.json`
- `res/itemprops.json`

These files should just contain an empty JSON array (`[]`) for testing.
Files marked with a * can be obtained by running the [data parsers](https://github.com/avrae/avrae-data).

##### Actually Running Avrae
###### Redis
You will need to run a Redis cache to serve as a high-performance cache. Download [Redis 4.0](https://redis.io/download) and run a redis server locally **before** launching Avrae.
###### MongoDB
You will also need to run a MongoDB instance to serve as Avrae's database.
###### Avrae
To actually run Avrae, you need Python version >= 3.6.0 < 3.7.
First, install the dependencies with `pip install -r requirements.txt`.

- If running Avrae in unsharded+unsupervised mode (**recommended for testing**), you can just run `python dbot.py test`.
- If running Avrae in sharded+unsupervised mode, launch each shard with `SHARDS=[NUM_SHARDS] python dbot.py test -s [SHARD_ID]`.
- If running Avrae in sharded+supervised mode, run `SHARDS=[NUM_SHARDS] python overseer.py test 0 [NUM_SHARDS-1]`.

