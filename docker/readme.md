# Using Docker with Avrae Discord Bot

## Prerequisites

- [Docker Compose](https://docs.docker.com/compose/install/).
- [Dicecloud](https://www.dicecloud.com) account - do NOT register with Google, create a normal account.
- [Discord](https://discordapp.com/) account.
- [Google Drive Service Account](https://gspread.readthedocs.io/en/latest/oauth2.html#using-signed-credentials).
    - Follow steps 1-3 in the **Signed Credentials** portion. The contents of this JSON file is your `GOOGLE_SERVICE_ACCOUNT` env var.
    - Alternatively, save that json file in the root project directory as `avrae-google.json`.


### Discord setup

- `User Settings` (cog icon) > `Appearance`, enable "Developer Mode".
- Right-click your name in the user list and `Copy ID`, this is your `DISCORD_OWNER_USER_ID` below.
- Create a server for yourself to test with: big `+` icon, `Create a server`.

### Discord bot creation

- Go to the [Discord Developer Portal](https://discordapp.com/developers/).
- `New Application`, give it a cool name, `Create`.
- Copy the `Client ID` from `General Information`, you'll need this shortly.
- `Bot` > `Add Bot`.
- `Click to reveal token`, this is your `DISCORD_BOT_TOKEN` below.
- Invite your bot to your server: `https://discordapp.com/oauth2/authorize?permissions=388160&scope=bot&client_id=1234`, replacing `1234` with your bot's `Client ID`. Make sure you select the correct server!

## Docker Compose magic

1. Create a `docker\env` file with real credentials.
2. Run `docker-compose up --build`.

### docker\env file (dev)

    TOKEN=1
    DISCORD_OWNER_USER_ID=1
    DICECLOUD_USER=b
    DICECLOUD_PASS=c
    DICECLOUD_TOKEN=d

    # set these to these literal values
    MONGO_URL=mongodb://root:topsecret@mongo:27017
    REDIS_URL=redis://redis:6379/0
    
    # optional - only required if not using avrae-google.json 
    GOOGLE_SERVICE_ACCOUNT=e
