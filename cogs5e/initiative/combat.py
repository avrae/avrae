import asyncio
from functools import cached_property
from typing import List, Literal, Optional, TYPE_CHECKING, Tuple, Union, overload

import cachetools
import disnake
from d20 import roll
from pydantic import BaseModel

from cogs5e.models.errors import NoCharacter
from utils.functions import search_and_select
from .combatant import Combatant, MonsterCombatant, PlayerCombatant
from .errors import *
from .group import CombatantGroup
from .types import CombatantType

COMBAT_TTL = 60 * 60 * 24 * 7  # 1 week TTL

# ==== typing ====
if TYPE_CHECKING:
    import cogs5e.initiative
    from .upenn_nlp import NLPRecorder
    from utils.context import AvraeContext


# ==== code ====
class CombatOptions(BaseModel):
    dynamic: bool = False
    turnnotif: bool = False
    deathdelete: bool = True
    name: Optional[str] = None


class Combat:
    # we cache up to 500 combats in memory for a short period
    # this makes sure that multiple calls to Combat.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Combat state
    # caches based on channel id
    # probably won't encounter any scaling issues, since a combat will be shard-specific
    _cache: cachetools.TTLCache[str, "Combat"] = cachetools.TTLCache(maxsize=500, ttl=10)

    def __init__(
        self,
        channel_id: str,
        message_id: int,
        dm_id: int,
        options: CombatOptions,
        ctx: Union["AvraeContext", "disnake.Interaction"],
        combatants: List[Combatant] = None,
        round_num: int = 0,
        turn_num: int = 0,
        current_index: Optional[int] = None,
        metadata: dict = None,
        nlp_record_session_id: str = None,
    ):
        if combatants is None:
            combatants = []
        if metadata is None:
            metadata = {}
        self._channel = str(channel_id)  # readonly
        self.summary_message_id = int(message_id)  # readonly
        self.dm_id = int(dm_id)
        self.options = options
        self._combatants = combatants
        self.round_num = round_num
        self._turn = turn_num
        self._current_index = current_index
        self.ctx = ctx  # try to avoid using this whereever possible - this is *not* always the current ctx
        self.metadata = metadata
        self.nlp_record_session_id = nlp_record_session_id

    @classmethod
    def new(
        cls,
        channel_id: str,
        message_id: int,
        dm_id: int,
        options: CombatOptions,
        ctx: Union["AvraeContext", "disnake.Interaction"],
    ):
        return cls(channel_id, message_id, dm_id, options, ctx)

    # async deser
    @classmethod
    async def from_ctx(cls, ctx):  # cached
        return await cls.from_id(str(ctx.channel.id), ctx)

    @classmethod
    async def from_id(cls, channel_id: str, ctx):
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = await ctx.bot.mdb.combats.find_one({"channel": channel_id})
            if raw is None:
                raise CombatNotFound()
            # write to cache
            inst = await cls.from_dict(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    async def from_dict(cls, raw, ctx):
        # noinspection DuplicatedCode
        inst = cls(
            channel_id=raw["channel"],
            message_id=raw["summary"],
            dm_id=raw["dm"],
            options=CombatOptions.parse_obj(raw["options"]),
            ctx=ctx,
            combatants=[],
            round_num=raw["round"],
            turn_num=raw["turn"],
            current_index=raw["current"],
            metadata=raw.get("metadata"),
            nlp_record_session_id=raw.get("nlp_record_session_id"),
        )
        for c in raw["combatants"]:
            inst._combatants.append(await deserialize_combatant(c, ctx, inst))
        return inst

    # sync deser/ser
    @classmethod
    def from_ctx_sync(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = ctx.bot.mdb.combats.delegate.find_one({"channel": channel_id})
            if raw is None:
                raise CombatNotFound
            # write to cache
            inst = cls.from_dict_sync(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx):
        # noinspection DuplicatedCode
        inst = cls(
            channel_id=raw["channel"],
            message_id=raw["summary"],
            dm_id=raw["dm"],
            options=CombatOptions.parse_obj(raw["options"]),
            ctx=ctx,
            combatants=[],
            round_num=raw["round"],
            turn_num=raw["turn"],
            current_index=raw["current"],
            metadata=raw.get("metadata"),
            nlp_record_session_id=raw.get("nlp_record_session_id"),
        )
        for c in raw["combatants"]:
            inst._combatants.append(deserialize_combatant_sync(c, ctx, inst))
        return inst

    def to_dict(self):
        return {
            "channel": self._channel,
            "summary": self.summary_message_id,
            "dm": self.dm_id,
            "options": self.options.dict(exclude_unset=True),
            "combatants": [c.to_dict() for c in self._combatants],
            "turn": self.turn_num,
            "round": self.round_num,
            "current": self._current_index,
            "metadata": self.metadata,
            "nlp_record_session_id": self.nlp_record_session_id,
        }

    # members
    @property
    def channel_id(self) -> int:
        return int(self._channel)

    @property  # private write
    def turn_num(self) -> int:
        return self._turn

    @property  # private write
    def index(self) -> Optional[int]:
        return self._current_index

    @property
    def _combatant_id_map(self):
        return {c.id: c for c in self.get_combatants(groups=True)}

    # combatants
    @property
    def combatants(self):
        """
        A read-only copy of the combatant list.
        Note that this will not update if the underlying combatant list changes.
        Use this to access a combatant given its index.
        """
        return tuple(self._combatants)

    @property
    def current_combatant(self) -> Optional[Combatant]:
        """
        The combatant whose turn it currently is.
        """
        if self.index is None:
            return None
        return self._combatants[self.index]

    @property
    def next_combatant(self) -> Optional[Combatant]:
        """
        The combatant whose turn it will be when advance_turn() is called. Returns None iff the combatant list is empty.
        """
        if len(self._combatants) == 0:
            return None
        if self.index is None:
            index = 0
        elif self.index + 1 >= len(self._combatants):
            index = 0
        else:
            index = self.index + 1
        return self._combatants[index]

    @cached_property
    def nlp_recorder(self) -> Optional["NLPRecorder"]:
        if self.nlp_record_session_id is None or self.ctx is None:
            return None
        combat_cog = self.ctx.bot.get_cog("InitTracker")  # type: Optional[cogs5e.initiative.InitTracker]
        if combat_cog is None:
            return None
        return combat_cog.nlp

    def get_combatants(self, groups=False) -> List[Combatant]:
        """
        Returns a list of all Combatants in a combat, regardless of if they are in a group.
        Differs from ._combatants since that won't yield combatants in groups.

        :param groups: Whether to return CombatantGroup objects in the list.
        :return: A list of all combatants (and optionally groups).
        """
        combatants = []
        for c in self._combatants:
            if not isinstance(c, CombatantGroup):
                combatants.append(c)
            else:
                combatants.extend(c.get_combatants())
                if groups:
                    combatants.append(c)
        return combatants

    def get_groups(self) -> List[CombatantGroup]:
        """
        Returns a list of all CombatantGroups in a combat
        :return: A list of all CombatantGroups
        """
        return [g for g in self._combatants if isinstance(g, CombatantGroup)]

    def add_combatant(self, combatant: Combatant):
        """
        Adds a combatant to combat, and sorts the combatant list by init.
        """
        self._combatants.append(combatant)
        self.sort_combatants()

    def remove_combatant(self, combatant: Combatant, ignore_remove_hook=False):
        """
        Removes a combatant from combat, sorts the combatant list by init (updates index), and fires the remove hook.
        """
        if not ignore_remove_hook:
            combatant.on_remove()
        if not combatant.group:
            self._combatants.remove(combatant)
            self.sort_combatants()
        else:
            self.get_group(combatant.group).remove_combatant(combatant)
            self._check_empty_groups()

    def sort_combatants(self):
        """
        Sorts the combatant list by place in init and updates combatants' indices.
        """
        if not self._combatants:
            self._current_index = None
            self._turn = 0
            return

        current = None
        if self._current_index is not None:
            current = next((c for c in self._combatants if c.index == self._current_index), None)

        self._combatants = sorted(self._combatants, key=lambda k: (k.init, int(k.init_skill)), reverse=True)
        for n, c in enumerate(self._combatants):
            c.index = n

        if current is not None:
            self._current_index = current.index
            self._turn = current.init
        else:
            self._current_index = None

    def combatant_by_id(self, combatant_id: str) -> Optional[Combatant]:
        """Gets a combatant by their ID."""
        return self._combatant_id_map.get(combatant_id)

    def get_combatant(self, name: str, strict=None) -> Optional[Combatant]:
        """Gets a combatant by their name or ID.

        :param name: The name or id of the combatant.
        :param strict: Whether combatant name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The combatant or None.
        """
        if name in self._combatant_id_map:
            return self._combatant_id_map[name]

        combatant = None
        if strict is not False:
            combatant = next((c for c in self.get_combatants() if name.lower() == c.name.lower()), None)
        if not combatant and not strict:
            combatant = next((c for c in self.get_combatants() if name.lower() in c.name.lower()), None)
        return combatant

    def get_group(
        self, name: str, create: Optional[int] = None, strict: Optional[bool] = None
    ) -> Optional[CombatantGroup]:
        """
        Gets a combatant group by its name or ID.

        :rtype: CombatantGroup
        :param name: The name of the combatant group.
        :param create: The initiative to create a group at if a group is not found.
        :param strict: Whether combatant name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The combatant group.
        """
        if name in self._combatant_id_map and isinstance(self._combatant_id_map[name], CombatantGroup):
            return self._combatant_id_map[name]

        grp = None
        if strict is not False:
            grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)
        if not grp and not strict:
            grp = next((g for g in self.get_groups() if name.lower() in g.name.lower()), None)

        if grp is None and create is not None:
            grp = CombatantGroup.new(self, name, init=create, ctx=self.ctx)
            self.add_combatant(grp)

        return grp

    def _check_empty_groups(self):
        """Removes any empty groups in the combat."""
        removed = False
        for c in self._combatants:
            if isinstance(c, CombatantGroup) and len(c.get_combatants()) == 0:
                self.remove_combatant(c)
                removed = True
        if removed:
            self.sort_combatants()

    def reroll_dynamic(self) -> str:
        """
        Rerolls all combatant initiatives. Returns a string representing the new init order.
        """
        rolls = {}
        for c in self._combatants:
            init_roll = roll(c.init_skill.d20())
            c.init = init_roll.total
            rolls[c] = init_roll
        self.sort_combatants()

        # reset current turn
        self.end_round()

        order = []
        for combatant, init_roll in sorted(
            rolls.items(), key=lambda r: (r[1].total, int(r[0].init_skill)), reverse=True
        ):
            order.append(f"{init_roll.result}: {combatant.name}")

        order = "\n".join(order)

        return order

    def end_round(self):
        """
        Moves initiative to just before the next round (no active combatant or group).
        """
        self._turn = 0
        self._current_index = None

    @overload
    async def select_combatant(
        self, ctx, name: str, choice_message: Optional[str] = None, select_group: Literal[True] = False
    ) -> Optional[Combatant | CombatantGroup]: ...

    async def select_combatant(
        self, ctx, name: str, choice_message: Optional[str] = None, select_group: Literal[False] = False
    ) -> Optional[Combatant]:
        """
        Opens a prompt for a user to select the combatant they were searching for.

        :param choice_message: The message to pass to the selector.
        :param select_group: Whether to allow groups to be selected.
        :rtype: Combatant
        :param name: The name of the combatant to search for.
        :return: The selected Combatant, or None if the search failed.
        """
        return await search_and_select(
            ctx,
            self.get_combatants(select_group),
            name,
            lambda c: c.name,
            message=choice_message,
            selectkey=lambda c: f"{c.name} {c.hp_str()}",
        )

    def advance_turn(self) -> Tuple[bool, List[str]]:
        """
        Advances the turn. If any caveats should be noted, returns them in messages.

        :returns: A tuple (changed_round, list_of_messages).
        """
        if len(self._combatants) == 0:
            raise NoCombatants

        messages = []

        changed_round = False
        if self.index is None:  # new round, no dynamic reroll
            self._current_index = 0
            self.round_num += 1
        elif self.index + 1 >= len(self._combatants):  # new round
            if self.options.dynamic:
                messages.append(f"New initiatives:\n{self.reroll_dynamic()}")
            self._current_index = 0
            self.round_num += 1
            changed_round = True
        else:
            self._current_index += 1

        self._turn = self.current_combatant.init
        for combatant in self._combatants:
            combatant.on_turn()
        return changed_round, messages

    def rewind_turn(self):
        if len(self._combatants) == 0:
            raise NoCombatants

        for combatant in self._combatants:
            combatant.on_turn(num_turns=-1)

        if self.index is None:  # start of combat
            self._current_index = len(self._combatants) - 1
        elif self.index == 0:  # new round
            self._current_index = len(self._combatants) - 1
            self.round_num -= 1
        else:
            self._current_index -= 1

        self._turn = self.current_combatant.init

    def goto_turn(self, init_num: int | Combatant, is_combatant=False):
        if len(self._combatants) == 0:
            raise NoCombatants

        for combatant in self._combatants:
            combatant.on_turn(num_turns=0)

        if is_combatant:
            if init_num.group:
                init_num = self.get_group(init_num.group)
            self._current_index = init_num.index
        else:
            target = next((c for c in self._combatants if c.init <= init_num), None)
            if target:
                self._current_index = target.index
            else:
                self._current_index = 0

        self._turn = self.current_combatant.init

    def skip_rounds(self, num_rounds: int):
        messages = []

        self.round_num += num_rounds
        for com in self.get_combatants():
            com.on_turn(num_rounds)
        if self.options.dynamic:
            messages.append(f"New initiatives:\n{self.reroll_dynamic()}")

        return messages

    async def end(self):
        """Ends combat in a channel."""
        for c in self._combatants:
            c.on_remove()
        await self.ctx.bot.mdb.combats.delete_one({"channel": self._channel})
        try:
            del Combat._cache[self._channel]
        except KeyError:
            pass

    # stringification
    def get_turn_str(self, status=True, **kwargs) -> Optional[str]:
        """
        Gets the string representing the current turn, and all combatants on it.

        If *status* is false, only displays the combatant's name and no status codeblock.

        Any other kwargs are passed to Combatant.get_status().
        """
        combatant = self.current_combatant
        if combatant is None:
            return None
        out = self.get_turn_str_for(combatant, status, **kwargs)
        if self.options.turnnotif:
            next_combatant = self.next_combatant
            out += f"**Next up**: {next_combatant.name} ({next_combatant.controller_mention()})\n"
        return out

    def get_turn_str_for(self, combatant: Combatant, status=True, **kwargs) -> str:
        """Like get_turn_str, but for a specific combatant."""
        if isinstance(combatant, CombatantGroup):
            combatants = combatant.get_combatants()
            combatant_statuses = "\n".join(co.get_status(**kwargs) for co in combatants)
            mentions = ", ".join({co.controller_mention() for co in combatants})
            out = f"**Initiative {self.turn_num} (round {self.round_num})**: {combatant.name} ({mentions})\n"
        else:
            combatant_statuses = combatant.get_status(**kwargs)
            out = (
                f"**Initiative {self.turn_num} (round {self.round_num})**: {combatant.name} "
                f"({combatant.controller_mention()})\n"
            )

        if status:
            out += f"```md\n{combatant_statuses}```"

        return out

    def get_turn_str_mentions(self) -> disnake.AllowedMentions:
        """Gets the :class:`disnake.AllowedMentions` for the users mentioned in the current turn str."""
        if self.current_combatant is None:
            return disnake.AllowedMentions.none()
        mentions = self.get_turn_str_mentions_for(self.current_combatant)
        if self.options.turnnotif and self.next_combatant is not None:
            next_combatant = self.get_turn_str_mentions_for(self.next_combatant)
            merged_users = set(next_combatant.users).union(mentions.users)
            mentions = mentions.merge(disnake.AllowedMentions(users=list(merged_users)))
        return mentions

    def get_turn_str_mentions_for(self, combatant) -> disnake.AllowedMentions:
        """Like get_turn_str_mentions, but for a specific combatant."""
        if isinstance(combatant, CombatantGroup):
            # noinspection PyUnresolvedReferences
            user_ids = {disnake.Object(id=comb.controller_id) for comb in combatant.get_combatants()}
        else:
            user_ids = {disnake.Object(id=combatant.controller_id)}
        return disnake.AllowedMentions(users=list(user_ids))

    def get_summary(self, private=False) -> str:
        """Returns the generated summary message (pinned) content."""
        combatants = self._combatants
        name = self.options.name or "Current initiative"

        out = f"```md\n{name}: {self.turn_num} (round {self.round_num})\n"
        out += f"{'=' * (len(out) - 7)}\n"

        combatant_strs = []
        for c in combatants:
            combatant_str = ("# " if self.index == c.index else "  ") + c.get_summary(private)
            combatant_strs.append(combatant_str)

        out += "{}```"
        if len(out.format("\n".join(combatant_strs))) > 2000:
            combatant_strs = []
            for c in combatants:
                combatant_str = ("# " if self.index == c.index else "  ") + c.get_summary(private, no_notes=True)
                combatant_strs.append(combatant_str)
        return out.format("\n".join(combatant_strs))

    # db
    async def commit(self, ctx):
        """Commits the combat to db."""
        for pc in self.get_combatants():
            if isinstance(pc, PlayerCombatant):
                await pc.character.commit(ctx)
        await ctx.bot.mdb.combats.update_one(
            {"channel": self._channel},
            {"$set": self.to_dict(), "$currentDate": {"lastchanged": True}},
            upsert=True,
        )

    async def final(self, ctx):
        """Commit, update the summary message, and fire any recorder events in parallel."""
        # Eventually edit the summary message with the latest summary - this is fire-and-forget so that edit ratelimits
        # do not hold up the rest of the execution that might be waiting on this.
        asyncio.create_task(self.update_summary())
        if self.nlp_recorder is None:
            await self.commit(ctx)
        else:
            await asyncio.gather(self.commit(ctx), self.nlp_recorder.on_combat_commit(self, ctx))

    # misc
    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.combats.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInCombat

    async def update_summary(self):
        """Edits the summary message with the latest summary."""
        try:
            await self.get_summary_msg().edit(content=self.get_summary())
        except disnake.HTTPException:
            pass

    def get_channel(self) -> disnake.TextChannel | disnake.Thread:
        """Gets the Channel object of the combat."""
        if self.ctx:
            return self.ctx.channel
        else:
            chan = self.ctx.bot.get_channel(self.channel_id)
            if chan:
                return chan
            else:
                raise CombatChannelNotFound()

    def get_summary_msg(self) -> disnake.PartialMessage:
        """Gets the Message object of the combat summary."""
        return disnake.PartialMessage(channel=self.get_channel(), id=self.summary_message_id)

    def __str__(self):
        return f"Initiative in <#{self.channel_id}>"


async def deserialize_combatant(raw_combatant, ctx, combat):
    ctype = CombatantType(raw_combatant["type"])
    if ctype == CombatantType.GENERIC:
        return Combatant.from_dict(raw_combatant, ctx, combat)
    elif ctype == CombatantType.MONSTER:
        return MonsterCombatant.from_dict(raw_combatant, ctx, combat)
    elif ctype == CombatantType.PLAYER:
        try:
            return await PlayerCombatant.from_dict(raw_combatant, ctx, combat)
        except NoCharacter:
            # if the character was deleted, make a best effort to restore what we know
            # note: PlayerCombatant.from_dict mutates raw_combatant so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Combatant(ctx, combat, **raw_combatant)
    elif ctype == CombatantType.GROUP:
        return await CombatantGroup.from_dict(raw_combatant, ctx, combat)
    else:
        raise CombatException(f"Unknown combatant type: {raw_combatant['type']}")


def deserialize_combatant_sync(raw_combatant, ctx, combat):
    ctype = CombatantType(raw_combatant["type"])
    if ctype == CombatantType.GENERIC:
        return Combatant.from_dict(raw_combatant, ctx, combat)
    elif ctype == CombatantType.MONSTER:
        return MonsterCombatant.from_dict(raw_combatant, ctx, combat)
    elif ctype == CombatantType.PLAYER:
        try:
            return PlayerCombatant.from_dict_sync(raw_combatant, ctx, combat)
        except NoCharacter:
            # if the character was deleted, make a best effort to restore what we know
            # note: PlayerCombatant.from_dict mutates raw_combatant so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Combatant(ctx, combat, **raw_combatant)
    elif ctype == CombatantType.GROUP:
        return CombatantGroup.from_dict_sync(raw_combatant, ctx, combat)
    else:
        raise CombatException(f"Unknown combatant type: {raw_combatant['type']}")
