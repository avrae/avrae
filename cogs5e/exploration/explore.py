import asyncio
import logging
import math
import discord

from typing import List, Any, TYPE_CHECKING
import cachetools
from cogs5e.models.errors import NoCharacter
from utils.functions import search_and_select
from .encounter import Encounter
from .types import ExplorerType
from .explorer import Explorer, PlayerExplorer
from .group import ExplorerGroup
from .errors import *
log = logging.getLogger(__name__)
_CtxT = Any
if TYPE_CHECKING:
    from utils.context import AvraeContext
    _CtxT = AvraeContext


class Explore:
    # cache exploration for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Explore.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Explore state
    # caches based on channel id
    # probably won't encounter any scaling issues, since an exploration will be shard-specific
    _cache = cachetools.TTLCache(maxsize=50, ttl=10)

    def __init__(
        self,
        channel_id: str,
        message_id: int,
        dm_id: str,
        options: dict,
        ctx: _CtxT,
        explorers: List[Explorer] = None,
        round_num: int = 0,
        enctimer: int = 0,
        encthreshold: int = 0,
        chance: int = 100
    ):
        if explorers is None:
            explorers = []
        self._channel = str(channel_id)  # readonly
        self._summary = int(message_id)  # readonly
        self._dm = str(dm_id)
        self._options = options  # readonly (?)
        self._explorers = explorers
        self._round = round_num
        self.ctx = ctx
        self._enctimer = enctimer
        self._encthreshold = encthreshold
        self._chance = chance

    @classmethod
    def new(cls, channel_id, message_id, dm_id, options, ctx):
        return cls(channel_id, message_id, dm_id, options, ctx)

    @classmethod
    async def from_ctx(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        return await cls.from_id(channel_id, ctx)

    @classmethod
    async def from_id(cls, channel_id, ctx):
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = await ctx.bot.mdb.explorations.find_one({"channel": channel_id})
            if raw is None:
                raise ExplorationNotFound()
            # write to cache
            inst = await cls.from_dict(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    async def from_dict(cls, raw, ctx):
        inst = cls(
            raw["channel"],
            raw["summary"],
            raw["dm"],
            raw["options"],
            ctx,
            [],
            raw["round"],
            raw["enctimer"],
            raw["encthreshold"],
            raw["chance"],
        )
        for e in raw["explorers"]:
            inst._explorers.append(await deserialize_explorer(e, ctx, inst))
        return inst

    # sync deser/ser
    @classmethod
    def from_ctx_sync(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = ctx.bot.mdb.explorations.delegate.find_one({"channel": channel_id})
            if raw is None:
                raise ExplorationNotFound
            # write to cache
            inst = cls.from_dict_sync(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx):
        inst = cls(
            raw["channel"],
            raw["summary"],
            raw["dm"],
            raw["options"],
            ctx,
            [],
            raw["round"],
            raw["enctimer"],
            raw["encthreshold"],
            raw["chance"],
        )
        for e in raw["explorers"]:
            inst._explorers.append(deserialize_explorer_sync(e, ctx, inst))
        return inst

    def to_dict(self):
        return {
            "channel": self.channel,
            "summary": self.summary,
            "dm": self.dm,
            "options": self.options,
            "explorers": [c.to_dict() for c in self._explorers],
            "round": self.round_num,
            "enctimer": self.enctimer,
            "encthreshold": self.encthreshold,
            "chance": self._chance
        }

    # members
    @property
    def channel(self):
        return self._channel

    @property
    def summary(self):
        return self._summary

    @summary.setter
    def summary(self, new_summary: int):
        self._summary = new_summary

    @property
    def dm(self):
        return self._dm

    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, value):
        self._options = value

    @property
    def round_num(self):
        return self._round

    @round_num.setter
    def round_num(self, value):
        self._round = value

    @property
    def enctimer(self):
        return self._enctimer

    @enctimer.setter
    def enctimer(self, value):
        self._enctimer = value

    @property
    def encthreshold(self):
        return self._encthreshold

    @encthreshold.setter
    def encthreshold(self, value):
        self._encthreshold = value

    @property
    def chance(self):
        return self._chance

    @chance.setter
    def chance(self, value):
        self._chance = value

    @property
    def _explorer_id_map(self):
        return {c.id: c for c in self.get_explorers(groups=True)}

    # explorers
    @property
    def explorers(self):
        """
        A read-only copy of the explorer list.
        Note that this will not update if the underlying explorer list changes.
        Use this to access an explorer given its index.
        """
        return tuple(self._explorers)

    def get_explorers(self, groups=False):
        """
        Returns a list of all Explorers in an exploration, regardless of if they are in a group.
        Differs from ._explorers since that won't yield explorers in groups.

        :param: groups: Whether to return ExplorerGroup objects in the list.
        :return: A list of all explorers (and optionally groups).
        """
        explorers = []
        for e in self._explorers:
            if not isinstance(e, ExplorerGroup):
                explorers.append(e)
            else:
                explorers.extend(e.get_explorers())
                if groups:
                    explorers.append(e)
        return explorers

    def get_groups(self):
        """
        Returns a list of all ExplorerGroups in an exploration
        :return: A list of all ExplorerGroups
        """
        return [g for g in self._explorers if isinstance(g, ExplorerGroup)]

    def add_explorer(self, explorer):
        """
        Adds an explorer to exploration

        :type: explorer: Explorer
        """
        self._explorers.append(explorer)

    def remove_explorer(self, explorer, ignore_remove_hook=False):
        """
        Removes an explorer from exploration, and fires the remove hook.

        :type: explorer: Explorer
        :param: bool ignore_remove_hook: Whether to ignore the remove hook.
        :rtype: Explorer
        """
        if not ignore_remove_hook:
            explorer.on_remove()
        if not explorer.group:
            self._explorers.remove(explorer)
        else:
            self.get_group(explorer.group).remove_explorer(explorer)
            self._check_empty_groups()
        return self

    def explorer_by_id(self, explorer_id):
        """Gets an explorer by their ID."""
        return self._explorer_id_map.get(explorer_id)

    def get_explorer(self, name, strict=None):
        """Gets an explorer by their name or ID.

        :param: name: The name or id of the explorer.
        :param: strict: Whether explorer name must be a full case-insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The explorer or None.
        """
        if name in self._explorer_id_map:
            return self._explorer_id_map[name]

        explorer = None
        if strict is not False:
            explorer = next((c for c in self.get_explorers() if name.lower() == c.name.lower()), None)
        if not explorer and not strict:
            explorer = next((c for c in self.get_explorers() if name.lower() in c.name.lower()), None)
        return explorer

    def get_group(self, name, strict=None):
        """
        Gets an explorer group by its name or ID.

        :rtype: ExplorerGroup
        :param: name: The name of the explorer group.
        :param: strict: Whether explorer name must be a full case-insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The explorer group.
        """
        if name in self._explorer_id_map and isinstance(self._explorer_id_map[name], ExplorerGroup):
            return self._explorer_id_map[name]

        grp = None
        if strict is not False:
            grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)
        if not grp and not strict:
            grp = next((g for g in self.get_groups() if name.lower() in g.name.lower()), None)

        return grp

    def _check_empty_groups(self):
        """Removes any empty groups in the exploration."""
        for c in self._explorers:
            if isinstance(c, ExplorerGroup) and len(c.get_explorers()) == 0:
                self.remove_explorer(c)

    async def select_explorer(self, name, choice_message=None, select_group=False):
        """
        Opens a prompt for a user to select the explorer they were searching for.

        :param: choice_message: The message to pass to the selector.
        :param: select_group: Whether to allow groups to be selected.
        :rtype: Explorer
        :param: name: The name of the explorer to search for.
        :return: The selected Explorer, or None if the search failed.
        """
        return await search_and_select(
            self.ctx,
            self.get_explorers(select_group),
            name,
            lambda c: c.name,
            message=choice_message,
            selectkey=lambda c: f"{c.name}",
        )

    def set_chance(self, percent):
        if percent > 100:
            self.chance = 100
        elif percent < 1:
            self.chance = 1
        else:
            self.chance = percent

    def set_enc_timer(self, number):
        self.encthreshold = number
        self.enctimer = number

    async def skip_rounds(self, ctx, num_rounds):
        messages = []
        light_end_messages = []
        try:
            enc = await ctx.get_encounter()
        except NoEncounter:
            enc = None
        if self._enctimer != 0 and enc is not None:
            div = num_rounds // self._enctimer
            mod = num_rounds % self._enctimer
            log.warning(mod)
            log.warning(self._enctimer)
            if div == 0:
                self._enctimer -= num_rounds
            else:
                self._enctimer = self._encthreshold - mod
                encounter_list = enc.roll_encounters(div, self.chance)
                log.warning(encounter_list)
                encounter_strs = ["Random encounters rolled:\n"]
                for enc in encounter_list:
                    if enc[1] is None:
                        encounter_strs.append(f"{enc[2]}) {enc[0]}")
                    else:
                        encounter_strs.append(f"{enc[2]}) {enc[1]} {enc[0]}")
                encounter_strs = "\n".join(encounter_strs)
                messages.append(encounter_strs)
        self._round += num_rounds
        for exp in self.get_explorers():
            light_end_messages.append(exp.on_round(num_rounds))
            exp.on_round_end(num_rounds)
        light_end_messages = "\n".join(light_end_messages)
        if light_end_messages == "\n":
            light_end_messages = None
        return light_end_messages, messages

    async def end(self):
        """Ends exploration in a channel."""
        for c in self._explorers:
            c.on_remove()
        await self.ctx.bot.mdb.explorations.delete_one({"channel": self.channel})
        try:
            del Explore._cache[self.channel]
        except KeyError:
            pass

    def get_summary(self, private=False):
        """Returns the generated summary message (pinned) content."""
        explorers = self._explorers
        name = self.options.get("name") if self.options.get("name") else "Exploration"
        duration = self.duration_str(self.round_num)

        out = f"```md\n{name} ({duration})\n"
        out += f"{'=' * (len(out) - 7)}\n"

        explorer_strs = []
        for e in explorers:
            explorer_str = ("# " + e.get_summary(private))
            explorer_strs.append(explorer_str)

        out += "{}```"
        if len(out.format("\n".join(explorer_strs))) > 2000:
            explorer_strs = []
            for e in explorers:
                explorer_str = ("# " + e.get_summary(private, no_notes=True))
                explorer_strs.append(explorer_str)
        return out.format("\n".join(explorer_strs))

    # db
    async def commit(self):
        """Commits the exploration to db."""
        if not self.ctx:
            raise RequiresContext
        for pc in self.get_explorers():
            if isinstance(pc, PlayerExplorer):
                await pc.character.commit(self.ctx)
        await self.ctx.bot.mdb.explorations.update_one(
            {"channel": self.channel}, {"$set": self.to_dict(), "$currentDate": {"lastchanged": True}}, upsert=True
        )

    async def final(self):
        """Commit, update the summary message, and fire any recorder events in parallel."""
        await asyncio.gather(self.commit(), self.update_summary())

    # misc
    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.explorations.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInUse

    @staticmethod
    def duration_str(round_num):
        # build string
        remaining = round_num
        if math.isinf(remaining):
            return ""
        elif remaining > 5_256_000:  # years
            divisor, unit = 5256000, "year"
        elif remaining > 438_000:  # months
            divisor, unit = 438000, "month"
        elif remaining > 100_800:  # weeks
            divisor, unit = 100800, "week"
        elif remaining > 14_400:  # days
            divisor, unit = 14400, "day"
        elif remaining > 600:  # hours
            divisor, unit = 600, "hour"
        elif remaining > 10:  # minutes
            divisor, unit = 10, "minute"
        else:  # rounds
            divisor, unit = 1, "second"

        rounded = round(remaining / divisor, 1) if divisor > 1 else remaining * 6
        return f"[{rounded} {unit}s]"

    async def update_summary(self):
        """Edits the summary message with the latest summary."""
        await self.get_summary_msg().edit(content=self.get_summary())

    def get_channel(self):
        """Gets the Channel object of the exploration."""
        if self.ctx:
            return self.ctx.channel
        else:
            chan = self.ctx.bot.get_channel(int(self.channel))
            if chan:
                return chan
            else:
                raise ExplorationChannelNotFound()

    def get_summary_msg(self):
        """Gets the Message object of the exploration summary."""
        return discord.PartialMessage(channel=self.get_channel(), id=self.summary)

    def __str__(self):
        return f"Exploration in <#{self.channel}>"


async def deserialize_encounter(raw_encounter):
    return Encounter.from_dict(raw_encounter)


async def deserialize_explorer(raw_explorer, ctx, exploration):
    ctype = ExplorerType(raw_explorer["type"])
    if ctype == ExplorerType.GENERIC:
        return Explorer.from_dict(raw_explorer, ctx, exploration)
    elif ctype == ExplorerType.PLAYER:
        try:
            return await PlayerExplorer.from_dict(raw_explorer, ctx, exploration)
        except NoCharacter:
            # if the character was deleted, make the best effort to restore what we know
            # note: PlayerExplorer.from_dict mutates raw_explorer, so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Explorer(ctx, exploration, **raw_explorer)
    elif ctype == ExplorerType.GROUP:
        return await ExplorerGroup.from_dict(raw_explorer, ctx, exploration)
    else:
        raise ExplorationException(f"Unknown explorer type: {raw_explorer['type']}")


def deserialize_explorer_sync(raw_explorer, ctx, exploration):
    ctype = ExplorerType(raw_explorer["type"])
    if ctype == ExplorerType.GENERIC:
        return Explorer.from_dict(raw_explorer, ctx, exploration)
    elif ctype == ExplorerType.PLAYER:
        try:
            return PlayerExplorer.from_dict_sync(raw_explorer, ctx, exploration)
        except NoCharacter:
            # if the character was deleted, make the best effort to restore what we know
            # note: PlayerExplorer.from_dict mutates raw_explorer, so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Explorer(ctx, exploration, **raw_explorer)
    elif ctype == ExplorerType.GROUP:
        return ExplorerGroup.from_dict_sync(raw_explorer, ctx, exploration)
    else:
        raise ExplorationException(f"Unknown explorer type: {raw_explorer['type']}")
