# Avrae Discord Bot

[![Avrae Website](http://avrae.io/assets/img/AvraeLogo.jpg)](https://avrae.io/)

![Build Status](https://github.com/avrae/avrae/workflows/Test/badge.svg)

Avrae is a Discord bot designed to help you and your friends play D&D online.

You can join the Avrae Development Discord [here](https://support.avrae.io), and invite Avrae to your own Discord
server [here](https://invite.avrae.io)!

## Key Features

### Advanced Dice Roller

With a custom dice parser, Avrae is one of the most advanced dice rollers on Discord, capable of supporting pretty much
every type of roll needed to play D&D. Advantage, disadvantage, and crits are built in, you can keep, drop, or reroll
dice as needed, dice can explode, and dice can be bounded.

Want to use the dice roller in your own code? Check out [the code](https://github.com/avrae/d20)!

### Character Sheet Integration

Avrae can read character sheets from D&D Beyond, Dicecloud, or a Google Sheet, automatically generating macros to roll
attacks, ability checks, and saving throws. A player can then simply use a command to make a check, save, attack, or
cast, and all necessary rolls will be resolved automatically.

### Initiative Tracking

The initiative tracker is a fast way to track combat in a text channel. It supports automatic combatant sorting, HP, AC,
resistance, and status effect tracking, and integration with the character sheet manager and 5e content to further
streamline combat.

### Moddability

Have a feature in mind that isn't already in Avrae? Avrae provides a fully-featured modding API to write your own
commands, and a place to share them with the community!

Check out [the docs](https://avrae.readthedocs.io/en/latest/aliasing/api.html) and the
[Alias Workshop](https://avrae.io/dashboard/workshop)!

## Contributing

There are a few options to run Avrae locally. Docker is easier to get started with with less managment of dependencies,
but slower and more resource-intensive.

### Using Docker (Recommended)

Check out [README-docker.md](README-docker.md).

### Building Manually

#### Dependencies

**Services/OS**

- Ubuntu 18.04+ or other UNIX system (Windows is compatible but untested)
- Redis Server 4+ (<https://redis.io/download>)
- MongoDB Community Server 3.6+ (<https://www.mongodb.com/try/download/community>)
- Python 3.8+ (<https://www.python.org/downloads/>)

**Support Files**

You'll need to create a Google Drive Service Account. You can find instructions on how to do
this [here](https://gspread.readthedocs.io/en/latest/oauth2.html).

Follow steps 1-7 in the **For Bots: Using Service Account** portion. Rename the JSON `avrae-google.json` and put it in
the project root.

**Python Packages**

We recommend using a [Virtual Environment](https://docs.python.org/3/library/venv.html) for Avrae development to prevent
package installs from polluting the global Python install. You can create and active a virtual environment by running:

```bash
$ python3 --version  # to ensure that you are creating a venv from the right python version
$ python3 -m venv venv
$ source venv/bin/activate
# if the venv was set up correctly, you should see (venv) before your username in the terminal
# run these commands to check the installed version and path
(venv) $ python --version
Python 3.X.X
(venv) $ pip --version
pip X.Y.Z from (project root)/venv/lib/python3.X/site-packages/pip (python 3.X)
```

To install the dependencies, run:

```bash
(venv) $ pip install -r requirements.txt
```

*Optional* - You can install the `avrae-automation-common` and `draconic` dependencies from your local filesystem
rather than pip+git, to make working on depended libraries in parallel easier:

```bash
(venv) $ pip install /path/to/automation-common -e
(venv) $ pip install /path/to/draconic -e
```

Any changes to the library will immediately be picked up in avrae without requiring a reinstall of the library.

#### Environment Variables

| Name                             | Description                                                                                                                                                                      | Used For                      | Set By (dev)         | Set By (prod)                     | Required?       |
|----------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------|----------------------|-----------------------------------|-----------------|
| `DISCORD_BOT_TOKEN`              | The bot token used to authenticate to the Discord API. See "Discord Bot Token", below.                                                                                           | Connecting to the Discord API | you                  | AWS Secrets Manager via Terraform | **yes**         |
| `TESTING`                        | Whether the bot is running in a dev environment. See "Testing Env Var", below. Also set if `test` arg supplied in CLI.                                                           | Enabling certain debug logs   | you                  | N/A                               | no              |
| `ENVIRONMENT`                    | The environment the bot is running in. Defaults to `development` if `TESTING` is set, or `production` otherwise.                                                                 | Logs (e.g. Sentry)            | set to `development` | Terraform                         | **yes**         |
| `GIT_COMMIT_SHA`                 | The commit SHA of the running deploy.                                                                                                                                            | Cluster coordination key      | N/A                  | Docker via GH Actions             | *prod only*     |
| `NUM_CLUSTERS`                   | The number of clusters (ECS tasks) Avrae is running across. Defaults to 1.                                                                                                       | Cluster coordination          | N/A                  | Terraform                         | *prod only*     |
| `NUM_SHARDS`                     | An explicit override for the number of shards to run across all shards. Defaults to dynamic value from Discord.                                                                  | Cluster coordination          | N/A                  | Terraform (nightly/stg)           | no              |
| `RELOAD_INTERVAL`                | An interval to automatically reload gamedata at, in seconds. Defaults to 0. This should be set to 0.                                                                             | Loading gamedata              | N/A                  | N/A                               | no              |
| `ECS_CONTAINER_METADATA_URI`     | <https://docs.aws.amazon.com/AmazonECS/latest/userguide/task-metadata-endpoint-v3-fargate.html>                                                                                  | Cluster coordination          | N/A                  | AWS Fargate                       | *prod only*     |
| `MONSTER_TOKEN_ENDPOINT`         | The base URL that monster token paths defined in monster gamedata are relative to.                                                                                               | `!token`                      | N/A                  | Terraform                         | *prod only*     |
| `DDB_MEDIA_S3_BUCKET_DOMAIN`     | The S3 bucket domain for DDB media assets, such as character avatars.                                                                                                            | `!token`                      | N/A                  | Terraform                         | *prod only*     |
| `DRACONIC_SIGNATURE_SECRET`      | The secret used to sign signatures in the Draconic API's `signature()` function. Defaults to `secret`.                                                                           | Aliasing                      | optional             | AWS Secrets Manager via Terraform | *prod only*     |
| `MONGO_URL`                      | The connection URL used to connect to MongoDB. Defaults to `mongodb://localhost:27017`.                                                                                          | Connecting to database        | you                  | AWS Secrets Manager via Terraform | **yes**         |
| `MONGODB_DB_NAME`                | The name of the database in Mongo to use. Defaults to `avrae`.                                                                                                                   | Connecting to database        | optional             | Terraform                         | no              |
| `REDIS_URL`                      | The connection URL used to connect to Redis. Defaults to `redis://localhost:6379/0`.                                                                                             | Connecting to database        | you                  | Terraform                         | **yes**         |
| `REDIS_DB_NUM`                   | The database number to use in Redis. Defaults to `0`.                                                                                                                            | Connecting to database        | optional             | Terraform                         | no              |
| `DEFAULT_PREFIX`                 | The default command prefix. Defaults to `!`.                                                                                                                                     | Running commands              | optional             | Terraform                         | no              |
| `SENTRY_DSN`                     | The [Sentry DSN](https://docs.sentry.io/platforms/python/) used to send exceptions to Sentry. If not set, no errors are sent to Sentry.                                          | Monitoring                    | optional             | AWS Secrets Manager via Terraform | *prod only*     |
| `DD_SERVICE`                     | The name of the service, used for DataDog. If not set, disables DataDog tracing and profiling.                                                                                   | Monitoring                    | optional             | Terraform                         | *prod only*     |
| `NO_DICECLOUD`                   | If set, disables Dicecloud v1 connections in the running bot. Defaults to true if `DICECLOUD_USER` is not set.                                                                   | CI                            | optional             | N/A                               | no              |
| `DICECLOUD_USER`                 | The [Dicecloud v1](https://v1.dicecloud.com) username of the bot account.                                                                                                        | Sheet Import                  | you                  | Terraform                         | **yes**         |
| `DICECLOUD_PASS`                 | The Dicecloud v1 password of the bot account.                                                                                                                                    | Sheet Import                  | you                  | AWS Secrets Manager via Terraform | **yes**         |
| `DICECLOUD_TOKEN`                | The Dicecloud v1 API key of the bot account.                                                                                                                                     | Sheet Import                  | you                  | AWS Secrets Manager via Terraform | **yes**         |
| `NO_DICECLOUDV2`                 | If set, disables Dicecloud v2 connections in the running bot.                                                                                                                    | CI                            | optional             | N/A                               | no              |
| `DCV2_NO_AUTH`                   | If set, connects to Dicecloud v2 without any form of authentication. As such, any imported sheets must be public. Defaults to true if `DICECLOUDV2_USER` is not set.             | CI                            | optional             | N/A                               | no              |
| `DICECLOUDV2_USER`               | The [Dicecloud v2](https://dicecloud.com) username of the bot account.                                                                                                           | Sheet Import                  | you                  | Terraform                         | **yes**         |
| `DICECLOUDV2_PASS`               | The Dicecloud v2 password of the bot account.                                                                                                                                    | Sheet Import                  | you                  | AWS Secrets Manager via Terraform | **yes**         |
| `GOOGLE_SERVICE_ACCOUNT`         | The contents of the [Google Drive Service Account](https://gspread.readthedocs.io/en/latest/oauth2.html) JSON key file. Defaults to a file named `avrae-google.json` if not set. | Sheet Import                  | you                  | AWS Secrets Manager via Terraform | **yes**         |
| `DDB_AUTH_SECRET`                | The secret used to sign JWT claims to exchange Discord user info for a STT via the Auth Service.                                                                                 | Entitlements                  | 1Password            | AWS Secrets Manager via Terraform | *DDB team only* |
| `DDB_AUTH_WATERDEEP_SECRET`      | The secret used to verify JWTs returned from the Auth Service.                                                                                                                   | Entitlements                  | 1Password            | AWS Secrets Manager via Terraform | *DDB team only* |
| `DDB_AUTH_AUDIENCE`              | Override a verification for the `aud` claim of an Auth Service JWT. Defaults to `avrae.io`.                                                                                      | Entitlements                  | N/A                  | N/A                               | no              |
| `DDB_AUTH_ISSUER`                | Override a verification for the `iss` claim of an Auth Service JWT. Defaults to `dndbeyond.com`.                                                                                 | Entitlements                  | N/A                  | N/A                               | no              |
| `DDB_AUTH_EXPIRY_SECONDS`        | Override a JWT's lifetime for the Discord -> STT exchange. Defaults to 5 minutes (300).                                                                                          | Entitlements                  | N/A                  | N/A                               | no              |
| `DDB_AUTH_SERVICE_URL`           | The base URL for requests to the DDB Auth Service. If not set, all entitlements code is disabled.                                                                                | Entitlements                  | 1Password            | Terraform                         | *DDB team only* |
| `DYNAMO_REGION`                  | The AWS region to search for resources in. This controls more than Dynamo. Defaults to `us-east-1`.                                                                              | Entitlements                  | 1Password            | Terraform                         | *DDB team only* |
| `DYNAMO_ENTITLEMENTS_TABLE`      | The name of the DynamoDB table to query for entitlements data. Defaults to `entitlements-live`.                                                                                  | Entitlements                  | 1Password            | Terraform                         | *DDB team only* |
| `AWS_ACCESS_KEY_ID`              | The AWS Access Key ID to connect to AWS resources.                                                                                                                               | Entitlements                  | 1Password            | AWS Fargate                       | *DDB team only* |
| `AWS_SECRET_ACCESS_KEY`          | The AWS Secret Access Key to connect to AWS resources.                                                                                                                           | Entitlements                  | 1Password            | AWS Fargate                       | *DDB team only* |
| `NLP_KINESIS_DELIVERY_STREAM`    | The name of the AWK Kinesis Firehose delivery stream used to ingest NLP events.                                                                                                  | UPenn NLP                     | N/A                  | Terraform                         | no              |
| `CHARACTER_COMPUTATION_ENDPOINT` | The API endpoint used to call the Character Computation lambda.                                                                                                                  | Sheet Import                  | you                  | Terraform                         | *DDB team only* |
| `DDB_WATERDEEP_URL`              | The base URL for requests to the Waterdeep monoloth. Defaults to `https://www.dndbeyond.com`.                                                                                    | Campaign Link                 | 1Password            | Terraform                         | no              |
| `DDB_GAMELOG_ENDPOINT`           | The endpoint used to post Game Log events to the Game Log. Defaults to `https://game-log-rest-live.dndbeyond.com/v1`.                                                            | Campaign Link                 | 1Password            | Terraform                         | no              |
| `DDB_CHARACTER_SERVICE_URL`      | The base URL for requests to the Character Service. Defaults to `https://character-service.dndbeyond.com/character/v5`.                                                          | Campaign Link                 | 1Password            | Terraform                         | no              |
| `DDB_SCDS_SERVICE_URL`           | The base URL for requests to the Simple Character Data Store. Defaults to `https://character-service-scds.dndbeyond.com/v2`.                                                     | Campaign Link                 | 1Password            | Terraform                         | no              |
| `LAUNCHDARKLY_SDK_KEY`           | The [LaunchDarkly SDK Key](https://docs.launchdarkly.com/sdk/server-side/python).                                                                                                | Feature Flags                 | 1Password            | AWS Secrets Manager via Terraform | *DDB team only* |
| `DBL_TOKEN`                      | The Discord Bot List API token.                                                                                                                                                  | Updating server count         | N/A                  | AWS Secrets Manager via Terraform | no              |

**Discord Bot Token**

To create a Discord bot user, go to the [Discord Developer Portal](https://discord.com/developers/).

- `New Application`, give it a cool name, `Create`.
- `Bot` > `Add Bot`.
- (Optional but recommended): Switch off `Public Bot` so only you can add this bot to servers.
- Scroll down to `Privileged Gateway Intents`, and enable the switches to the right of `Server Members Intent`
  and `Message Content Intent`.
- `Click to Reveal Token`, this is your `DISCORD_BOT_TOKEN`.

**Testing Env Var**

The `TESTING` env var, if present, enables/disables the following:

- Dicecloud Client: Meteor debug logs enabled
- cogs.publicity: Discord Bot List update disabled
- config: `ENVIRONMENT` set to `development` by default if not manually set
- Discord Application Commands: enables command sync debug logs and command testing guilds

#### Running

```bash
(venv) $ python dbot.py test
```

<details>
  <summary>VSCode launch.json Template</summary>

  ```json
    {
      "version": "0.2.0",
      "configurations": [
        {
          "name": "Run Avrae",
          "type": "python",
          "request": "launch",
          "program": "dbot.py",
          "console": "integratedTerminal",
          "env": {
            "DISCORD_BOT_TOKEN":" ",
            "DISCORD_OWNER_USER_ID": " ",
            "DICECLOUD_USER": " ",
            "DICECLOUD_PASS": " ",
            "DICECLOUD_TOKEN": " ",
            "DICECLOUDV2_USER": " ",
            "DICECLOUDV2_PASS": " ",
            "MONGO_URL": " ",
            "REDIS_URL": " ",
            "ENVIRONMENT": " ",
            "DDB_AUTH_SECRET": " ",
            "DYNAMO_REGION": " ",
            "DYNAMO_ENTITLEMENTS_TABLE": " ",
            "DDB_AUTH_SERVICE_URL": " ",
            "AWS_ACCESS_KEY_ID": " ",
            "AWS_SECRET_ACCESS_KEY": " ",
            "DDB_AUTH_WATERDEEP_SECRET": " ",
            "CHARACTER_COMPUTATION_ENDPOINT": " ",
            "DDB_WATERDEEP_URL": " ",
            "DDB_GAMELOG_ENDPOINT": " ",
            "DDB_CHARACTER_SERVICE_URL": " ",
            "DDB_SCDS_SERVICE_URL": " ",
            "LAUNCHDARKLY_SDK_KEY": " "
          }
        }
      ]
    }
  ```

</details>

### Testing

This repo contains a pytest test suite that mocks a number of interactions between Avrae and the Discord API, and runs
end-to-end tests between user input, bot output, and database state.

These tests can be found in `tests/`.

#### Dependencies

```bash
(venv) $ pip install -r tests/requirements.txt
```

#### Running

Tests can either be run using Docker Compose, or manually.

**Docker**

```bash
docker-compose -f docker-compose.ci.yml -p avrae up -d --build
docker logs -f avrae_tests_1
```

Once tests complete, it is recommended to clean up the containers with `docker-compose down`.

**Manually**

```bash
(venv) $ TESTING=1 pytest tests/
```

In either case, you should set `NO_DICECLOUD=1`.

### Docs

Avrae uses Sphinx to generate documentation for the Aliasing API and Automation Engine. The source for this
documentation can be found in `docs/`.

By default, each push to `master` will trigger a new build of the docs at <https://avrae.readthedocs.io/en/latest/>.

You can also build the docs manually:

```bash
# install dependencies
(venv) $ cd docs
(venv) $ pip install -r requirements.txt
# build and open browser
(venv) $ make preview
# build
(venv) $ make html
```

### Committing, Formatting, and Linting

Avrae uses [Black](https://black.readthedocs.io/) to format and lint its Python code.
Black is automatically run on every commit via pre-commit hook, and takes its configuration options from the `pyproject.toml` file.

The pre-commit hook is installed by by running `pre-commit install` from the repo root.
The hook's configuration is governed by the `.pre-commit-config.yaml` file.

#### Dependencies

In order to run `pre-commit` or `black`, they must be installed.
These dependencies are contained within the `test/requirements.txt` file, and can be installed like so:

```bash
(venv) $ pip install -r test/requirements.txt
```
