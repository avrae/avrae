import logging

from utils.functions import get_guild_member, user_from_id

_sentinel = object()
log = logging.getLogger(__name__)


class GameLogEventContext:
    """
    The context in which a game log event occurred. It is convention to pass this to the handler as ``gctx``.
    """

    def __init__(self, bot, event, guild, channel):
        """
        :type bot: dbot.Avrae
        :type event: ddb.gamelog.events.GameLogEvent
        :type guild: discord.Guild
        :type channel: discord.TextChannel
        """
        self.bot = bot
        self.event = event
        self.guild = guild
        self.channel = channel

        # cached values
        # we use sentinel because the value we want to cache can be None
        self._discord_user_id = _sentinel
        self._discord_user = _sentinel
        self._character = _sentinel

    async def get_discord_user_id(self):
        """
        Gets the Discord user ID for the DDB user associated with the event.

        :rtype: int or None
        """
        if self._discord_user_id is not _sentinel:
            return self._discord_user_id
        # this mapping is updated in ddb.client.get_ddb_user()
        result = await self.bot.mdb.ddb_account_map.find_one({"ddb_id": self.event.user_id})
        if result is not None:
            self._discord_user_id = result['discord_id']
        else:
            self._discord_user_id = None
        return self._discord_user_id

    async def get_discord_user(self):
        """
        Gets the Discord user associated with the event.

        :rtype: discord.User or None
        """
        if self._discord_user is not _sentinel:
            return self._discord_user

        if self.guild is not None:
            # optimization: we can use get_guild_member rather than user_from_id because we're operating in a guild
            user = await get_guild_member(self.guild, await self.get_discord_user_id())
        else:
            # technically user_from_id expects a :class:`~discord.ext.commands.Context` but GameLogEventContext has the
            # necessary duck typing
            # regardless, we should probably be aware that this is happening
            log.warning(
                f"No guild found when getting discord user for event {self.event.id!r}, falling back to user fetch")
            user = await user_from_id(self, await self.get_discord_user_id())

        self._discord_user = user
        return user
