import cachetools
import discord
from d20 import roll

from cogs5e.models.errors import ChannelInCombat, CombatChannelNotFound, CombatException, CombatNotFound, \
    InvalidArgument, NoCharacter, NoCombatants, RequiresContext
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistance, Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP, StatBlock
from gamedata.monster import MonsterCastableSpellbook
from utils.argparser import argparse
from utils.constants import RESIST_TYPES
from utils.functions import get_selection, maybe_mod

COMBAT_TTL = 60 * 60 * 24 * 7  # 1 week TTL


class Combat:
    # cache combats for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Combat.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Combat state
    # caches based on channel id
    # probably won't encounter any scaling issues, since a combat will be shard-specific
    _cache = cachetools.TTLCache(maxsize=50, ttl=10)
    message_cache = cachetools.LRUCache(500)

    def __init__(self, channelId, summaryMsgId, dmId, options, ctx, combatants=None, roundNum=0, turnNum=0,
                 currentIndex=None):
        if combatants is None:
            combatants = []
        self._channel = channelId  # readonly
        self._summary = summaryMsgId  # readonly
        self._dm = dmId
        self._options = options  # readonly (?)
        self._combatants = combatants
        self._round = roundNum
        self._turn = turnNum
        self._current_index = currentIndex
        self.ctx = ctx

    @classmethod
    def new(cls, channelId, summaryMsgId, dmId, options, ctx):
        return cls(channelId, summaryMsgId, dmId, options, ctx)

    @classmethod
    async def from_ctx(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        return await cls.from_id(channel_id, ctx)

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
    async def from_id(cls, channel_id, ctx):  # cached
        if channel_id in cls._cache:
            return cls._cache[channel_id]
        else:
            raw = await ctx.bot.mdb.combats.find_one({"channel": channel_id})
            if raw is None:
                raise CombatNotFound
            # write to cache
            inst = await cls.from_dict(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    async def from_dict(cls, raw, ctx):
        inst = cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, [], raw['round'],
                   raw['turn'], raw['current'])
        for c in raw['combatants']:
            if c['type'] == 'common':
                inst._combatants.append(Combatant.from_dict(c, ctx, inst))
            elif c['type'] == 'monster':
                inst._combatants.append(MonsterCombatant.from_dict(c, ctx, inst))
            elif c['type'] == 'player':
                inst._combatants.append(await PlayerCombatant.from_dict(c, ctx, inst))
            elif c['type'] == 'group':
                inst._combatants.append(await CombatantGroup.from_dict(c, ctx, inst))
            else:
                raise CombatException("Unknown combatant type")
        return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx):
        inst = cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, [], raw['round'],
                   raw['turn'], raw['current'])
        for c in raw['combatants']:
            if c['type'] == 'common':
                inst._combatants.append(Combatant.from_dict(c, ctx, inst))
            elif c['type'] == 'monster':
                inst._combatants.append(MonsterCombatant.from_dict(c, ctx, inst))
            elif c['type'] == 'player':
                inst._combatants.append(PlayerCombatant.from_dict_sync(c, ctx, inst))
            elif c['type'] == 'group':
                inst._combatants.append(CombatantGroup.from_dict_sync(c, ctx, inst))
            else:
                raise CombatException("Unknown combatant type")
        return inst

    def to_dict(self):
        return {'channel': self.channel, 'summary': self.summary, 'dm': self.dm, 'options': self.options,
                'combatants': [c.to_dict() for c in self._combatants], 'turn': self.turn_num,
                'round': self.round_num, 'current': self._current_index}

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

    @property
    def current_combatant(self):
        """The combatant whose turn it currently is."""
        return next((c for c in self._combatants if c.index == self.index), None) if self.index is not None else None

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
        return next(c for c in self._combatants if c.index == index) if index is not None else None

    def get_combatants(self, groups=False):
        """
        Returns a list of all Combatants in a combat.
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

    def add_combatant(self, combatant):
        self._combatants.append(combatant)
        self.sort_combatants()

    def remove_combatant(self, combatant, ignore_remove_hook=False):
        if not ignore_remove_hook:
            combatant.on_remove()
        if not combatant.group:
            self._combatants.remove(combatant)
            self.sort_combatants()
        else:
            self.get_group(combatant.group).remove_combatant(combatant)
            self.check_empty_groups()
        return self

    def sort_combatants(self):
        current = self.current_combatant
        self._combatants = sorted(self._combatants, key=lambda k: (k.init, int(k.init_skill)), reverse=True)
        for n, c in enumerate(self._combatants):
            c.index = n
        if current is not None:
            self._current_index = current.index
            self._turn = current.init

    def get_combatant(self, name, strict=True):
        if strict:
            return next((c for c in self.get_combatants() if c.name.lower() == name.lower()), None)
        else:
            return next((c for c in self.get_combatants() if name.lower() in c.name.lower()), None)

    def get_group(self, name, create=None, strict=True):
        """
        Gets a combatant group.
        :rtype: CombatantGroup
        :param name: The name of the combatant group.
        :param create: The initiative to create a group at if a group is not found.
        :param strict: Whether group name must be a full case insensitive match.
        :return: The combatant group.
        """
        if strict:
            grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)
        else:
            grp = next((g for g in self.get_groups() if name.lower() in g.name.lower()), None)

        if grp is None and create is not None:
            grp = CombatantGroup.new(self, name, init=create, ctx=self.ctx)
            self.add_combatant(grp)

        return grp

    def get_groups(self):
        return [c for c in self._combatants if isinstance(c, CombatantGroup)]

    def check_empty_groups(self):
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
            rolls[c.name] = init_roll
        self.sort_combatants()

        # reset current turn
        self._turn = 0
        self._current_index = None

        order = []
        for combatant_name, init_roll in sorted(rolls.items(), key=lambda r: r[1].total, reverse=True):
            order.append(f"{init_roll.result}: {combatant_name}")

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
        matching = [(c.name, c) for c in self.get_combatants(select_group) if name.lower() == c.name.lower()]
        if not matching:
            matching = [(c.name, c) for c in self.get_combatants(select_group) if name.lower() in c.name.lower()]
        return await get_selection(self.ctx, matching, message=choice_message)

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

    def get_turn_str(self):
        nextCombatant = self.current_combatant

        if isinstance(nextCombatant, CombatantGroup):
            thisTurn = nextCombatant.get_combatants()
            outStr = "**Initiative {} (round {})**: {} ({})\n{}"
            outStr = outStr.format(self.turn_num,
                                   self.round_num,
                                   nextCombatant.name,
                                   ", ".join({co.controller_mention() for co in thisTurn}),
                                   '```markdown\n' + "\n".join([co.get_status() for co in thisTurn]) + '```')
        else:
            outStr = "**Initiative {} (round {})**: {}\n{}"
            outStr = outStr.format(self.turn_num,
                                   self.round_num,
                                   "{} ({})".format(nextCombatant.name, nextCombatant.controller_mention()),
                                   '```markdown\n' + nextCombatant.get_status() + '```')

        if self.options.get('turnnotif'):
            nextTurn = self.next_combatant
            outStr += f"**Next up**: {nextTurn.name} ({nextTurn.controller_mention()})\n"
        return outStr

    def get_turn_str_mentions(self):
        """Gets the :class:`discord.AllowedMentions` for the users mentioned in the current turn str."""
        if self.current_combatant is None:
            return None
        if isinstance(self.current_combatant, CombatantGroup):
            user_ids = {discord.Object(id=int(comb.controller)) for comb in self.current_combatant.get_combatants()}
        else:
            user_ids = {discord.Object(id=int(self.current_combatant.controller))}

        if self.options.get('turnnotif'):
            if self.next_combatant is not None:
                user_ids.add(discord.Object(id=int(self.next_combatant.controller)))
        return discord.AllowedMentions(users=list(user_ids))

    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.combats.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInCombat

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

    def get_summary(self, private=False):
        """Returns the generated summary message content."""
        combatants = sorted(self._combatants, key=lambda k: (k.init, int(k.init_skill)), reverse=True)
        outStr = "```markdown\n{}: {} (round {})\n".format(
            self.options.get('name') if self.options.get('name') else "Current initiative",
            self.turn_num, self.round_num)
        outStr += f"{'=' * (len(outStr) - 13)}\n"

        combatantStr = ""
        for c in combatants:
            combatantStr += ("# " if self.index == c.index else "  ") + c.get_summary(private) + "\n"

        outStr += "{}```"  # format place for combatatstr
        if len(outStr.format(combatantStr)) > 2000:
            combatantStr = ""
            for c in combatants:
                combatantStr += ("# " if self.index == c.index else "  ") + c.get_summary(private, no_notes=True) + "\n"
        return outStr.format(combatantStr)

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
                raise CombatChannelNotFound

    async def get_summary_msg(self):
        """Gets the Message object of the combat summary."""
        if self.summary in Combat.message_cache:
            return Combat.message_cache[self.summary]
        else:
            msg = await self.get_channel().fetch_message(self.summary)
            Combat.message_cache[msg.id] = msg
            return msg

    async def final(self):
        """Final commit/update."""
        await self.commit()
        await self.update_summary()

    async def end(self):
        """Ends combat in a channel."""
        for c in self._combatants:
            c.on_remove()
        await self.ctx.bot.mdb.combats.delete_one({"channel": self.channel})
        if self.channel in Combat._cache:
            del Combat._cache[self.channel]

    def __str__(self):
        return f"Initiative in <#{self.channel}>"


class Combatant(StatBlock):
    DESERIALIZE_MAP = DESERIALIZE_MAP  # allow making class-specific deser maps

    def __init__(self,
                 # init metadata
                 ctx, combat, name: str, controller_id: str, private: bool, init: int, index: int = None,
                 notes: str = None, effects: list = None, group: str = None,
                 # statblock info
                 stats: BaseStats = None, levels: Levels = None, attacks: AttackList = None,
                 skills: Skills = None, saves: Saves = None, resistances: Resistances = None,
                 spellbook: Spellbook = None,
                 ac: int = None, max_hp: int = None, hp: int = None, temp_hp: int = 0):
        super(Combatant, self).__init__(
            name=name, stats=stats, levels=levels, attacks=attacks, skills=skills, saves=saves, resistances=resistances,
            spellbook=spellbook,
            ac=ac, max_hp=max_hp, hp=hp, temp_hp=temp_hp
        )
        if effects is None:
            effects = []
        self.ctx = ctx
        self.combat = combat

        self._controller = controller_id
        self._init = init
        self._private = private
        self._index = index  # combat write only; position in combat
        self._notes = notes
        self._effects = effects
        self._group = group

        self._cache = {}

    @classmethod
    def new(cls, name: str, controller_id: str, init: int, init_skill: Skill, max_hp: int, ac: int, private: bool,
            resists: Resistances, ctx, combat):
        skills = Skills.default()
        skills.update({"initiative": init_skill})
        return cls(ctx, combat, name, controller_id, private, init, resistances=resists, skills=skills,
                   max_hp=max_hp, ac=ac)

    @classmethod
    def from_dict(cls, raw, ctx, combat):
        for key, klass in cls.DESERIALIZE_MAP.items():
            if key in raw:
                raw[key] = klass.from_dict(raw[key])
        del raw['type']
        effects = raw.pop('effects')
        inst = cls(ctx, combat, **raw)
        inst._effects = [Effect.from_dict(e, combat, inst) for e in effects]
        return inst

    def to_dict(self):
        d = super(Combatant, self).to_dict()
        d.update({
            'controller_id': self.controller, 'init': self.init, 'private': self.is_private,
            'index': self.index, 'notes': self.notes, 'effects': [e.to_dict() for e in self.get_effects()],
            'group': self.group, 'type': 'common'
        })
        return d

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        for effect in self._effects:
            effect.on_name_change(self._name, new_name)
        self._name = new_name

    @property
    def controller(self):
        return self._controller

    @controller.setter
    def controller(self, new_controller_id):
        self._controller = new_controller_id

    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, new_init):
        self._init = new_init

    @property
    def init_skill(self):
        return self.skills.initiative

    @property
    def max_hp(self):
        return self._max_hp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp
        if self._hp is None:
            self._hp = new_max_hp

    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, new_hp):
        self._hp = new_hp

    def hp_str(self, private=False):
        """Returns a string representation of the combatant's HP."""
        hpStr = ''
        if not self.is_private or private:
            hpStr = '<{}/{} HP>'.format(self.hp, self.max_hp) if self.max_hp is not None else '<{} HP>'.format(
                self.hp) if self.hp is not None else ''
            if self.temp_hp and self.temp_hp > 0:
                hpStr += f' (+{self.temp_hp} temp)'
        elif self.max_hp is not None and self.max_hp > 0:
            ratio = self.hp / self.max_hp
            if ratio >= 1:
                hpStr = "<Healthy>"
            elif 0.5 < ratio < 1:
                hpStr = "<Injured>"
            elif 0.15 < ratio <= 0.5:
                hpStr = "<Bloodied>"
            elif 0 < ratio <= 0.15:
                hpStr = "<Critical>"
            elif ratio <= 0:
                hpStr = "<Dead>"
        return hpStr

    @property
    def ac(self):
        _ac = self._ac
        for e in self.active_effects('ac'):
            _ac = maybe_mod(e, base=_ac)
        return _ac

    @ac.setter
    def ac(self, new_ac):
        self._ac = new_ac

    @property
    def is_private(self):
        return self._private

    @is_private.setter
    def is_private(self, new_privacy):
        self._private = new_privacy

    @property
    def resistances(self):
        out = self._resistances.copy()
        out.update(Resistances.from_dict({k: self.active_effects(k) for k in RESIST_TYPES}), overwrite=False)
        return out

    def set_resist(self, damage_type: str, resist_type: str):
        if resist_type not in RESIST_TYPES:
            raise ValueError("Resistance type is invalid")

        for rt in RESIST_TYPES:
            for resist in reversed(self._resistances[rt]):
                if resist.dtype == damage_type:
                    self._resistances[rt].remove(resist)

        if resist_type != 'neutral':
            resistance = Resistance.from_str(damage_type)
            self._resistances[resist_type].append(resistance)

    @property
    def attacks(self):
        if 'attacks' not in self._cache:
            # attacks granted by effects are cached so that the same object is referenced in initTracker (#950)
            self._cache['attacks'] = self._attacks + AttackList.from_dict(self.active_effects('attack'))
        return self._cache['attacks']

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    @property
    def notes(self):
        return self._notes

    @notes.setter
    def notes(self, new_notes):
        self._notes = new_notes

    @property
    def group(self):
        return self._group

    @group.setter
    def group(self, value):
        self._group = value

    def add_effect(self, effect):
        # handle name conflict
        if self.get_effect(effect.name, True):
            self.get_effect(effect.name).remove()

        # handle concentration conflict
        conc_conflict = []
        if effect.concentration:
            conc_conflict = self.remove_all_effects(lambda e: e.concentration)

        # invalidate cache
        self._invalidate_effect_cache()

        self._effects.append(effect)
        return {"conc_conflict": conc_conflict}

    def get_effects(self):
        return self._effects

    def get_effect(self, name, strict=True):
        if strict:
            return next((c for c in self.get_effects() if c.name == name), None)
        else:
            return next((c for c in self.get_effects() if name.lower() in c.name.lower()), None)

    async def select_effect(self, name):
        """
        Opens a prompt for a user to select the effect they were searching for.
        :rtype: Effect
        :param name: The name of the effect to search for.
        :return: The selected Effect, or None if the search failed.
        """
        matching = [(c.name, c) for c in self.get_effects() if name.lower() in c.name.lower()]
        return await get_selection(self.ctx, matching)

    def remove_effect(self, effect):
        try:
            self._effects.remove(effect)
        except ValueError:
            # this should be safe
            # the only case where this occurs is if a parent removes an effect while it's trying to remove itself
            pass
        # invalidate cache
        self._invalidate_effect_cache()

    def remove_all_effects(self, _filter=None):
        if _filter is None:
            _filter = lambda _: True
        to_remove = list(filter(_filter, self._effects))
        for e in to_remove:
            e.remove()
        return to_remove

    def active_effects(self, key=None):
        if 'parsed_effects' not in self._cache:
            parsed_effects = {}
            for effect in self.get_effects():
                for k, v in effect.effect.items():
                    if k not in parsed_effects:
                        parsed_effects[k] = []
                    if not isinstance(v, list):
                        parsed_effects[k].append(v)
                    else:
                        parsed_effects[k].extend(v)
            self._cache['parsed_effects'] = parsed_effects
        if key:
            return self._cache['parsed_effects'].get(key, [])
        return self._cache['parsed_effects']

    def _invalidate_effect_cache(self):
        if 'parsed_effects' in self._cache:
            del self._cache['parsed_effects']
        if 'attacks' in self._cache:
            del self._cache['attacks']

    def is_concentrating(self):
        return any(e.concentration for e in self.get_effects())

    def controller_mention(self):
        return f"<@{self.controller}>"

    def on_turn(self, num_turns=1):
        """
        A method called at the start of each of the combatant's turns.
        :param num_turns: The number of turns that just passed.
        :return: None
        """
        for e in self.get_effects().copy():
            e.on_turn(num_turns)

    def on_turn_end(self, num_turns=1):
        """A method called at the end of each of the combatant's turns."""
        for e in self.get_effects().copy():
            e.on_turn_end(num_turns)

    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        hpStr = f"{self.hp_str(private)} " if self.hp_str(private) else ''
        if not no_notes:
            return f"{self.init:>2}: {self.name} {hpStr}{self.get_effects_and_notes()}"
        else:
            return f"{self.init:>2}: {self.name} {hpStr}"

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        name = self.name
        hp_ac = self.get_hp_and_ac(private)
        resists = self.get_resist_string(private)
        notes = '\n# ' + self.notes if self.notes else ''
        effects = self.get_long_effects()
        return f"{name} {hp_ac} {resists}{notes}\n{effects}".strip()

    def get_long_effects(self):
        return '\n'.join(f"* {str(e)}" for e in self.get_effects())

    def get_effects_and_notes(self):
        out = []
        if self.ac is not None and not self.is_private:
            out.append('AC {}'.format(self.ac))
        for e in self.get_effects():
            out.append(e.get_short_str())
        if self.notes:
            out.append(self.notes)
        if out:
            return f"({', '.join(out)})"
        return ""

    def get_hp_and_ac(self, private: bool = False):
        out = [self.hp_str(private)]
        if self.ac is not None and (not self.is_private or private):
            out.append("(AC {})".format(self.ac))
        return ' '.join(out)

    def get_resist_string(self, private: bool = False):
        resist_str = ''
        if not self.is_private or private:
            if len(self.resistances.resist) > 0:
                resist_str += "\n> Resistances: " + ', '.join([str(r) for r in self.resistances.resist])
            if len(self.resistances.immune) > 0:
                resist_str += "\n> Immunities: " + ', '.join([str(r) for r in self.resistances.immune])
            if len(self.resistances.vuln) > 0:
                resist_str += "\n> Vulnerabilities: " + ', '.join([str(r) for r in self.resistances.vuln])
        return resist_str

    def on_remove(self):
        """
        Called when the combatant is removed from combat, either through !i remove or the combat ending.
        """
        pass

    def __str__(self):
        return f"{self.name}: {self.hp_str()}".strip()

    def __hash__(self):
        return hash(f"{self.combat.channel}.{self.name}")


class MonsterCombatant(Combatant):
    DESERIALIZE_MAP = {**DESERIALIZE_MAP, "spellbook": MonsterCastableSpellbook}

    def __init__(self,
                 # init metadata
                 ctx, combat, name: str, controller_id: str, private: bool, init: int, index: int = None,
                 notes: str = None, effects: list = None, group: str = None,
                 # statblock info
                 stats: BaseStats = None, levels: Levels = None, attacks: AttackList = None,
                 skills: Skills = None, saves: Saves = None, resistances: Resistances = None,
                 spellbook: Spellbook = None,
                 ac: int = None, max_hp: int = None, hp: int = None, temp_hp: int = 0,
                 # monster specific
                 monster_name=None):
        super(MonsterCombatant, self).__init__(
            ctx, combat, name, controller_id, private, init, index, notes, effects, group,
            stats, levels, attacks, skills, saves, resistances, spellbook, ac, max_hp, hp, temp_hp)
        self._monster_name = monster_name

    @classmethod
    def from_monster(cls, monster, ctx, combat, name, controller_id, init, private, hp=None, ac=None):
        monster_name = monster.name
        hp = int(monster.hp) if not hp else int(hp)
        ac = int(monster.ac) if not ac else int(ac)

        # copy spellbook
        spellbook = None
        if monster.spellbook is not None:
            spellbook = MonsterCastableSpellbook.copy(monster.spellbook)

        # copy resistances (#1134)
        resistances = monster.resistances.copy()

        return cls(ctx, combat, name, controller_id, private, init,
                   # statblock info
                   stats=monster.stats, levels=monster.levels, attacks=monster.attacks,
                   skills=monster.skills, saves=monster.saves, resistances=resistances,
                   spellbook=spellbook, ac=ac, max_hp=hp,
                   # monster specific
                   monster_name=monster_name)

    @classmethod
    def from_dict(cls, raw, ctx, combat):
        inst = super(MonsterCombatant, cls).from_dict(raw, ctx, combat)
        inst._monster_name = raw['monster_name']
        return inst

    @property
    def monster_name(self):
        return self._monster_name

    def to_dict(self):
        raw = super(MonsterCombatant, self).to_dict()
        raw['monster_name'] = self.monster_name
        raw['type'] = 'monster'
        return raw


class PlayerCombatant(Combatant):
    def __init__(self,
                 # init metadata
                 ctx, combat, name: str, controller_id: str, private: bool, init: int, index: int = None,
                 notes: str = None, effects: list = None, group: str = None,
                 # statblock info
                 attacks: AttackList = None, resistances: Resistances = None,
                 ac: int = None, max_hp: int = None,
                 # character specific
                 character_id=None, character_owner=None):
        # note that the player combatant doesn't initialize the statblock
        # because we want the combatant statblock attrs to reference the character attrs
        super(PlayerCombatant, self).__init__(
            ctx, combat, name, controller_id, private, init, index, notes, effects, group,
            attacks=attacks, resistances=resistances, ac=ac, max_hp=max_hp
        )
        self.character_id = character_id
        self.character_owner = character_owner

        self._character = None  # cache

    @classmethod
    async def from_character(cls, character, ctx, combat, controller_id, init, private):
        inst = cls(ctx, combat, character.name, controller_id, private, init,
                   # statblock copies
                   resistances=character.resistances.copy(),
                   # character specific
                   character_id=character.upstream, character_owner=character.owner)
        inst._character = character
        return inst

    @property
    def character(self):
        return self._character

    @property
    def init_skill(self):
        return self.character.skills.initiative

    @property
    def stats(self):
        return self.character.stats

    @property
    def levels(self):
        return self.character.levels

    @property
    def skills(self):
        return self.character.skills

    @property
    def saves(self):
        return self.character.saves

    @property
    def ac(self):
        _ac = self._ac or self.character.ac
        for e in self.active_effects('ac'):
            _ac = maybe_mod(e, base=_ac)
        return _ac

    @ac.setter
    def ac(self, new_ac):
        """
        :param int|None new_ac: The new AC
        """
        self._ac = new_ac

    @property
    def spellbook(self):
        return self.character.spellbook

    @property
    def max_hp(self):
        return self._max_hp or self.character.max_hp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp

    @property
    def hp(self):
        return self.character.hp

    @hp.setter
    def hp(self, new_hp):
        self.character.hp = new_hp

    def set_hp(self, new_hp):
        return self.character.set_hp(new_hp)

    def reset_hp(self):
        return self.character.reset_hp()

    @property
    def temp_hp(self):
        return self.character.temp_hp

    @temp_hp.setter
    def temp_hp(self, new_hp):
        self.character.temp_hp = new_hp

    @property
    def attacks(self):
        return super().attacks + self.character.attacks

    def get_scope_locals(self):
        return {**self.character.get_scope_locals(), **super().get_scope_locals()}

    # ==== serialization ====
    @classmethod
    async def from_dict(cls, raw, ctx, combat):
        inst = super(PlayerCombatant, cls).from_dict(raw, ctx, combat)
        inst.character_id = raw['character_id']
        inst.character_owner = raw['character_owner']

        try:
            from cogs5e.models.character import Character
            inst._character = await Character.from_bot_and_ids(ctx.bot, inst.character_owner, inst.character_id)
        except NoCharacter:
            raise CombatException(f"A character in combat was deleted. "
                                  f"Please run `{ctx.prefix}init end -force` to end combat.")

        return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx, combat):
        inst = super(PlayerCombatant, cls).from_dict(raw, ctx, combat)
        inst.character_id = raw['character_id']
        inst.character_owner = raw['character_owner']

        try:
            from cogs5e.models.character import Character
            inst._character = Character.from_bot_and_ids_sync(ctx.bot, inst.character_owner, inst.character_id)
        except NoCharacter:
            raise CombatException(f"A character in combat was deleted. "
                                  f"Please run `{ctx.prefix}init end -force` to end combat.")
        return inst

    def to_dict(self):
        IGNORED_ATTRIBUTES = ("stats", "levels", "skills", "saves", "spellbook", "hp", "temp_hp")
        raw = super(PlayerCombatant, self).to_dict()
        for attr in IGNORED_ATTRIBUTES:
            del raw[attr]
        raw['character_id'] = self.character_id
        raw['character_owner'] = self.character_owner
        raw['type'] = 'player'
        return raw


class CombatantGroup(Combatant):
    def __init__(self, ctx, combat, combatants, name, init, index=None):
        super(CombatantGroup, self).__init__(
            ctx, combat, name=name, controller_id=str(ctx.author.id), private=False, init=init, index=index)
        self._combatants = combatants

    # noinspection PyMethodOverriding
    @classmethod
    def new(cls, combat, name, init, ctx=None):
        return cls(ctx, combat, [], name, init)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = new_name
        for combatant in self._combatants:
            combatant.group = self.name

    def get_name(self):
        return self.name

    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, new_init):
        self._init = new_init

    @property
    def init_skill(self):
        # groups: if all combatants are the same type, return the first one's skill, otherwise +0
        if all(isinstance(c, MonsterCombatant) for c in self._combatants) \
                and len(set(c.monster_name for c in self._combatants)) == 1:
            return self._combatants[0].init_skill
        return Skill(0)

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    @property
    def controller(self):
        return str(self.ctx.author.id)  # workaround

    @property
    def attacks(self):
        a = AttackList()
        seen = set()
        for c in self.get_combatants():
            for atk in c.attacks:
                if atk in seen:
                    continue
                seen.add(atk)
                atk_copy = Attack.copy(atk)
                atk_copy.name = f"{atk.name} ({c.name})"
                a.append(atk_copy)
        return a

    def get_combatants(self):
        return self._combatants

    def add_combatant(self, combatant):
        self._combatants.append(combatant)
        combatant.group = self.name
        combatant.init = self.init

    def remove_combatant(self, combatant):
        self._combatants.remove(combatant)
        combatant.group = None

    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        if len(self._combatants) > 7 and not private:
            status = f"{self.init:>2}: {self.name} ({len(self.get_combatants())} combatants)"
        else:
            status = f"{self.init:>2}: {self.name}"
            for c in self.get_combatants():
                status += f'\n     - {": ".join(c.get_summary(private, no_notes).split(": ")[1:])}'
        return status

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        return '\n'.join(c.get_status(private) for c in self.get_combatants())

    def on_turn(self, num_turns=1):
        for c in self.get_combatants():
            c.on_turn(num_turns)

    def on_turn_end(self, num_turns=1):
        for c in self.get_combatants():
            c.on_turn_end(num_turns)

    def on_remove(self):
        for c in self.get_combatants():
            c.on_remove()

    def controller_mention(self):
        return ", ".join({c.controller_mention() for c in self.get_combatants()})

    @classmethod
    async def from_dict(cls, raw, ctx, combat):
        combatants = []
        for c in raw.pop('combatants'):
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx, combat))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx, combat))
            elif c['type'] == 'player':
                combatants.append(await PlayerCombatant.from_dict(c, ctx, combat))
            else:
                raise CombatException("Unknown combatant type")
        del raw['type']
        return cls(ctx, combat, combatants, **raw)

    @classmethod
    def from_dict_sync(cls, raw, ctx, combat):
        combatants = []
        for c in raw.pop('combatants'):
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx, combat))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx, combat))
            elif c['type'] == 'player':
                combatants.append(PlayerCombatant.from_dict_sync(c, ctx, combat))
            else:
                raise CombatException("Unknown combatant type")
        del raw['type']
        return cls(ctx, combat, combatants, **raw)

    def to_dict(self):
        return {'name': self.name, 'init': self.init, 'combatants': [c.to_dict() for c in self.get_combatants()],
                'index': self.index, 'type': 'group'}

    def __str__(self):
        return f"{self.name} ({len(self.get_combatants())} combatants)"

    def __contains__(self, item):
        return item in self._combatants

    def __len__(self):
        return len(self._combatants)


# ==== effect helpers ====
def parse_attack_arg(arg, name):
    data = arg.split('|')
    if not len(data) == 3:
        raise InvalidArgument("`attack` arg must be formatted `HIT|DAMAGE|TEXT`")
    return {'name': name, 'attackBonus': data[0] or None, 'damage': data[1] or None, 'details': data[2] or None}


def parse_attack_str(atk):
    try:
        return f"{int(atk['attackBonus']):+}|{atk['damage']}"
    except:
        return f"{atk['attackBonus']}|{atk['damage']}"


def parse_resist_arg(arg, _):
    return [Resistance.from_dict(r).to_dict() for r in arg]


def parse_resist_str(resist_list):
    return ', '.join([str(Resistance.from_dict(r)) for r in resist_list])


class Effect:
    LIST_ARGS = ('resist', 'immune', 'vuln', 'neutral')
    SPECIAL_ARGS = {  # 2-tuple of effect, str
        'attack': (parse_attack_arg, parse_attack_str),
        'resist': (parse_resist_arg, parse_resist_str)
    }
    VALID_ARGS = {'b': 'Attack Bonus', 'd': 'Damage Bonus', 'ac': 'AC', 'resist': 'Resistance', 'immune': 'Immunity',
                  'vuln': 'Vulnerability', 'neutral': 'Neutral', 'attack': 'Attack', 'sb': 'Save Bonus'}

    def __init__(self, combat, combatant, name: str, duration: int, remaining: int, effect: dict,
                 concentration: bool = False, children: list = None, parent: dict = None, tonend: bool = False):
        if children is None:
            children = []
        self.combat = combat
        self.combatant = combatant
        self._name = name
        self._duration = duration
        self._remaining = remaining
        self._effect = effect
        self._concentration = concentration
        self.children = children
        self.parent = parent
        self.ticks_on_end = tonend

    @classmethod
    def new(cls, combat, combatant, name, duration, effect_args, concentration: bool = False, character=None,
            tick_on_end=False):
        if isinstance(effect_args, str):
            if (combatant and isinstance(combatant, PlayerCombatant)) or character:
                effect_args = argparse(effect_args, combatant.character or character)
            else:
                effect_args = argparse(effect_args)
        effect_dict = {}
        for arg in effect_args:
            arg_arg = None
            if arg in cls.LIST_ARGS:
                arg_arg = effect_args.get(arg, [])
            elif arg in cls.VALID_ARGS:
                arg_arg = effect_args.last(arg)

            if arg in cls.SPECIAL_ARGS:
                effect_dict[arg] = cls.SPECIAL_ARGS[arg][0](arg_arg, name)
            elif arg_arg is not None:
                effect_dict[arg] = arg_arg
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            raise InvalidArgument("Effect duration must be an integer.")
        return cls(combat, combatant, name, duration, duration, effect_dict, concentration=concentration,
                   tonend=tick_on_end)

    def set_parent(self, parent):
        """Sets the parent of an effect."""
        self.parent = {"combatant": parent.combatant.name, "effect": parent.name}
        parent.children.append({"combatant": self.combatant.name, "effect": self.name})
        return self

    @property
    def name(self):
        return self._name

    @property
    def duration(self):
        return self._duration

    @property
    def remaining(self):
        return self._remaining

    @property
    def effect(self):
        return self._effect

    @property
    def concentration(self):
        return self._concentration

    # --- stringification ---
    def __str__(self):
        out = [self.name]
        if duration := self.duration_str():
            out.append(duration)
        out.append(self.get_parenthetical())
        if self.concentration:
            out.append("<C>")
        return ' '.join(out)

    def get_short_str(self):
        """Gets a short string describing the effect (for display in init summary)"""
        return f'{self.name} {self.duration_str()}'.strip()

    def duration_str(self):
        """Gets a string describing this effect's duration."""
        if self.remaining < 0:
            return ''
        elif 0 <= self.remaining <= 1:  # effect ends on next tick
            if self.ticks_on_end:
                return "[until end of turn]"
            else:
                return "[until start of next turn]"
        elif self.remaining > 5_256_000:  # years
            divisor, unit = 5256000, "year"
        elif self.remaining > 438_000:  # months
            divisor, unit = 438000, "month"
        elif self.remaining > 100_800:  # weeks
            divisor, unit = 100800, "week"
        elif self.remaining > 14_400:  # days
            divisor, unit = 14400, "day"
        elif self.remaining > 600:  # hours
            divisor, unit = 600, "hour"
        elif self.remaining > 10:  # minutes
            divisor, unit = 10, "minute"
        else:  # rounds
            divisor, unit = 1, "round"

        rounded = round(self.remaining / divisor, 1) if divisor > 1 else self.remaining
        return f"[{rounded} {unit}s]"

    def get_parenthetical(self):
        """Gets the descriptive text inside parentheses."""
        text = []
        if self.effect:
            text.append(self.get_effect_str())
        if self.parent:
            text.append(f"Parent: {self.parent['effect']}")  # name of parent effect
        if text:
            return f"({'; '.join(text)})"
        return ""

    def get_effect_str(self):
        out = []
        for k, v in self.effect.items():
            if k in self.SPECIAL_ARGS:
                out.append(f"{self.VALID_ARGS.get(k)}: {self.SPECIAL_ARGS[k][1](v)}")
            elif isinstance(v, list):
                out.append(f"{self.VALID_ARGS.get(k)}: {', '.join(v)}")
            else:
                out.append(f"{self.VALID_ARGS.get(k)}: {v}")
        return '; '.join(out)

    # --- hooks ---
    def on_turn(self, num_turns=1):
        """
        Reduces the turn counter if applicable, and removes itself if at 0.
        """
        if self.remaining >= 0 and not self.ticks_on_end:
            if self.remaining - num_turns <= 0:
                self.remove()
            self._remaining -= num_turns

    def on_turn_end(self, num_turns=1):
        """
        Reduces the turn counter if applicable, and removes itself if at 0.
        """
        if self.remaining >= 0 and self.ticks_on_end:
            if self.remaining - num_turns <= 0:
                self.remove()
            self._remaining -= num_turns

    def remove(self, removed=None):
        if removed is None:
            removed = [self]
        for effect in self.get_children_effects():
            if effect not in removed:  # no infinite recursion please
                removed.append(effect)
                effect.remove(removed)
        self.combatant.remove_effect(self)

    def on_name_change(self, old_name, new_name):
        for effect in self.get_children_effects():
            effect.parent['combatant'] = new_name

        if self.parent:
            parent = self.get_parent_effect()
            for child in parent.children:
                if child['combatant'] == old_name:
                    child['combatant'] = new_name

    def get_parent_effect(self):
        return self.combat.get_combatant(self.parent['combatant'], True).get_effect(self.parent['effect'], True)

    def get_children_effects(self):
        """Returns an iterator of Effects of this Effect's children."""
        for e in self.children.copy():
            child = self.get_child_effect(e)
            if child:
                yield child
            else:
                self.children.remove(e)  # effect was removed elsewhere; disown it

    def get_child_effect(self, e):
        combatant = self.combat.get_combatant(e['combatant'], True)
        if not combatant:
            return None
        return combatant.get_effect(e['effect'], True)

    @classmethod
    def from_dict(cls, raw, combat, combatant):
        return cls(combat, combatant, **raw)

    def to_dict(self):
        return {'name': self.name, 'duration': self.duration, 'remaining': self.remaining, 'effect': self.effect,
                'concentration': self.concentration, 'children': self.children, 'parent': self.parent,
                'tonend': self.ticks_on_end}
