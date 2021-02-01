import cachetools
import discord
from d20 import roll

from utils.functions import search_and_select
from .utils import CombatantType
from .combatant import Combatant, MonsterCombatant, PlayerCombatant
from .errors import *
from .group import CombatantGroup

COMBAT_TTL = 60 * 60 * 24 * 7  # 1 week TTL


class Combat:
    # cache combats for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Combat.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Combat state
    # caches based on channel id
    # probably won't encounter any scaling issues, since a combat will be shard-specific
    _cache = cachetools.TTLCache(maxsize=50, ttl=10)
    message_cache = cachetools.LRUCache(500)

    def __init__(self, channel_id, message_id, dm_id, options, ctx,
                 combatants=None, round_num=0, turn_num=0, current_index=None):
        if combatants is None:
            combatants = []
        self._channel = str(channel_id)  # readonly
        self._summary = int(message_id)  # readonly
        self._dm = str(dm_id)
        self._options = options  # readonly (?)
        self._combatants = combatants
        self._round = round_num
        self._turn = turn_num
        self._current_index = current_index
        self.ctx = ctx

        self._combatant_id_map = {c.id: c for c in combatants}

    @classmethod
    def new(cls, channel_id, message_id, dm_id, options, ctx):
        return cls(channel_id, message_id, dm_id, options, ctx)

    # async deser
    @classmethod
    async def from_ctx(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        return await cls.from_id(channel_id, ctx)

    @classmethod
    async def from_id(cls, channel_id, ctx):  # cached
        if channel_id in cls._cache:
            return cls._cache[channel_id]
        raw = await ctx.bot.mdb.combats.find_one({"channel": channel_id})
        if raw is None:
            raise CombatNotFound()
        # write to cache
        inst = await cls.from_dict(raw, ctx)
        cls._cache[channel_id] = inst
        return inst

    @classmethod
    async def from_dict(cls, raw, ctx):
        inst = cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, [], raw['round'],
                   raw['turn'], raw['current'])
        for c in raw['combatants']:
            ctype = CombatantType(c['type'])
            if ctype == CombatantType.GENERIC:
                inst._combatants.append(Combatant.from_dict(c, ctx, inst))
            elif ctype == CombatantType.MONSTER:
                inst._combatants.append(MonsterCombatant.from_dict(c, ctx, inst))
            elif ctype == CombatantType.PLAYER:
                inst._combatants.append(await PlayerCombatant.from_dict(c, ctx, inst))
            elif ctype == CombatantType.GROUP:
                inst._combatants.append(await CombatantGroup.from_dict(c, ctx, inst))
            else:
                raise CombatException(f"Unknown combatant type: {c['type']}")
        return inst

    # sync deser/ser
    @classmethod
    def from_ctx_sync(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        if channel_id in cls._cache:
            return cls._cache[channel_id]
        else:
            raw = ctx.bot.mdb.combats.delegate.find_one({"channel": channel_id})
            if raw is None:
                raise CombatNotFound
            # write to cache
            inst = cls.from_dict_sync(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx):
        inst = cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, [], raw['round'],
                   raw['turn'], raw['current'])
        for c in raw['combatants']:
            ctype = CombatantType(c['type'])
            if c['type'] == CombatantType.GENERIC:
                inst._combatants.append(Combatant.from_dict(c, ctx, inst))
            elif c['type'] == CombatantType.MONSTER:
                inst._combatants.append(MonsterCombatant.from_dict(c, ctx, inst))
            elif c['type'] == CombatantType.PLAYER:
                inst._combatants.append(PlayerCombatant.from_dict_sync(c, ctx, inst))
            elif c['type'] == CombatantType.GROUP:
                inst._combatants.append(CombatantGroup.from_dict_sync(c, ctx, inst))
            else:
                raise CombatException("Unknown combatant type")
        return inst

    def to_dict(self):
        return {'channel': self.channel, 'summary': self.summary, 'dm': self.dm, 'options': self.options,
                'combatants': [c.to_dict() for c in self._combatants], 'turn': self.turn_num,
                'round': self.round_num, 'current': self._current_index}

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

    @property  # private write
    def turn_num(self):
        return self._turn

    @property  # private write
    def index(self):
        return self._current_index

    # combatants
    @property
    def current_combatant(self):
        """
        The combatant whose turn it currently is.

        :rtype: Combatant
        """
        if self.index is None:
            return None
        return self._combatants[self.index]

    @property
    def next_combatant(self):
        """The combatant whose turn it will be when advance_turn() is called."""
        if len(self._combatants) == 0:
            return None
        if self.index is None:
            index = 0
        elif self.index + 1 >= len(self._combatants):
            index = 0
        else:
            index = self.index + 1
        return self._combatants[index]

    def get_combatants(self, groups=False):
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

    def get_groups(self):
        """
        Returns a list of all CombatantGroups in a combat
        :return: A list of all CombatantGroups
        """
        return [g for g in self._combatants if isinstance(g, CombatantGroup)]

    def add_combatant(self, combatant):
        """
        Adds a combatant to combat, and sorts the combatant list by init.

        :type combatant: Combatant
        """
        self._combatants.append(combatant)
        self._combatant_id_map[combatant.id] = combatant
        self.sort_combatants()

    def remove_combatant(self, combatant, ignore_remove_hook=False):
        """
        Removes a combatant from combat, sorts the combatant list by init (updates index), and fires the remove hook.

        :type combatant: Combatant
        :param bool ignore_remove_hook: Whether or not to ignore the remove hook.
        :rtype: Combatant
        """
        if not ignore_remove_hook:
            combatant.on_remove()
        if not combatant.group:
            self._combatants.remove(combatant)
            del self._combatant_id_map[combatant.id]
            self.sort_combatants()
        else:
            self.get_group(combatant.group).remove_combatant(combatant)
            self._check_empty_groups()
        return self

    def sort_combatants(self):
        """
        Sorts the combatant list by place in init and updates combatants' indices.
        """
        current = self.current_combatant
        self._combatants = sorted(self._combatants, key=lambda k: (k.init, int(k.init_skill)), reverse=True)
        for n, c in enumerate(self._combatants):
            c.index = n
        if current is not None:
            self._current_index = current.index
            self._turn = current.init

    def combatant_by_id(self, combatant_id):
        """Gets a combatant by their ID."""
        return self._combatant_id_map.get(combatant_id)

    def get_combatant(self, name, strict=True):
        """Gets a combatant by their name or ID."""
        if name in self._combatant_id_map:
            return self._combatant_id_map[name]
        if strict:
            return next((c for c in self.get_combatants() if c.name.lower() == name.lower()), None)
        else:
            return next((c for c in self.get_combatants() if name.lower() in c.name.lower()), None)

    def get_group(self, name, create=None, strict=True):
        """
        Gets a combatant group by its name or ID.

        :rtype: CombatantGroup
        :param name: The name of the combatant group.
        :param create: The initiative to create a group at if a group is not found.
        :param strict: Whether group name must be a full case insensitive match.
        :return: The combatant group.
        """
        if name in self._combatant_id_map and isinstance(self._combatant_id_map[name], CombatantGroup):
            return self._combatant_id_map[name]
        if strict:
            grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)
        else:
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

    def reroll_dynamic(self):
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
        self._turn = 0
        self._current_index = None

        order = []
        for combatant, init_roll in sorted(rolls.items(), key=lambda r: (r[1].total, int(r[0].init_skill)),
                                           reverse=True):
            order.append(f"{init_roll.result}: {combatant.name}")

        order = "\n".join(order)

        return order

    async def select_combatant(self, name, choice_message=None, select_group=False):
        """
        Opens a prompt for a user to select the combatant they were searching for.

        :param choice_message: The message to pass to the selector.
        :param select_group: Whether to allow groups to be selected.
        :rtype: Combatant
        :param name: The name of the combatant to search for.
        :return: The selected Combatant, or None if the search failed.
        """
        return await search_and_select(self.ctx, self.get_combatants(select_group), name, lambda c: c.name,
                                       message=choice_message)

    def advance_turn(self):
        """Advances the turn. If any caveats should be noted, returns them in messages."""
        if len(self._combatants) == 0:
            raise NoCombatants

        messages = []

        if self.current_combatant:
            self.current_combatant.on_turn_end()

        changed_round = False
        if self.index is None:  # new round, no dynamic reroll
            self._current_index = 0
            self._round += 1
        elif self.index + 1 >= len(self._combatants):  # new round
            if self.options.get('dynamic'):
                messages.append(f"New initiatives:\n{self.reroll_dynamic()}")
            self._current_index = 0
            self._round += 1
            changed_round = True
        else:
            self._current_index += 1

        self._turn = self.current_combatant.init
        self.current_combatant.on_turn()
        return changed_round, messages

    def rewind_turn(self):
        if len(self._combatants) == 0:
            raise NoCombatants

        if self.current_combatant:
            self.current_combatant.on_turn_end()

        if self.index is None:  # start of combat
            self._current_index = len(self._combatants) - 1
        elif self.index == 0:  # new round
            self._current_index = len(self._combatants) - 1
            self._round -= 1
        else:
            self._current_index -= 1

        self._turn = self.current_combatant.init

    def goto_turn(self, init_num, is_combatant=False):
        if len(self._combatants) == 0:
            raise NoCombatants

        if self.current_combatant:
            self.current_combatant.on_turn_end()

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

    def skip_rounds(self, num_rounds):
        messages = []

        self._round += num_rounds
        for com in self.get_combatants():
            com.on_turn(num_rounds)
            com.on_turn_end(num_rounds)
        if self.options.get('dynamic'):
            messages.append(f"New initiatives:\n{self.reroll_dynamic()}")

        return messages

    async def end(self):
        """Ends combat in a channel."""
        for c in self._combatants:
            c.on_remove()
        await self.ctx.bot.mdb.combats.delete_one({"channel": self.channel})
        if self.channel in Combat._cache:
            del Combat._cache[self.channel]

    # stringification
    def get_turn_str(self):
        """Gets the string representing the current turn, and all combatants on it."""
        combatant = self.current_combatant

        if combatant is None:
            return None

        if isinstance(combatant, CombatantGroup):
            combatants = combatant.get_combatants()
            combatant_statuses = "\n".join([co.get_status() for co in combatants])
            mentions = ", ".join({co.controller_mention() for co in combatants})
            out = f"**Initiative {self.turn_num} (round {self.round_num})**: {combatant.name} ({mentions})\n" \
                  f"```md\n{combatant_statuses}```"

        else:
            out = f"**Initiative {self.turn_num} (round {self.round_num})**: {combatant.name} " \
                  f"({combatant.controller_mention()})\n```md\n{combatant.get_status()}```"

        if self.options.get('turnnotif'):
            nextTurn = self.next_combatant
            out += f"**Next up**: {nextTurn.name} ({nextTurn.controller_mention()})\n"
        return out

    def get_turn_str_mentions(self):
        """Gets the :class:`discord.AllowedMentions` for the users mentioned in the current turn str."""
        if self.current_combatant is None:
            return discord.AllowedMentions.none()
        if isinstance(self.current_combatant, CombatantGroup):
            # noinspection PyUnresolvedReferences
            user_ids = {discord.Object(id=int(comb.controller)) for comb in self.current_combatant.get_combatants()}
        else:
            user_ids = {discord.Object(id=int(self.current_combatant.controller))}

        if self.options.get('turnnotif') and self.next_combatant is not None:
            user_ids.add(discord.Object(id=int(self.next_combatant.controller)))
        return discord.AllowedMentions(users=list(user_ids))

    def get_summary(self, private=False):
        """Returns the generated summary message (pinned) content."""
        combatants = self._combatants
        name = self.options.get('name') if self.options.get('name') else "Current initiative"

        out = f"```md\n{name}: {self.turn_num} (round {self.round_num})\n"
        out += f"{'=' * (len(out) - 7)}\n"

        combatant_strs = []
        for c in combatants:
            combatant_str = ("# " if self.index == c.index else "  ") + c.get_summary(private)
            combatant_strs.append(combatant_str)

        out += "{}```"
        if len(out.format('\n'.join(combatant_strs))) > 2000:
            combatant_strs = []
            for c in combatants:
                combatant_str = ("# " if self.index == c.index else "  ") + c.get_summary(private, no_notes=True)
                combatant_strs.append(combatant_str)
        return out.format('\n'.join(combatant_strs))

    # db
    async def commit(self):
        """Commits the combat to db."""
        if not self.ctx:
            raise RequiresContext
        for pc in self.get_combatants():
            if isinstance(pc, PlayerCombatant):
                await pc.character.commit(self.ctx)
        await self.ctx.bot.mdb.combats.update_one(
            {"channel": self.channel},
            {"$set": self.to_dict(), "$currentDate": {"lastchanged": True}},
            upsert=True
        )

    async def final(self):
        """Final commit/update."""
        await self.commit()
        await self.update_summary()

    # misc
    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.combats.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInCombat

    async def update_summary(self):
        """Edits the summary message with the latest summary."""
        await (await self.get_summary_msg()).edit(content=self.get_summary())

    def get_channel(self):
        """Gets the Channel object of the combat."""
        if self.ctx:
            return self.ctx.message.channel
        else:
            chan = self.ctx.bot.get_channel(int(self.channel))
            if chan:
                return chan
            else:
                raise CombatChannelNotFound()

    async def get_summary_msg(self):
        """Gets the Message object of the combat summary."""
        if self.summary in Combat.message_cache:
            return Combat.message_cache[self.summary]
        else:
            msg = await self.get_channel().fetch_message(self.summary)
            Combat.message_cache[msg.id] = msg
            return msg

    def __str__(self):
        return f"Initiative in <#{self.channel}>"
