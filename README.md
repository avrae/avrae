# avrae
[![Build Status](https://travis-ci.org/avrae/avrae.svg?branch=master)](https://travis-ci.org/avrae/avrae)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/678413361db643d9af25d9e8e2cdeaeb)](https://www.codacy.com/app/mommothazaz123/avrae?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=avrae/avrae&amp;utm_campaign=Badge_Grade)

Avrae is a bot to facilitate running Dungeons & Dragons 5e online over Discord.

You can join the Avrae Development Discord [here](https://discord.gg/pQbd4s6)!

## Contributing

### How to run Avrae locally
#### Using Docker (Recommended)

Check out docker/readme.md.

#### Building Manually
###### OS Requirements
Avrae runs best on Ubuntu 16.04.4, but should be fully compatible with any UNIX-based system.
It is possible to run Avrae on Windows, but is not recommended.
##### Creating Support Files
Avrae is a large project, and can be a bit daunting to get running.
You'll need to create a few files first.

###### Credentials
`credentials.py` should include, at the very least, variables as such:
- `officialToken` - Empty string.
- `owner_id` - The Discord User ID of the bot owner (you, if testing).
- `test_redis_url` - The URI of a Redis cache (e.g. `redis://localhost:6379/0`)
- `test_mongo_url` - The URI of a MongoDB instance. (e.g. `mongodb://localhost:27017`)
- `testToken` - A valid Discord Bot token.
- `test_dicecloud_user` - A Dicecloud username.
- `test_dicecloud_pass` - The Dicecloud password of the Dicecloud user.
- `test_dicecloud_token` - A Dicecloud API token.

You'll also need to create a Google Drive Service Account. You can find instructions on how to do this [here](https://gspread.readthedocs.io/en/latest/oauth2.html#using-signed-credentials).
Follow steps 1-3 in the **Signed Credentials** portion. Rename the JSON `avrae-google.json` and put it in the project root.

###### Temp Folders
You will need to create a folder named `temp`.

###### Search Algorithm
You will also need to change the search algorithm used by spell lookup to the standard algorithm.

In `cogs5e/lookup.py`, delete line 14 (`from cogs5e.funcs.lookup_ml import ml_spell_search`) and
edit line 627
```py
spell = await select_spell_full(ctx, name, srd=srd, search_func=ml_spell_search)
```
to
```py
spell = await select_spell_full(ctx, name, srd=srd)
```

##### Actually Running Avrae
###### Redis
You will need to run a Redis instance to serve as a high-performance cache. Download [Redis 4.0](https://redis.io/download) and run a redis server locally **before** launching Avrae.
###### MongoDB
You will also need to run a MongoDB instance to serve as Avrae's database.
###### Avrae
To actually run Avrae, you need Python version >= 3.6.0 < 3.7.
First, install the dependencies with `pip install -r requirements.txt`.

- If running Avrae in unsharded mode (**recommended for testing**), run `python dbot.py test`.
- If running Avrae in sharded mode, run `python dbot.py`.

#### Testing
To test Avrae, run these commands:
```
docker-compose -f docker-compose.test.yml -p avrae build
docker-compose -f docker-compose.test.yml -p avrae up -d
docker logs -f avrae_tests_1
```
This should initialize an ephemeral database to run command unit tests in. 
You should set the `DICECLOUD_USER`, `DICECLOUD_PASS`, `DICECLOUD_TOKEN`, and `GOOGLE_SERVICE_ACCOUNT` env vars to their correct values.
