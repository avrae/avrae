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

1. **Create the application**
   - Go to the [Discord Developer Portal](https://discordapp.com/developers/).
   - Click `New Application`, give it a name, then click `Create`.
   - Copy the `Application ID` from `General Information` (you'll need this for the invite link).

2. **Configure the bot**
   - Navigate to the `Bot` tab.
   - Under `Privileged Gateway Intents`, enable both `Server Members Intent` and `Message Content Intent`.
   - Click `Save Changes`.

3. **Generate the bot token**
   - Still on the `Bot` tab, scroll down to `Token`.
   - Reset the `Bot Token` by clicking `Reset Token` (verify authentication if prompted).
   - Copy the token - this will be your `DISCORD_BOT_TOKEN` for the configuration.

4. **Set privacy options (recommended so only you can add the bot to a server)**
   - Navigate to the `Installation` tab.
   - Select `None` from the `Install Link` dropdown.
   - Click `Save Changes`.
   - Navigate to the `Bot` tab, scroll down to `Authorization Flow` and toggle off the `Public Bot` option.
   - Click `Save Changes`.

5. **Add bot to your server**
   - Use this URL to invite your bot: `https://discordapp.com/oauth2/authorize?permissions=274878295104&scope=bot&client_id=YOUR_APPLICATION_ID`
   - Replace `YOUR_APPLICATION_ID` with the Application ID you copied earlier.
   - Select your server from the dropdown and authorize the bot.

## Docker Compose magic

1. Create a `docker\env` file with real credentials (Reference the example below).
2. Run `docker-compose up --build`.
3. Wait for the bot to start up and join your server.
4. Stop the bot by pressing `Ctrl+C` in the terminal.
5. Run `docker-compose down -v` to remove the containers and volumes.

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
