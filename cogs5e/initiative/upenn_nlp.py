"""
This module contains the logic for recording messages and other events for the UPenn NLP project.

The recording is primarily based on the `cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id` key in
Redis - if the key is present in for a given guild channel, that channel is considered recorded.

This key is set when a combat starts and expired 2 minutes after a combat ends in a channel that has opted in to NLP
recording.
"""
import abc
import datetime
import time
from typing import Iterable, List, Optional, Tuple

import cachetools
import disnake
from bson import ObjectId
from pydantic import BaseModel

from .combat import Combat

ONE_MONTH_SECS = 2592000


# ==== models ====
class RecordedEvent(BaseModel, abc.ABC):
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


# ==== recorder ====
class NLPRecorder:
    # cache: channel id -> (when channels are recorded until, combat id); (0, None) if not recorded
    _recorded_channel_cache: cachetools.TTLCache[int, Tuple[int, Optional[str]]] = cachetools.TTLCache(
        maxsize=100000,
        ttl=120
    )

    def __init__(self, bot):
        self.bot = bot

    # ==== hooks ====
    async def on_combat_start(self, combat: Combat):
        """
        Called with the just-started combat instance after a combat is started in a guild with NLP recording enabled.
        """
        # enable recording in the combat's channel
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=int(combat.channel),
            combat_id=combat.id
        )
        # record cached messages less than X minutes old for pre-combat context
        # record combat start meta event
        # todo

    async def on_guild_message(self, message: disnake.Message):
        """
        Called on every message in a guild channel. If the guild has not opted in to NLP recording, does nothing.
        """
        guild_id = message.guild.id
        channel_id = message.channel.id
        now = time.time()
        # is the channel currently being recorded?
        try:
            # memory cache
            channel_recording_until, combat_id = self._recorded_channel_cache[channel_id]
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
                channel_recording_until = now + channel_recording_ttl
            self._recorded_channel_cache[channel_id] = (channel_recording_until, combat_id)

        # if we are not recording or the recording session has expired, return
        if not channel_recording_until or combat_id is None:
            return
        if channel_recording_until < now:
            return

        # we are recording, save the message
        await self._record_event(combat_id, RecordedMessage.from_message(message))

    # todo: on_guild_command to record valid command invocations and whether something was an alias

    async def on_combat_commit(self, combat: Combat):
        """
        Called each time a combat that is being recorded is committed.
        """
        # bump the recording time to equal the combat's expiration time
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=int(combat.channel),
            combat_id=combat.id
        )
        # record a snapshot of the combat's human-readable and machine-readable state
        # do this in a separate task to allow the commit to go through with minimal delay
        # todo

    async def on_combat_end(self, combat: Combat):
        """
        Called each time a combat that is being recorded ends.
        """
        # set the channel recording expiration to 2 minutes to record a few messages after combat ends
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=int(combat.channel),
            combat_id=combat.id,
            record_duration=120
        )
        # record a combat end meta marker
        # todo

    # ==== helpers ====
    async def _update_channel_recording_until(
        self,
        guild_id: int,
        channel_id: int,
        combat_id: ObjectId,
        record_duration: int = ONE_MONTH_SECS
    ) -> int:
        """
        Refreshes or sets the time a channel is recording to *record_duration* from when this method is called.
        Returns the UNIX timestamp when the channel will stop recording.
        """
        recording_until = int(time.time()) + record_duration
        # mark the channel as recorded in cache so we start listening for messages
        self._recorded_channel_cache[channel_id] = (recording_until, str(combat_id))
        # set the channel as recorded in redis so we don't have to do a mongo roundtrip to check
        await self.bot.rdb.set(
            f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id",
            str(combat_id),
            ex=record_duration
        )
        return recording_until

    async def _record_event(self, combat_id: str, event: RecordedEvent):
        """Saves an event to the recording for the given combat ID."""
        await self.bot.mdb.nlp_recordings.update_one(
            {"combat_id": combat_id},
            {"$push": {"events": event.dict()}}
        )

    async def _record_events(self, combat_id: str, events: Iterable[RecordedEvent]):
        """Saves many events to the recording for the given combat ID."""
        await self.bot.mdb.nlp_recordings.update_one(
            {"combat_id": combat_id},
            {"$push": {"events": {"$each": [event.dict() for event in events]}}}
        )
