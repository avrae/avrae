import copy

import cachetools

from cogs5e.funcs.dice import roll
from cogs5e.models.caster import Spellcasting, Spellcaster
from cogs5e.models.errors import CombatException, CombatNotFound, RequiresContext, ChannelInCombat, \
    CombatChannelNotFound, NoCombatants, NoCharacter, InvalidArgument
from utils.argparser import argparse
from utils.constants import RESIST_TYPES
from utils.functions import get_selection

COMBAT_TTL = 60 * 60 * 24 * 7  # 1 week TTL


class Combat:
    message_cache = cachetools.LRUCache(100)

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
    async def from_ctx(cls, ctx):
        raw = await ctx.bot.mdb.combats.find_one({"channel": str(ctx.channel.id)})
        if raw is None:
            raise CombatNotFound
        return await cls.from_dict(raw, ctx)

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
    async def from_id(cls, _id, ctx):
        raw = await ctx.bot.mdb.combats.find_one({"channel": _id})
        if raw is None:
            raise CombatNotFound
        return await cls.from_dict(raw, ctx)

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

    @property
    def dm(self):
        return self._dm

    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, value):
        self._options = value

    @property  # private write
    def round_num(self):
        return self._round

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
            if isinstance(c, Combatant):
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
        self._combatants = sorted(self._combatants, key=lambda k: (k.init, k.initMod), reverse=True)
        for n, c in enumerate(self._combatants):
            c.index = n
        self._current_index = current.index if current is not None else None

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
            grp = CombatantGroup.new(name, create, self.ctx)
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
        Rerolls all combatant initiatives.
        """
        for c in self._combatants:
            c.init = roll(f"1d20+{c.initMod}").total
        self.sort_combatants()

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
        if len(self._combatants) == 0:
            raise NoCombatants

        if self.current_combatant:
            self.current_combatant.on_turn_end()

        changed_round = False
        if self.index is None:  # new round, no dynamic reroll
            self._current_index = 0
            self._round += 1
        elif self.index + 1 >= len(self._combatants):  # new round
            if self.options.get('dynamic'):
                self.reroll_dynamic()
            self._current_index = 0
            self._round += 1
            changed_round = True
        else:
            self._current_index += 1

        self._turn = self.current_combatant.init
        self.current_combatant.on_turn()
        return changed_round

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
        self._round += num_rounds
        for com in self.get_combatants():
            com.on_turn(num_rounds)
            com.on_turn_end(num_rounds)
        if self.options.get('dynamic'):
            self.reroll_dynamic()

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
                await pc.character.manual_commit(self.ctx.bot, pc.character_owner)
        await self.ctx.bot.mdb.combats.update_one(
            {"channel": self.channel},
            {"$set": self.to_dict(), "$currentDate": {"lastchanged": True}},
            upsert=True
        )

    def get_summary(self, private=False):
        """Returns the generated summary message content."""
        combatants = sorted(self._combatants, key=lambda k: (k.init, k.initMod), reverse=True)
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
            msg = await self.get_channel().get_message(self.summary)
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


class Combatant(Spellcaster):
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx, combat,
                 index=None, notes=None, effects=None, group=None, temphp=None, spellcasting=None, *args, **kwargs):
        super(Combatant, self).__init__(spellcasting)
        if resists is None:
            resists = {}
        if attacks is None:
            attacks = []
        if effects is None:
            effects = []
        self._name = name
        self._controller = controllerId
        self._init = init
        self._mod = initMod  # readonly
        self._hpMax = hpMax  # optional
        self._hp = hp  # optional
        self._ac = ac  # optional
        self._private = private
        self._resists = resists
        self._attacks = attacks
        self._saves = saves
        self._index = index  # combat write only; position in combat
        self.ctx = ctx
        self.combat = combat
        self._notes = notes
        self._effects = effects
        self._group = group
        self._temphp = temphp

        self._cache = {}

    @classmethod
    def new(cls, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx, combat):
        return cls(name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx, combat)

    @classmethod
    def from_dict(cls, raw, ctx, combat):
        inst = cls(raw['name'], raw['controller'], raw['init'], raw['mod'], raw['hpMax'], raw['hp'], raw['ac'],
                   raw['private'], raw['resists'], raw['attacks'], raw['saves'], ctx, combat, index=raw['index'],
                   notes=raw['notes'], effects=[], group=raw['group'],  # begin backwards compatibility
                   temphp=raw.get('temphp'), spellcasting=Spellcasting.from_dict(raw.get('spellcasting', {})))
        inst._effects = [Effect.from_dict(e, combat, inst) for e in raw['effects']]
        return inst

    def to_dict(self):
        return {'name': self.name, 'controller': self.controller, 'init': self.init, 'mod': self.initMod,
                'hpMax': self._hpMax, 'hp': self._hp, 'ac': self._ac, 'private': self.isPrivate,
                'resists': self._resists, 'attacks': self._attacks, 'saves': self._saves, 'index': self.index,
                'notes': self.notes, 'effects': [e.to_dict() for e in self.get_effects()], 'group': self.group,
                'temphp': self.temphp, 'spellcasting': self.spellcasting.to_dict(), 'type': 'common'}

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        for effect in self._effects:
            effect.on_name_change(self._name, new_name)
        self._name = new_name

    def get_name(self):
        return self.name

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
    def initMod(self):
        return self._mod

    @property
    def hpMax(self):
        return self._hpMax

    @hpMax.setter
    def hpMax(self, new_hpMax):
        self._hpMax = new_hpMax
        if self._hp is None:
            self._hp = new_hpMax

    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, new_hp):  # may have odd side effects with temp hp
        if self._temphp:
            delta = new_hp - self._hp  # _hp includes all temp hp
            if delta < 0:  # don't add thp by adding to hp
                self._temphp = max(self._temphp + delta, 0)
        self._hp = new_hp

    def get_hp(self, no_temp=False):
        if not no_temp:
            return self.hp

        if self.temphp and self.temphp > 0:
            hp = self.hp - self.temphp
        else:
            hp = self.hp
        return hp

    def mod_hp(self, delta, overheal=True):
        if not overheal and delta > 0:
            if self.get_hp(True) + delta > self.hpMax:
                delta = max(self.hpMax - self.get_hp(True), 0)  # don't do damage by over-overhealing
        self.hp += delta

    def set_hp(self, new_hp):  # set hp before temp hp
        if self._temphp:
            self._hp = new_hp + self._temphp
        else:
            self._hp = new_hp

    def get_hp_str(self, private=False):
        """Returns a string representation of the combatant's HP."""
        hpStr = ''
        hp = self.get_hp(no_temp=True)
        if not self.isPrivate or private:
            hpStr = '<{}/{} HP>'.format(hp, self.hpMax) if self.hpMax is not None else '<{} HP>'.format(
                hp) if hp is not None else ''
            if self.temphp and self.temphp > 0:
                hpStr += f' <{self.temphp} THP>'
        elif self.hpMax is not None and self.hpMax > 0:
            ratio = self.hp / self.hpMax
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
    def temphp(self):
        return self._temphp

    @temphp.setter
    def temphp(self, new_hp):
        delta = max(new_hp - (self._temphp or 0), -(self._temphp or 0))
        self._temphp = max(new_hp, 0)
        self._hp += delta  # hp includes thp

    @property
    def ac(self):
        _ac = self._ac
        for e in self.active_effects('ac'):
            try:
                if e.startswith(('+', '-')):
                    _ac += int(e)
                else:
                    _ac = int(e)
            except (ValueError, TypeError):
                continue
        return _ac

    @ac.setter
    def ac(self, new_ac):
        self._ac = new_ac

    @property
    def isPrivate(self):
        return self._private

    @isPrivate.setter
    def isPrivate(self, new_privacy):
        self._private = new_privacy

    @property
    def resists(self):
        checked = []
        out = {}
        for k in reversed(RESIST_TYPES):
            out[k] = []
            for _type in self.active_effects(k):
                if _type not in checked:
                    out[k].append(_type)
                    checked.append(_type)
        for k in reversed(RESIST_TYPES):
            for _type in self._resists.get(k, []):
                if _type not in checked:
                    out[k].append(_type)
                    checked.append(_type)
        return out

    def set_resist(self, dmgtype, resisttype):
        if resisttype not in RESIST_TYPES:
            raise ValueError("Resistance type is invalid")
        for rt in RESIST_TYPES:
            if dmgtype in self._resists.get(rt, []):
                self._resists[rt].remove(dmgtype)
        if resisttype not in self._resists:
            self._resists[resisttype] = []
        self._resists[resisttype].append(dmgtype)

    @property
    def attacks(self):
        attacks = self.attack_effects(self._attacks)
        attacks.extend(self.attack_effects(self.active_effects('attack')))
        return attacks

    @property
    def saves(self):
        return self._saves

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
        if self.get_effect(effect.name, True):
            self.get_effect(effect.name).remove()
        conc_conflict = []
        if effect.concentration:
            conc_conflict = self.remove_all_effects(lambda e: e.concentration)

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
            raise CombatException("Effect does not exist on combatant.")

    def remove_all_effects(self, _filter=None):
        if _filter is None:
            _filter = lambda _: True
        to_remove = list(filter(_filter, self._effects))
        for e in to_remove:
            try:
                e.remove()
            except CombatException:  # effect was likely removed already, possibly by its parent being removed
                continue
        return to_remove

    def attack_effects(self, attacks):
        b = self.active_effects('b')
        d = self.active_effects('d')
        if b or d:
            at = copy.deepcopy(attacks)
            for a in at:
                if a['attackBonus'] is not None and b:
                    a['attackBonus'] += f" + {'+'.join(b)}"
                if a['damage'] is not None and d:
                    a['damage'] += f" + {'+'.join(d)}"
            return at
        return attacks.copy()

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
        hpStr = f"{self.get_hp_str(private)} " if self.get_hp_str(private) else ''
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
        if self.ac is not None and not self.isPrivate:
            out.append('AC {}'.format(self.ac))
        for e in self.get_effects():
            out.append('{} [{} rds]'.format(e.name, e.remaining if not e.remaining < 0 else '∞'))
        if self.notes:
            out.append(self.notes)
        if out:
            return f"({', '.join(out)})"
        return ""

    def get_hp_and_ac(self, private: bool = False):
        out = [self.get_hp_str(private)]
        if self.ac is not None and (not self.isPrivate or private):
            out.append("(AC {})".format(self.ac))
        return ' '.join(out)

    def get_resist_string(self, private: bool = False):
        resistStr = ''
        self._resists['resist'] = [r for r in self._resists['resist'] if r]  # clean empty resists
        self._resists['immune'] = [r for r in self._resists['immune'] if r]  # clean empty resists
        self._resists['vuln'] = [r for r in self._resists['vuln'] if r]  # clean empty resists
        if not self.isPrivate or private:
            if len(self.resists['resist']) > 0:
                resistStr += "\n> Resistances: " + ', '.join(self.resists['resist']).title()
            if len(self.resists['immune']) > 0:
                resistStr += "\n> Immunities: " + ', '.join(self.resists['immune']).title()
            if len(self.resists['vuln']) > 0:
                resistStr += "\n> Vulnerabilities: " + ', '.join(self.resists['vuln']).title()
        return resistStr

    def on_remove(self):
        """
        Called when the combatant is removed from combat, either through !i remove or the combat ending.
        """
        pass


class MonsterCombatant(Combatant):
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx, combat,
                 index=None, monster_name=None, notes=None, effects=None, group=None, temphp=None, spellcasting=None):
        super(MonsterCombatant, self).__init__(name, controllerId, init, initMod, hpMax, hp, ac, private, resists,
                                               attacks, saves, ctx, combat, index, notes, effects, group, temphp,
                                               spellcasting)
        self._monster_name = monster_name

    @classmethod
    def from_monster(cls, name, controllerId, init, initMod, private, monster, ctx, combat, opts=None, index=None,
                     hp=None, ac=None):
        monster_name = monster.name
        hp = int(monster.hp) if not hp else int(hp)
        ac = int(monster.ac) if not ac else int(ac)

        resist = monster.raw_resists['resist']
        immune = monster.raw_resists['immune']
        vuln = monster.raw_resists['vuln']
        # fix npr and blug/pierc/slash
        if opts.get('npr'):
            if resist:
                resist = [r for r in resist if not any(t in r.lower() for t in ('bludgeoning', 'piercing', 'slashing'))]
            if immune:
                immune = [r for r in immune if not any(t in r.lower() for t in ('bludgeoning', 'piercing', 'slashing'))]
            if vuln:
                vuln = [r for r in vuln if not any(t in r.lower() for t in ('bludgeoning', 'piercing', 'slashing'))]

        resists = {'resist': [r.lower() for r in resist],
                   'immune': [i.lower() for i in immune],
                   'vuln': [v.lower() for v in vuln]}
        attacks = monster.attacks
        saves = monster.saves
        spellcasting = Spellcasting(monster.spellcasting.get('spells', []), monster.spellcasting.get('dc', 0),
                                    monster.spellcasting.get('attackBonus', 0),
                                    monster.spellcasting.get('casterLevel', 0))

        return cls(name, controllerId, init, initMod, hp, hp, ac, private, resists, attacks, saves, ctx, combat, index,
                   monster_name, spellcasting=spellcasting)

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
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx, combat,
                 index=None, character_id=None, character_owner=None, notes=None, effects=None, group=None,
                 temphp=None, spellcasting=None):
        super(PlayerCombatant, self).__init__(name, controllerId, init, initMod, hpMax, hp, ac, private, resists,
                                              attacks, saves, ctx, combat, index, notes, effects, group, temphp,
                                              spellcasting)
        self.character_id = character_id
        self.character_owner = character_owner
        self._character = None  # shenanigans

    @classmethod
    async def from_character(cls, name, controllerId, init, initMod, ac, private, resists, ctx, combat, character_id,
                             character_owner, char):
        inst = cls(name, controllerId, init, initMod, None, None, ac, private, resists, None, None, ctx, combat,
                   character_id=character_id, character_owner=character_owner)
        inst._character = char
        return inst

    @property
    def character(self):
        return self._character

    @property
    def hpMax(self):
        return self._hpMax or self.character.get_max_hp()

    @hpMax.setter
    def hpMax(self, new_hpMax):
        self._hpMax = new_hpMax

    @property
    def hp(self):
        return self.character.get_current_hp()

    @hp.setter
    def hp(self, new_hp):
        self.character.set_hp(new_hp)

    def set_hp(self, new_hp):
        self.character.set_hp(new_hp, False)

    @property
    def temphp(self):
        return self.character.get_temp_hp()

    @temphp.setter
    def temphp(self, new_hp):
        self.character.set_temp_hp(new_hp)

    @property
    def attacks(self):
        attacks = super(PlayerCombatant, self).attacks
        attacks.extend(self.attack_effects(self.character.get_attacks()))
        return attacks

    @property
    def saves(self):
        return self.character.get_saves()

    @property
    def spellcasting(self):
        return Spellcasting(self.character.get_spell_list(), self.character.get_save_dc(),
                            self.character.get_spell_ab(), self.character.get_level())

    def can_cast(self, spell, level) -> bool:
        return self.character.can_cast(spell, level)

    def cast(self, spell, level):
        self.character.cast(spell, level)

    def remaining_casts_of(self, spell, level):
        return self.character.remaining_casts_of(spell, level)

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

    def to_dict(self):
        raw = super(PlayerCombatant, self).to_dict()
        raw['character_id'] = self.character_id
        raw['character_owner'] = self.character_owner
        raw['type'] = 'player'
        return raw


class CombatantGroup:
    def __init__(self, name, init, combatants, ctx, index=None):
        self._name = name
        self._init = init
        self._combatants = combatants
        self.ctx = ctx
        self._index = index
        self.initMod = 0  # for sorting
        self.group = None  # groups cannot be in groups
        self.isPrivate = False  # eh

    @classmethod
    def new(cls, name, init, ctx=None):
        return cls(name, init, [], ctx)

    @property
    def name(self):
        return self._name

    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, new_init):
        self._init = new_init

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
        a = []
        for c in self.get_combatants():
            a.extend(atk for atk in c.attacks if atk not in a)
        return a

    def get_combatants(self):
        return self._combatants

    def add_combatant(self, combatant):
        self._combatants.append(combatant)
        combatant.group = self.name

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
        for c in raw['combatants']:
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx, combat))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx, combat))
            elif c['type'] == 'player':
                combatants.append(await PlayerCombatant.from_dict(c, ctx, combat))
            else:
                raise CombatException("Unknown combatant type")
        return cls(raw['name'], raw['init'], combatants, ctx, raw['index'])

    def to_dict(self):
        return {'name': self.name, 'init': self.init, 'combatants': [c.to_dict() for c in self.get_combatants()],
                'index': self.index, 'type': 'group'}


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


class Effect:
    LIST_ARGS = ('resist', 'immune', 'vuln', 'neutral')
    SPECIAL_ARGS = {  # 2-tuple of effect, str
        'attack': (parse_attack_arg, parse_attack_str)
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
            if arg in cls.SPECIAL_ARGS:
                effect_dict[arg] = cls.SPECIAL_ARGS[arg][0](effect_args.last(arg), name)
            elif arg in cls.LIST_ARGS:
                effect_dict[arg] = effect_args.get(arg, [])
            elif arg in cls.VALID_ARGS:
                effect_dict[arg] = effect_args.last(arg)
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

    def __str__(self):
        desc = self.name
        if 0 <= self.remaining <= 1:
            if self.ticks_on_end:
                desc += " [until end of turn]"
            else:
                desc += " [until start of next turn]"
        elif self.remaining >= 0:  # ...an effect could have 0 duration
            desc += f" [{self.remaining} rounds]"
        desc += self.get_parenthetical()
        if self.concentration:
            desc += " <C>"
        return desc

    def get_parenthetical(self):
        """Gets the descriptive text inside parentheses."""
        text = []
        if self.effect:
            text.append(self.get_effect_str())
        if self.parent:
            text.append(f"Parent: {self.parent['effect']}")  # name of parent effect
        if text:
            return f" ({'; '.join(text)})"
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
