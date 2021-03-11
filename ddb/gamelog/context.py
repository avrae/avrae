import logging

from cogs5e.models.character import Character
from cogs5e.models.errors import NoCharacter
from gamedata.compendium import compendium
from utils.functions import get_guild_member, user_from_id

_sentinel = object()
log = logging.getLogger(__name__)


class GameLogEventContext:
    """
    The context in which a game log event occurred. It is convention to pass this to the handler as ``gctx``.
    """

    def __init__(self, bot, event, campaign, guild, channel, discord_user_id):
        """
        :type bot: dbot.Avrae
        :type event: ddb.gamelog.event.GameLogEvent
        :type campaign: ddb.gamelog.link.CampaignLink
        :type guild: discord.Guild
        :type channel: discord.TextChannel
        :type discord_user_id: int
        """
        self.bot = bot
        self.event = event
        self.campaign = campaign
        self.guild = guild
        self.channel = channel
        self.discord_user_id = discord_user_id

        # cached values
        # we use sentinel because the value we want to cache can be None
        self._discord_user = _sentinel
        self._character = _sentinel

    async def get_discord_user(self):
        """
        Gets the Discord user associated with the event.

        :rtype: discord.User or None
        """
        if self._discord_user is not _sentinel:
            return self._discord_user

        if self.guild is not None:
            # optimization: we can use get_guild_member rather than user_from_id because we're operating in a guild
            user = await get_guild_member(self.guild, self.discord_user_id)
        else:
            # technically user_from_id expects a :class:`~discord.ext.commands.Context` but GameLogEventContext has the
            # necessary duck typing
            # regardless, we should probably be aware that this is happening
            log.warning(
                f"No guild found when getting discord user for event {self.event.id!r}, falling back to user fetch")
            user = await user_from_id(self, self.discord_user_id)

        self._discord_user = user
        return user

    async def get_character(self):
        """
        Gets the Avrae character associated with the event. Returns None if the character is not found.

        :rtype: cogs5e.models.character.Character or None
        """
        if self._character is not _sentinel:
            return self._character

        # event is not in the character scope
        if self.event.entity_type != 'character':
            self._character = None
            return None

        ddb_character_upstream = f"beyond-{self.event.entity_id}"
        try:
            self._character = await Character.from_bot_and_ids(self.bot, str(self.discord_user_id),
                                                               ddb_character_upstream)
        except NoCharacter:
            self._character = None
        return self._character

    async def get_monster(self):
        """
        Gets the Monster associated with the event. Returns None if the event is not associated with a monster.

        :rtype: gamedata.monster.Monster or None
        """
        if not self.event.entity_id:
            return None
        return compendium.lookup_by_entitlement('monster', int(self.event.entity_id))

    async def get_statblock(self):
        """:rtype: cogs5e.models.sheet.statblock.StatBlock or None"""
        return (await self.get_character()) or (await self.get_monster())
