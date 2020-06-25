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
Check out `utils/config.py` for the list of env vars.

You'll also need to create a Google Drive Service Account. You can find instructions on how to do this [here](https://gspread.readthedocs.io/en/latest/oauth2.html#using-signed-credentials).
Follow steps 1-3 in the **Signed Credentials** portion. Rename the JSON `avrae-google.json` and put it in the project root.

##### Actually Running Avrae
###### Redis
You will need to run a Redis instance to serve as a high-performance cache. Download [Redis 4.0](https://redis.io/download) and run a redis server locally **before** launching Avrae.
###### MongoDB
You will also need to run a MongoDB instance to serve as Avrae's database.
###### Avrae
To actually run Avrae, you need Python version >= 3.8.0.
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

#### Misc
Env vars required to deploy to production:
- `NUM_CLUSTERS` - equal to the number of ECS tasks running Avrae
- `DDB_AUTH_SECRET` - JWT signing secret for DDB auth request
- `DDB_AUTH_WATERDEEP_SECRET` - JWT signing secret for DDB auth response
- `DDB_AUTH_AUDIENCE` - JWT audience (default `"avrae.io"`)
- `DDB_AUTH_ISSUER` - JWT issuer (default `"dndbeyond.com"`)
- `DDB_AUTH_EXPIRY_SECONDS` - JWT expiry (default 5m)
- `DDB_AUTH_SERVICE_URL` - DDB Auth Service base URL
- `DYNAMO_REGION` - AWS region for Entitlements DB
- `DYNAMO_USER_TABLE` - Table name for Entitlements user table
- `DYNAMO_ENTITY_TABLE` - Table name for Entitlements entity table
- `AWS_ACCESS_KEY_ID` - AWS Access Key to access Dynamo
- `AWS_SECRET_ACCESS_KEY` - AWS Secret Access Key
- `LAUNCHDARKLY_SDK_KEY` - LaunchDarkly SDK Key
- `CHARACTER_COMPUTATION_ENDPOINT` - HTTP endpoint for DDB character computation call

Other env vars:
- `NUM_SHARDS` - explicitly set the number of shards to run
- `GIT_COMMIT_SHA` - should be set in Travis (required for prod)
