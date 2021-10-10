import logging

import discord

from cogs5e.models.character import Character
from cogs5e.models.errors import NoCharacter
from ddb.gamelog.errors import IgnoreEvent
from ddb.utils import ddb_id_to_discord_user
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
        self._destination_channel = _sentinel

    # ==== discord utils ====
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

    async def destination_channel(self):
        """
        Returns the destination channel for this event.

        :rtype: discord.Channel
        """
        if self._destination_channel is not _sentinel:
            return self._destination_channel

        if self.event.message_scope == 'gameId':
            self._destination_channel = self.channel
            return self.channel
        elif self.event.message_scope == 'userId':
            if self.event.user_id == self.event.message_target:  # optimization: we already got this user (probably)
                discord_user = await self.get_discord_user()
            else:
                discord_user = await ddb_id_to_discord_user(self, self.event.message_target, self.guild)

            if discord_user is None:  # we did our best to find the user, but oh well
                raise IgnoreEvent(f"could not find discord user associated with userId: {self.event.message_target!r}")

            # try to find an existing dmchannel with the user
            existing_dmchannel = discord_user.dm_channel
            if existing_dmchannel is not None:
                self._destination_channel = existing_dmchannel
                return existing_dmchannel

            # otherwise we have to create a dmchannel :(
            self._destination_channel = await discord_user.create_dm()
            return self._destination_channel
        else:
            raise ValueError("message scope must be gameId or userId")

    async def trigger_typing(self):
        """Sends typing to the correct destination(s), accounting for message's scope."""
        destination = await self.destination_channel()
        try:
            await destination.trigger_typing()
        except discord.HTTPException as e:
            log.warning(f"Could not trigger typing in channel {destination!r}: {e}")

    async def send(self, *args, **kwargs):
        """Sends content to the correct destination(s), accounting for message's scope."""
        destination = await self.destination_channel()
        return await destination.send(*args, **kwargs)

    # ==== entity utils ====
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
        return compendium.lookup_entity('monster', int(self.event.entity_id))

    async def get_statblock(self):
        """:rtype: cogs5e.models.sheet.statblock.StatBlock or None"""
        return (await self.get_character()) or (await self.get_monster())
