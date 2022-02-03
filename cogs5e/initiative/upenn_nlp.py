"""
This module contains the logic for recording messages and other events for the UPenn NLP project.

The recording is primarily based on the `cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id` key in
Redis - if the key is present in for a given guild channel, that channel is considered recorded.

This key is set when a combat starts and expired 2 minutes after a combat ends in a channel that has opted in to NLP
recording.
"""
import datetime
import logging
import time
from typing import Any, Iterable, List, MutableMapping, Optional, Tuple

import cachetools
import disnake
from pydantic import BaseModel

import utils.context
from .combat import Combat

ONE_MONTH_SECS = 2592000

log = logging.getLogger(__name__)


# ==== models ====
class RecordedEvent(BaseModel):
    event_type: str


class RecordedMessage(RecordedEvent):
    event_type = 'message'
    message_id: int
    author_id: int
    author_name: str
    created_at: datetime.datetime
    content: str
    embeds: List[dict]  # just call disnake.Embed.to_dict() to generate these

    @classmethod
    def from_message(cls, message: disnake.Message):
        return cls(
            message_id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            created_at=message.created_at,
            content=message.content,
            embeds=[embed.to_dict() for embed in message.embeds]
        )


class RecordedCommandInvocation(RecordedMessage):
    event_type = 'command'
    prefix: str
    command_name: str
    called_by_alias: bool
    caster: Optional[dict]  # this is a StatBlock, typed as dict since StatBlock does not inherit from BaseModel
    targets: Optional[List[dict]]

    @classmethod
    def from_ctx(cls, ctx: utils.context.AvraeContext):
        message = ctx.message

        # caster
        caster = None
        if ctx.nlp_caster is not None:
            caster = ctx.nlp_caster.to_dict()
        elif ctx.nlp_character is not None:
            caster = ctx.nlp_character.to_dict()

        # targets
        targets = None
        if ctx.nlp_targets is not None:
            targets = [t.to_dict() for t in ctx.nlp_targets]

        return cls(
            message_id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            created_at=message.created_at,
            content=message.content,
            embeds=[embed.to_dict() for embed in message.embeds],

            prefix=ctx.prefix,
            command_name=ctx.command.qualified_name,
            called_by_alias=ctx.nlp_is_alias,
            caster=caster,
            targets=targets
        )


class RecordedCombatState(RecordedEvent):
    event_type = 'combat_state_update'
    data: Any
    human_readable: str

    @classmethod
    def from_combat(cls, combat: Combat):
        return cls(
            data=combat.to_dict(),
            human_readable=combat.get_summary(private=True)
        )


# ==== recorder ====
class NLPRecorder:
    # cache: channel id -> (when channels are recorded until, combat id); (0, None) if not recorded
    _recorded_channel_cache: MutableMapping[int, Tuple[int, Optional[str]]] = cachetools.TTLCache(
        maxsize=100000,
        ttl=120
    )

    def __init__(self, bot):
        self.bot = bot

    def register_listeners(self):
        self.bot.add_listener(self.on_message)
        self.bot.add_listener(self.on_command_completion)

    def deregister_listeners(self):
        self.bot.remove_listener(self.on_message)
        self.bot.remove_listener(self.on_command_completion)

    # ==== listeners ====
    async def on_message(self, message: disnake.Message):
        if message.guild is None:
            return
        await self.on_guild_message(message)

    async def on_command_completion(self, ctx: utils.context.AvraeContext):
        if ctx.guild is None:
            return
        await self.on_guild_command(ctx)

    # ==== main methods ====
    async def on_combat_start(self, combat: Combat):
        """
        Called with the just-started combat instance after a combat is started in a guild with NLP recording enabled.
        """
        # enable recording in the combat's channel
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=int(combat.channel),
            combat_id=combat.nlp_record_session_id
        )
        # record cached messages less than X minutes old for pre-combat context
        await self._record_events(
            combat.nlp_record_session_id,
            [
                RecordedMessage.from_message(message)
                for message in self.bot.cached_messages
                if (message.channel.id == int(combat.channel)
                    and message.created_at > disnake.utils.utcnow() - datetime.timedelta(minutes=15))
            ][-25:]
        )
        # record combat start meta event
        await self._record_event(combat.nlp_record_session_id, RecordedEvent(event_type='combat_start'))

    async def on_guild_message(self, message: disnake.Message):
        """
        Called on every message in a guild channel. If the guild has not opted in to NLP recording, does nothing.
        """
        is_recording, combat_id = await self._recording_info(message.guild.id, message.channel.id)
        if is_recording:
            await self._record_event(combat_id, RecordedMessage.from_message(message))

    async def on_guild_command(self, ctx: utils.context.AvraeContext):
        """
        Called after each successful invocation of a command in a guild. If the guild has not opted in to
        NLP recording, does nothing.
        """
        is_recording, combat_id = await self._recording_info(ctx.guild.id, ctx.channel.id)
        if is_recording:
            await self._record_event(combat_id, RecordedCommandInvocation.from_ctx(ctx))

    async def on_combat_commit(self, combat: Combat):
        """
        Called each time a combat that is being recorded is committed.
        """
        # bump the recording time to equal the combat's expiration time
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=int(combat.channel),
            combat_id=combat.nlp_record_session_id
        )
        # record a snapshot of the combat's human-readable and machine-readable state
        await self._record_event(combat.nlp_record_session_id, RecordedCombatState.from_combat(combat))

    async def on_combat_end(self, combat: Combat):
        """
        Called each time a combat that is being recorded ends.
        """
        # set the channel recording expiration to 2 minutes to record a few messages after combat ends
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=int(combat.channel),
            combat_id=combat.nlp_record_session_id,
            record_duration=120
        )
        # record a combat end meta marker
        await self._record_event(combat.nlp_record_session_id, RecordedEvent(event_type='combat_end'))

    # ==== helpers ====
    async def _recording_info(self, guild_id: int, channel_id: int) -> Tuple[bool, Optional[str]]:
        """
        Given a guild and channel ID, return a two-tuple of (is_recording, combat_id).
        """
        now = time.time()
        # is the channel currently being recorded?
        try:
            # memory cache
            channel_recording_until, combat_id = self._recorded_channel_cache[channel_id]
            log.debug(f"found recording info for {channel_id} in memory cache")
        except KeyError:
            # get from redis
            combat_id = await self.bot.rdb.get(
                f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id"
            )
            # and write to memory cache
            if combat_id is None:
                channel_recording_until = 0
            else:
                channel_recording_ttl = await self.bot.rdb.ttl(
                    f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id"
                )
                channel_recording_until = int(now + channel_recording_ttl)
                log.debug(f"found recording info for {channel_id} in redis with ttl {channel_recording_ttl}")
            self._recorded_channel_cache[channel_id] = (channel_recording_until, combat_id)

        log.debug(f"{channel_id}: {channel_recording_until=}, {combat_id=}")

        # if we are not recording or the recording session has expired, return
        if not channel_recording_until or combat_id is None:
            return False, None
        if channel_recording_until < now:
            return False, None
        return True, combat_id

    async def _update_channel_recording_until(
        self,
        guild_id: int,
        channel_id: int,
        combat_id: str,
        record_duration: int = ONE_MONTH_SECS
    ) -> int:
        """
        Refreshes or sets the time a channel is recording to *record_duration* from when this method is called.
        Returns the UNIX timestamp when the channel will stop recording.
        """
        recording_until = int(time.time()) + record_duration
        # mark the channel as recorded in cache so we start listening for messages
        self._recorded_channel_cache[channel_id] = (recording_until, combat_id)
        # set the channel as recorded in redis so we don't have to do a mongo roundtrip to check
        await self.bot.rdb.set(
            f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id",
            combat_id,
            ex=record_duration
        )
        log.debug(
            f"{channel_id}: recording_until updated to {recording_until!r} "
            f"(cache size: {len(self._recorded_channel_cache)})"
        )
        return recording_until

    async def _record_event(self, combat_id: str, event: RecordedEvent):
        """Saves an event to the recording for the given combat ID."""
        log.debug(f"saving 1 event to {combat_id=} of type {event.event_type!r}")
        await self.bot.mdb.nlp_recordings.insert_one(
            {
                "combat_id": combat_id,
                "timestamp": datetime.datetime.now(),
                **event.dict()
            }
        )

    async def _record_events(self, combat_id: str, events: Iterable[RecordedEvent]):
        """Saves many events to the recording for the given combat ID."""
        now = datetime.datetime.now()
        documents = [
            {
                "combat_id": combat_id,
                "timestamp": now,
                **event.dict()
            }
            for event in events
        ]
        if not documents:
            return
        log.debug(f"saving {len(documents)} events to {combat_id=}")
        await self.bot.mdb.nlp_recordings.insert_many(documents)
