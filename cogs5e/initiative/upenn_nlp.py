"""
This module contains the logic for recording messages and other events for the UPenn NLP project.

The recording is primarily based on the `cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id` key in
Redis - if the key is present in for a given guild channel, that channel is considered recorded.

This key is set when a combat starts and expired 2 minutes after a combat ends in a channel that has opted in to NLP
recording.
"""

import datetime
import logging
import re
import time
from typing import Any, List, MutableMapping, Optional, Sequence, TYPE_CHECKING, Tuple, Union

import botocore.exceptions
import cachetools
import disnake
from aiobotocore.session import get_session
from pydantic import BaseModel, Field

from utils import config
from .utils import nlp_feature_flag_enabled

if TYPE_CHECKING:
    from cogs5e.models.automation import Automation, AutomationResult
    from cogs5e.models.sheet.statblock import StatBlock
    from utils.context import AvraeContext
    from .combat import Combat

ONE_MONTH_SECS = 2592000

log = logging.getLogger(__name__)


# ==== models ====
class RecordedEvent(BaseModel):
    """Base class for all recorded events"""

    combat_id: str
    event_type: str
    timestamp: float = Field(default_factory=time.time)


class RecordedMessage(RecordedEvent):
    """
    A message was sent in a recorded channel.

    Causality: This is the first event in an interaction context.
    """

    event_type = "message"
    message_id: int
    author_id: str
    author_name: str
    author_bot: Optional[bool]
    created_at: float
    content: str
    embeds: List[dict]  # call disnake.Embed.to_dict() to generate these
    components: List[dict]  # call disnake.Component.to_dict() to generate these
    referenced_message_id: Optional[int]  # if the message was a reply (or pin add/crosspost), what does it reference?

    @classmethod
    def from_message(cls, combat_id: str, message: disnake.Message):
        return cls(
            combat_id=combat_id,
            message_id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            author_bot=message.author.bot,
            created_at=message.created_at.timestamp(),
            content=message.content,
            embeds=[embed.to_dict() for embed in message.embeds],
            components=[component.to_dict() for component in message.components],
            referenced_message_id=message.reference.message_id if message.reference is not None else None,
        )


class RecordedAliasResolution(RecordedEvent):
    """
    An alias was evaluated.

    Causality:
    - Must occur after a RecordedMessage with the same ``message_id``
    - If a valid command, must occur before a RecordedCommandInvocation with the same ``message_id``
    """

    event_type = "alias_resolution"
    message_id: int
    alias_name: str
    alias_body: str
    content_before: str
    content_after: str
    prefix: str


class RecordedSnippetResolution(RecordedEvent):
    """
    A snippet was evaluated. May occur multiple times per command execution.

    Causality:
    - Must occur after a RecordedMessage with the same ``message_id``
    - If in an alias, must occur after a RecordedAliasResolution with the same ``message_id``
    - If a valid command, must occur before a RecordedCommandInvocation with the same ``message_id``
    """

    event_type = "snippet_resolution"
    message_id: int
    snippet_name: str
    snippet_body: str
    content_after: str


class RecordedCommandInvocation(RecordedMessage):
    """
    A command successfully completed in a recorded channel.

    Note: ``content`` may not match the content in the corresponding RecordedMessage as the recorded content here
    is the resolved content after aliases.

    Causality: A RecordedCommandInvocation will always happen after a RecordedMessage with the same ``message_id``.
    If an alias or snippet was used (after v4.1.0), it must happen after a RecordedAliasResolution and/or
    zero or more RecordedSnippetResolutions with the same ``message_id``.
    """

    event_type = "command"
    prefix: str
    command_name: str
    called_by_alias: bool
    caster: Optional[dict]  # this is a StatBlock, typed as dict since StatBlock does not inherit from BaseModel
    targets: Optional[List[dict]]

    @classmethod
    def from_ctx(cls, combat_id: str, ctx: "AvraeContext"):
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
            combat_id=combat_id,
            message_id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            author_bot=message.author.bot,
            created_at=message.created_at.timestamp(),
            content=message.content,
            embeds=[embed.to_dict() for embed in message.embeds],
            components=[component.to_dict() for component in message.components],
            referenced_message_id=message.reference.message_id if message.reference is not None else None,
            prefix=ctx.prefix,
            command_name=ctx.command.qualified_name,
            called_by_alias=ctx.nlp_is_alias,
            caster=caster,
            targets=targets,
        )


class RecordedButtonInteraction(RecordedEvent):
    """
    A button was clicked in a recorded channel.

    Causality: This is the first event in an interaction context.
    """

    event_type = "button_press"
    interaction_id: int
    interaction_message_id: int
    author_id: str
    author_name: str
    button_id: str
    button_label: str

    @classmethod
    def from_interaction(cls, combat_id: str, interaction: disnake.MessageInteraction):
        return cls(
            combat_id=combat_id,
            interaction_id=interaction.id,
            interaction_message_id=interaction.message.id,
            author_id=interaction.author.id,
            author_name=interaction.author.display_name,
            button_id=interaction.data.custom_id,
            button_label=interaction.component.label,
        )


class RecordedAutomation(RecordedEvent):
    """
    An Automation document finished executing in a recorded channel.

    Causality:
    - Must occur after a RecordedMessage or RecordedButtonInteraction with the same ``message_id`` or ``interaction_id``
    - If message, must occur before RecordedCommandInvocation with the same ``message_id``
    - Must occur before a RecordedCombatState which *may* have the same ``interaction_id``
    """

    event_type = "automation_run"
    interaction_id: int
    automation: Any
    automation_result: Any
    caster: Optional[dict]  # this is a StatBlock, typed as dict since StatBlock does not inherit from BaseModel
    targets: Optional[List[dict]]

    @classmethod
    def new(
        cls,
        ctx: Union["AvraeContext", disnake.Interaction],
        combat: "Combat",
        automation: "Automation",
        automation_result: "AutomationResult",
        caster: "StatBlock",
        targets: List[Union["StatBlock", str]],
    ):
        return cls(
            combat_id=combat.nlp_record_session_id,
            interaction_id=interaction_id(ctx),
            automation=automation.to_dict(),
            automation_result=automation_result.to_dict(),
            caster=caster.to_dict(),
            targets=[t.to_dict() if hasattr(t, "to_dict") else t for t in targets],
        )


class RecordedCombatState(RecordedEvent):
    """
    The recorded combat has been committed.

    Causality:
    - Must occur after a RecordedMessage or RecordedButtonInteraction which *may* have the same ``message_id`` or
      ``interaction_id``
    - Must occur before RecordedCommandInvocation which *may* have the same ``message_id`` or ``interaction_id``
    """

    event_type = "combat_state_update"
    # due to caching this might not actually be the interaction this state update is tied to
    probable_interaction_id: int
    data: Any
    human_readable: str

    @classmethod
    def from_combat(cls, combat: "Combat", ctx: Union["AvraeContext", disnake.Interaction]):
        return cls(
            combat_id=combat.nlp_record_session_id,
            probable_interaction_id=interaction_id(ctx),
            data=combat.to_dict(),
            human_readable=combat.get_summary(private=True),
        )


# ==== recorder ====
class NLPRecorder:
    # cache: channel id -> (when channels are recorded until, combat id); (0, None) if not recorded
    _recorded_channel_cache: MutableMapping[int, Tuple[int, Optional[str]]] = cachetools.TTLCache(
        maxsize=100000, ttl=120
    )

    def __init__(self, bot):
        self.bot = bot
        self._kinesis_firehose = None

    async def initialize(self):
        if config.NLP_KINESIS_DELIVERY_STREAM is None:
            log.warning("'NLP_KINESIS_DELIVERY_STREAM' env var is not set - nlp module will not record any events")
            return
        boto_session = get_session()
        self._kinesis_firehose = await boto_session.create_client(
            "firehose", region_name=config.DYNAMO_REGION
        ).__aenter__()

    def close(self):
        if self._kinesis_firehose is not None:
            self.bot.loop.create_task(self._kinesis_firehose.__aexit__(None, None, None))

    def register_listeners(self):
        self.bot.add_listener(self.on_message)
        self.bot.add_listener(self.on_command_completion)
        self.bot.add_listener(self.on_button_click)

    def deregister_listeners(self):
        self.bot.remove_listener(self.on_message)
        self.bot.remove_listener(self.on_command_completion)
        self.bot.remove_listener(self.on_button_click)

    # ==== listeners ====
    async def on_message(self, message: disnake.Message):
        if message.guild is None:
            return
        await self.on_guild_message(message)

    async def on_command_completion(self, ctx: "AvraeContext"):
        if ctx.guild is None:
            return
        await self.on_guild_command(ctx)

    async def on_button_click(self, interaction: disnake.MessageInteraction):
        if interaction.guild_id is None:
            return
        await self.on_guild_button_click(interaction)

    # ==== main methods ====
    async def on_combat_start(self, combat: "Combat"):
        """
        Called with the just-started combat instance after a combat is started in a guild with NLP recording enabled.
        """
        # enable recording in the combat's channel
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=combat.channel_id,
            combat_id=combat.nlp_record_session_id,
            insert_if_not_exist=True,
        )
        # record cached messages less than X minutes old for pre-combat context
        await self._record_events(
            [
                RecordedMessage.from_message(combat_id=combat.nlp_record_session_id, message=message)
                for message in self.bot.cached_messages
                if (
                    message.channel.id == combat.channel_id
                    and message.created_at > disnake.utils.utcnow() - datetime.timedelta(minutes=15)
                )
            ][-25:]
        )
        # record combat start meta event
        await self._record_event(RecordedEvent(combat_id=combat.nlp_record_session_id, event_type="combat_start"))

    async def on_guild_message(self, message: disnake.Message):
        """
        Called on every message in a guild channel. If the guild has not opted in to NLP recording, does nothing.
        """
        is_recording, combat_id = await self._recording_info(message.guild.id, message.channel.id)
        if is_recording:
            await self._record_event(RecordedMessage.from_message(combat_id=combat_id, message=message))

    async def on_guild_command(self, ctx: "AvraeContext"):
        """
        Called after each successful invocation of a command in a guild. If the guild has not opted in to
        NLP recording, does nothing.
        """
        is_recording, combat_id = await self._recording_info(ctx.guild.id, ctx.channel.id)
        if is_recording:
            await self._record_event(RecordedCommandInvocation.from_ctx(combat_id=combat_id, ctx=ctx))

    async def on_guild_button_click(self, interaction: disnake.MessageInteraction):
        """
        Called when a button is clicked in a guild. If the guild has not opted in to NLP recording, does nothing.
        """
        is_recording, combat_id = await self._recording_info(interaction.guild_id, interaction.channel_id)
        if is_recording:
            await self._record_event(
                RecordedButtonInteraction.from_interaction(combat_id=combat_id, interaction=interaction)
            )

    async def on_automation_run(
        self,
        ctx: Union["AvraeContext", disnake.Interaction],
        combat: "Combat",
        automation: "Automation",
        automation_result: "AutomationResult",
        caster: "StatBlock",
        targets: List[Union["StatBlock", str]],
    ):
        """Called each time an automation run completes in a recorded combat."""
        is_recording, combat_id = await self._recording_info(combat.ctx.guild.id, combat.ctx.channel.id)
        if is_recording:
            await self._record_event(
                RecordedAutomation.new(ctx, combat, automation, automation_result, caster, targets)
            )

    async def on_combat_commit(self, combat: "Combat", ctx: Union["AvraeContext", disnake.Interaction]):
        """
        Called each time a combat that is being recorded is committed.
        """
        # bump the recording time to equal the combat's expiration time
        await self._update_channel_recording_until(
            guild_id=ctx.guild.id, channel_id=combat.channel_id, combat_id=combat.nlp_record_session_id
        )
        # record a snapshot of the combat's human-readable and machine-readable state
        await self._record_event(RecordedCombatState.from_combat(combat, ctx))

    async def on_combat_end(self, combat: "Combat"):
        """
        Called each time a combat that is being recorded ends.
        """
        # set the channel recording expiration to 2 minutes to record a few messages after combat ends
        await self._update_channel_recording_until(
            guild_id=combat.ctx.guild.id,
            channel_id=combat.channel_id,
            combat_id=combat.nlp_record_session_id,
            record_duration=120,
        )
        # record a combat end meta marker
        await self._record_event(RecordedEvent(combat_id=combat.nlp_record_session_id, event_type="combat_end"))

    async def on_alias_resolve(
        self,
        ctx: "AvraeContext",
        alias_name: str,
        alias_body: str,
        content_before: str,
        content_after: str,
        prefix: str,
    ):
        """Called each time an alias is resolved."""
        if ctx.guild is None:
            return
        is_recording, combat_id = await self._recording_info(ctx.guild.id, ctx.channel.id)
        if is_recording:
            await self._record_event(
                RecordedAliasResolution(
                    combat_id=combat_id,
                    message_id=ctx.message.id,
                    alias_name=alias_name,
                    alias_body=alias_body,
                    content_before=content_before,
                    content_after=content_after,
                    prefix=prefix,
                )
            )

    async def on_snippet_resolve(self, ctx: "AvraeContext", snippet_name: str, snippet_body: str, content_after: str):
        """Called each time a snippet is resolved."""
        if ctx.guild is None:
            return
        is_recording, combat_id = await self._recording_info(ctx.guild.id, ctx.channel.id)
        if is_recording:
            await self._record_event(
                RecordedSnippetResolution(
                    combat_id=combat_id,
                    message_id=ctx.message.id,
                    snippet_name=snippet_name,
                    snippet_body=snippet_body,
                    content_after=content_after,
                )
            )

    # ==== management ====
    async def get_recording_channels(self, guild_id: int):
        """
        Returns a list of channel IDs in the given guild that have an active recording.
        """
        channels = []
        async for key in self.bot.rdb.iscan(match=f"cog.initiative.upenn_nlp.{guild_id}.*"):
            channel_id_match = re.match(r"cog\.initiative\.upenn_nlp\.(\d+)\.(\d+)\.recorded_combat_id", key)
            if channel_id_match is None:
                continue
            channels.append(int(channel_id_match.group(2)))
        return channels

    async def stop_all_recordings(self, guild: disnake.Guild):
        """
        Immediately stop all message recording in a given guild. Returns number of channels recording was stopped in.
        """
        guild_id = guild.id

        # delete all recording keys
        keys_to_delete = {key async for key in self.bot.rdb.iscan(match=f"cog.initiative.upenn_nlp.{guild_id}.*")}
        if keys_to_delete:
            await self.bot.rdb.delete(*keys_to_delete)
        log.debug(f"deleted {len(keys_to_delete)} recording keys for {guild_id=}")

        # remove all channel entries from cache
        for channel in guild.channels:
            self._recorded_channel_cache.pop(channel.id, None)

        return len(keys_to_delete)

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
            # log.debug(f"found recording info for {channel_id} in memory cache")
        except KeyError:
            # get from redis
            combat_id = await self.bot.rdb.get(f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id")
            # and write to memory cache
            if combat_id is None:
                channel_recording_until = 0
            else:
                channel_recording_ttl = await self.bot.rdb.ttl(
                    f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id"
                )
                channel_recording_until = int(now + channel_recording_ttl)
                # log.debug(f"found recording info for {channel_id} in redis with ttl {channel_recording_ttl}")
            self._recorded_channel_cache[channel_id] = (channel_recording_until, combat_id)

        # log.debug(f"{channel_id}: {channel_recording_until=}, {combat_id=}")

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
        record_duration: int = ONE_MONTH_SECS,
        insert_if_not_exist: bool = False,
    ) -> int:
        """
        Refreshes or sets the time a channel is recording to *record_duration* from when this method is called.
        Returns the UNIX timestamp when the channel will stop recording.
        """
        now = time.time()
        recording_until = int(now) + record_duration
        # mark the channel as recorded in cache so we start listening for messages
        if insert_if_not_exist or (
            (cache_entry := self._recorded_channel_cache.get(channel_id)) is not None and cache_entry[0] >= now
        ):
            self._recorded_channel_cache[channel_id] = (recording_until, combat_id)
            log.debug(
                f"{channel_id}: recording_until updated in cache to {recording_until!r} "
                f"(cache size: {len(self._recorded_channel_cache)})"
            )
        # set the channel as recorded in redis so we don't have to do a mongo roundtrip to check
        await self.bot.rdb.set(
            f"cog.initiative.upenn_nlp.{guild_id}.{channel_id}.recorded_combat_id",
            combat_id,
            ex=record_duration,
            xx=not insert_if_not_exist,
        )
        return recording_until

    async def _record_event(self, event: RecordedEvent):
        """Saves an event to the recording for the given combat ID."""
        if self._kinesis_firehose is None:
            log.warning("skipping event because kinesis firehose is not initialized")
            return
        if not await nlp_feature_flag_enabled(self.bot):
            log.debug("NLP feature flag is disabled, dropping event")
            return

        log.debug(f"saving 1 event to {event.combat_id=} of type {event.event_type!r}")
        if config.TESTING:
            # this is behind this if because .json() is (relatively) slow, even if the output is discarded
            # so only call it on local dev
            log.debug(event.json(indent=2))

        try:
            response = await self._kinesis_firehose.put_record(
                DeliveryStreamName=config.NLP_KINESIS_DELIVERY_STREAM, Record={"Data": event.json().encode()}
            )
        except botocore.exceptions.ClientError:
            log.exception(f"Failed to record NLP event to {event.combat_id=} of type {event.event_type!r}")
        else:
            log.debug(str(response))

    async def _record_events(self, events: Sequence[RecordedEvent]):
        """Saves many events to the recording for the given combat ID."""
        if not events:
            return
        if self._kinesis_firehose is None:
            log.warning(f"skipping {len(events)} events because kinesis firehose is not initialized")
            return
        if not await nlp_feature_flag_enabled(self.bot):
            log.debug("NLP feature flag is disabled, dropping event")
            return

        log.debug(f"saving {len(events)} events to kinesis")
        try:
            response = await self._kinesis_firehose.put_record_batch(
                DeliveryStreamName=config.NLP_KINESIS_DELIVERY_STREAM,
                Records=[{"Data": event.json().encode()} for event in events],
            )
        except botocore.exceptions.ClientError:
            log.exception(f"Failed to record {len(events)} NLP events")
        else:
            log.debug(str(response))
            if failed_count := response.get("FailedPutCount"):
                log.error(f"Failed to record {failed_count} NLP events; response={response!r}")


# ==== helpers ====
def interaction_id(ctx: Union["AvraeContext", disnake.Interaction]):
    """Helper to retrieve the interaction ID from a context or interaction."""
    if isinstance(ctx, disnake.Interaction):
        return ctx.id
    return ctx.message.id
