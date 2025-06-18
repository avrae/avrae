# Using Docker with Avrae Discord Bot

## Prerequisites

- [Docker Compose](https://docs.docker.com/compose/install/).
- [Discord](https://discordapp.com/) account.
- [Dicecloud v1](https://v1.dicecloud.com) account - do NOT register with Google, create a normal account.
- [Dicecloud v2](https://dicecloud.com) account - do NOT register with Google, create a normal account.
- [Google Drive Service Account](https://gspread.readthedocs.io/en/latest/oauth2.html).
    - Follow steps 1-7 in the **For Bots: Using Service Account** portion. The contents of this JSON file is
      your `GOOGLE_SERVICE_ACCOUNT` env var.
    - Alternatively, save that json file in the root project directory as `avrae-google.json`.

### Dicecloud v1

- Click Username in top left top open Account page
- `DICECLOUD_USER` is the login username
- `DICECLOUD_PASS` is your password (recommended to use a dedicated bot account with a random generated password)
- `DICECLOUD_TOKEN` is the `API KEY` revealed by `SHOW`

### Dicecloud v2

- Click gear in top left top open Account page
- `DICECLOUDV2_USER` is the login username
- `DICECLOUDV2_PASS` is your password (recommended to use a dedicated bot account with a random generated password)

### Discord setup

- `User Settings` (cog icon) > `Advanced`, enable "Developer Mode".
- Right-click your name in the user list and `Copy ID`, this is your `DISCORD_OWNER_USER_ID` below.
- Create a server for yourself to test with: big `+` icon, `Create a server`.

### Discord bot creation

- Go to the [Discord Developer Portal](https://discordapp.com/developers/).
- `New Application`, give it a cool name, `Create`.
- Copy the `Application ID` from `General Information`, you'll need this shortly.
- `Bot` > `Add Bot`.
- (Optional but recommended): Switch off `Public Bot` so only you can add this bot to servers.
- Scroll down to `Privileged Gateway Intents`, and enable the switches to the right of `Server Members Intent`
  and `Message Content Intent`.
- `Click to reveal token`, this is your `DISCORD_BOT_TOKEN` below.
- Invite your bot to your
  server: `https://discordapp.com/oauth2/authorize?permissions=274878295104&scope=bot&client_id=1234`, replacing `1234`
  with your bot's `Application ID`. Make sure you select the correct server!

## Docker Compose magic

1. Create a `docker\env` file with real credentials.
2. Run `docker-compose up --build`.

### docker\env file (dev)

    DISCORD_BOT_TOKEN=1
    DICECLOUD_USER=b
    DICECLOUD_PASS=c
    DICECLOUD_TOKEN=d
    
    DICECLOUDV2_USER=e
    DICECLOUDV2_PASS=f

    # set these to these literal values
    MONGO_URL=mongodb://root:topsecret@mongo:27017
    REDIS_URL=redis://redis:6379/0
    
    # set this to the contents of the JSON file downloaded in the Google Drive Service Account step
    GOOGLE_SERVICE_ACCOUNT=g

### Development with Kafka

If you're developing a feature that requires Kafka, you can either copy the `docker-compose.kafka-dev.yml` file to `docker-compose.override.yml` or pass it as an argument to `docker-compose`:

```bash
docker-compose -f docker-compose.yml -f docker-compose.kafka-dev.yml up --build
```

This will add the Kafka `broker` service and set up the necessary environment variables for Avrae to connect to Kafka.

To watch the messages being sent to Kafka, you can use the `kafka-console-consumer` command:

```bash
docker exec -it avrae-broker-1 /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic dnddev_avraebot --from-beginning
```
