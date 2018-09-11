import copy

import cachetools

from cogs5e.funcs.dice import roll
from cogs5e.models.errors import CombatException, CombatNotFound, RequiresContext, ChannelInCombat, \
    CombatChannelNotFound, NoCombatants
from utils.argparser import argparse, ParsedArguments
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
        self.sort_combatants()

    @classmethod
    def new(cls, channelId, summaryMsgId, dmId, options, ctx):
        return cls(channelId, summaryMsgId, dmId, options, ctx)

    @classmethod
    async def from_ctx(cls, ctx):
        raw = await ctx.bot.mdb.combats.find_one({"channel": ctx.message.channel.id})
        if raw is None:
            raise CombatNotFound
        return await cls.from_dict(raw, ctx)

    @classmethod
    async def from_dict(cls, raw, ctx):
        combatants = []
        for c in raw['combatants']:
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx))
            elif c['type'] == 'player':
                combatants.append(await PlayerCombatant.from_dict(c, ctx))
            elif c['type'] == 'group':
                combatants.append(await CombatantGroup.from_dict(c, ctx))
            else:
                raise CombatException("Unknown combatant type")
        return cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, combatants, raw['round'],
                   raw['turn'], raw['current'])

    @classmethod
    async def from_id(cls, _id, ctx):
        raw = await ctx.bot.mdb.combats.find_one({"channel": _id})
        if raw is None:
            raise CombatNotFound
        return await cls.from_dict(raw, ctx)

    def to_dict(self):
        return {'channel': self.channel, 'summary': self.summary, 'dm': self.dm, 'options': self.options,
                'combatants': [c.to_dict() for c in self._combatants], 'turn': self.turn_num,
                'round': self.round_num, 'current': self.index}

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

    def remove_combatant(self, combatant, ignore_callback=False):
        if not ignore_callback:
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
            return next((c for c in self.get_combatants() if c.name == name), None)
        else:
            return next((c for c in self.get_combatants() if name.lower() in c.name.lower()), None)

    def get_group(self, name, create=None):
        """
        Gets a combatant group.
        :rtype: CombatantGroup
        :param name: The name of the combatant group.
        :param create: The initiative to create a group at if a group is not found.
        :return: The combatant group.
        """
        grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)

        if grp is None and create is not None:
            grp = CombatantGroup.new(name, create, self.ctx)
            self.add_combatant(grp)

        return grp

    def get_groups(self):
        return [c for c in self._combatants if isinstance(c, CombatantGroup)]

    def check_empty_groups(self):
        for c in self._combatants:
            if isinstance(c, CombatantGroup) and len(c.get_combatants()) == 0:
                self.remove_combatant(c)

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
        if await ctx.bot.mdb.combats.find_one({"channel": ctx.message.channel.id}):
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
        await self.ctx.bot.edit_message(await self.get_summary_msg(), self.get_summary())

    def get_channel(self):
        """Gets the Channel object of the combat."""
        if self.ctx:
            return self.ctx.message.channel
        else:
            chan = self.ctx.bot.get_channel(self.channel)
            if chan:
                return chan
            else:
                raise CombatChannelNotFound

    async def get_summary_msg(self):
        """Gets the Message object of the combat summary."""
        if self.summary in Combat.message_cache:
            return Combat.message_cache[self.summary]
        else:
            msg = await self.ctx.bot.get_message(self.get_channel(), self.summary)
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


class Combatant:
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx,
                 index=None, notes=None, effects=None, group=None, temphp=None, spellcasting=None, *args, **kwargs):
        if resists is None:
            resists = {}
        if attacks is None:
            attacks = []
        if effects is None:
            effects = []
        if spellcasting is None:
            spellcasting = Spellcasting()
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
        self._notes = notes
        self._effects = effects
        self._group = group
        self._temphp = temphp
        self._spellcasting = spellcasting

        self._cache = {}

    @classmethod
    def new(cls, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx):
        return cls(name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx)

    @classmethod
    def from_dict(cls, raw, ctx):
        effects = [Effect.from_dict(e) for e in raw['effects']]
        return cls(raw['name'], raw['controller'], raw['init'], raw['mod'], raw['hpMax'], raw['hp'], raw['ac'],
                   raw['private'], raw['resists'], raw['attacks'], raw['saves'], ctx, index=raw['index'],
                   notes=raw['notes'], effects=effects, group=raw['group'],  # begin backwards compatibility
                   temphp=raw.get('temphp'), spellcasting=Spellcasting.from_dict(raw.get('spellcasting', {})))

    def to_dict(self):
        return {'name': self.name, 'controller': self.controller, 'init': self.init, 'mod': self.initMod,
                'hpMax': self._hpMax, 'hp': self._hp, 'ac': self._ac, 'private': self.isPrivate,
                'resists': self.resists, 'attacks': self._attacks, 'saves': self._saves, 'index': self.index,
                'notes': self.notes, 'effects': [e.to_dict() for e in self.get_effects()], 'group': self.group,
                'temphp': self.temphp, 'spellcasting': self.spellcasting.to_dict(), 'type': 'common'}

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
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

    def set_hp(self, new_hp):  # set hp before temp hp
        if self._temphp:
            self._hp = new_hp + self._temphp
        else:
            self._hp = new_hp

    def get_hp_str(self, private=False):
        """Returns a string representation of the combatant's HP."""
        hpStr = ''
        if self.temphp and self.temphp > 0:
            hp = self.hp - self.temphp
        else:
            hp = self.hp
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
        for k in ('resist', 'immune', 'vuln'):
            if not k in self._resists:
                self._resists[k] = []
        return self._resists

    @property
    def attacks(self):
        return self.attack_effects(self._attacks)

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

    @property
    def spellcasting(self):
        return self._spellcasting

    def add_effect(self, effect):
        self._effects.append(effect)

    def get_effects(self):
        return self._effects

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

    def remove_all_effects(self):
        self._effects = []

    def attack_effects(self, attacks):
        at = copy.deepcopy(attacks)
        b = self.active_effects('b')
        d = self.active_effects('d')
        for a in at:
            if a['attackBonus'] is not None and b:
                a['attackBonus'] += f" + {'+'.join(b)}"
            if a['damage'] is not None and d:
                a['damage'] += f" + {'+'.join(d)}"
        return at

    def active_effects(self, key=None):
        if 'parsed_effects' not in self._cache:
            parsed_effects = {}
            for effect in self.get_effects():
                for k, v in effect.effect.items():
                    if k not in parsed_effects:
                        parsed_effects[k] = []
                    parsed_effects[k].append(v)
            self._cache['parsed_effects'] = parsed_effects
        if key:
            return self._cache['parsed_effects'].get(key, [])
        return self._cache['parsed_effects']

    def controller_mention(self):
        return f"<@{self.controller}>"

    def can_cast(self, spell, level) -> bool:
        """
        Checks whether a combatant can cast a certain spell at a certain level.
        :param spell: The spell to check.
        :param level: The level to cast it at.
        :return: Whether the combatant can cast the spell.
        """
        return spell['name'].lower() in [s.lower() for s in
                                         self.spellcasting.spells]  # TODO: care about monster slots

    def cast(self, spell, level):
        """
        Casts a spell at a certain level, using the necessary resources.
        :param spell: The spell
        :param level: The level
        :return: None
        """
        pass  # again, don't care about monsters

    def remaining_casts_of(self, spell, level):
        """
        Gets the string representing how many more times this combatant can cast this spell.
        :param spell: The spell
        :param level: The level
        """
        return "Slots are not yet tracked for non-player combatants."

    def on_turn(self, num_turns=1):
        """
        A method called at the start of each of the combatant's turns.
        :param num_turns: The number of turns that just passed.
        :return: None
        """
        for e in self.get_effects().copy():
            if e.on_turn(num_turns):
                self.remove_effect(e)

    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        hpStr = f"{self.get_hp_str(private)} " if self.get_hp_str(private) else ''
        if not no_notes:
            return f"{self.init}: {self.name} {hpStr}({self.get_effects_and_notes()})"
        else:
            return f"{self.init}: {self.name} {hpStr}"

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        csFormat = "{} {} {}{}\n{}"
        status = csFormat.format(self.name,
                                 self.get_hp_and_ac(private),
                                 self.get_resist_string(private),
                                 '\n# ' + self.notes if self.notes else '',
                                 self.get_long_effects())
        return status

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
        out = ', '.join(out)
        return out

    def get_hp_and_ac(self, private: bool = False):
        out = [self.get_hp_str(private)]
        if self.ac is not None and (not self.isPrivate or private):
            out.append("(AC {})".format(self.ac))
        return ' '.join(out)

    def get_resist_string(self, private: bool = False):
        resistStr = ''
        self._resists['resist'] = [r for r in self.resists['resist'] if r]  # clean empty resists
        self._resists['immune'] = [r for r in self.resists['immune'] if r]  # clean empty resists
        self._resists['vuln'] = [r for r in self.resists['vuln'] if r]  # clean empty resists
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
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx,
                 index=None, monster_name=None, notes=None, effects=None, group=None, temphp=None, spellcasting=None):
        super(MonsterCombatant, self).__init__(name, controllerId, init, initMod, hpMax, hp, ac, private, resists,
                                               attacks, saves, ctx, index, notes, effects, group, temphp, spellcasting)
        self._monster_name = monster_name

    @classmethod
    def from_monster(cls, name, controllerId, init, initMod, private, monster, ctx, opts=None, index=None, hp=None,
                     ac=None):
        monster_name = monster.name
        hp = int(monster.hp) if not hp else int(hp)
        ac = int(monster.ac) if not ac else int(ac)

        resist = monster.resist
        immune = monster.immume
        vuln = monster.vuln
        # fix npr and blug/pierc/slash
        if opts.get('npr'):
            if resist:
                resist = [r for r in resist if not any(t in r.lower() for t in ('bludgeoning', 'piercing', 'slashing'))]
            if immune:
                immune = [r for r in immune if not any(t in r.lower() for t in ('bludgeoning', 'piercing', 'slashing'))]
            if vuln:
                vuln = [r for r in vuln if not any(t in r.lower() for t in ('bludgeoning', 'piercing', 'slashing'))]
        for t in (resist, immune, vuln):
            for e in t:
                for d in ('bludgeoning', 'piercing', 'slashing'):
                    if d in e and not d == e.lower():
                        try:
                            t.remove(e)
                        except ValueError:
                            pass
                        t.append(d)

        resists = {'resist': resist, 'immune': immune, 'vuln': vuln}
        attacks = monster.attacks
        saves = monster.saves
        spellcasting = Spellcasting(monster.spellcasting.get('spells', []), monster.spellcasting.get('dc', 0),
                                    monster.spellcasting.get('attackBonus', 0),
                                    monster.spellcasting.get('casterLevel', 0))

        return cls(name, controllerId, init, initMod, hp, hp, ac, private, resists, attacks, saves, ctx, index,
                   monster_name, spellcasting=spellcasting)

    @classmethod
    def from_dict(cls, raw, ctx):
        inst = super(MonsterCombatant, cls).from_dict(raw, ctx)
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
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx,
                 index=None, character_id=None, character_owner=None, notes=None, effects=None, group=None,
                 temphp=None, spellcasting=None):
        super(PlayerCombatant, self).__init__(name, controllerId, init, initMod, hpMax, hp, ac, private, resists,
                                              attacks, saves, ctx, index, notes, effects, group, temphp, spellcasting)
        self.character_id = character_id
        self.character_owner = character_owner
        self._character = None  # shenanigans

    @classmethod
    async def from_character(cls, name, controllerId, init, initMod, ac, private, resists, ctx, character_id,
                             character_owner, char):
        inst = cls(name, controllerId, init, initMod, None, None, ac, private, resists, None, None, ctx,
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
        return self.attack_effects(self.character.get_attacks())

    @property
    def saves(self):
        return self.character.get_saves()

    @property
    def spellcasting(self):
        return Spellcasting(self.character.get_spell_list(), self.character.get_save_dc(),
                            self.character.get_spell_ab(), self.character.get_level())

    def can_cast(self, spell, level) -> bool:
        return self.character.get_remaining_slots(level) > 0 and spell['name'] in self.spellcasting.spells

    def cast(self, spell, level):
        self.character.use_slot(level)

    def remaining_casts_of(self, spell, level):
        return self.character.get_remaining_slots_str(level)

    @classmethod
    async def from_dict(cls, raw, ctx):
        inst = super(PlayerCombatant, cls).from_dict(raw, ctx)
        inst.character_id = raw['character_id']
        inst.character_owner = raw['character_owner']

        from cogs5e.models.character import Character
        inst._character = await Character.from_bot_and_ids(ctx.bot, inst.character_owner, inst.character_id)

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
        return self.ctx.message.author.id  # workaround

    @property
    def attacks(self):
        a = []
        for c in self.get_combatants():
            a.extend(c.attacks)
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
            status = f"{self.init}: {self.name} ({len(self.get_combatants())} combatants)"
        else:
            status = f"{self.init}: {self.name}"
            for c in self.get_combatants():
                status += f'\n    - {": ".join(c.get_summary(private, no_notes).split(": ")[1:])}'
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

    def on_remove(self):
        for c in self.get_combatants():
            c.on_remove()

    def controller_mention(self):
        return ", ".join({c.controller_mention() for c in self.get_combatants()})

    @classmethod
    async def from_dict(cls, raw, ctx):
        combatants = []
        for c in raw['combatants']:
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx))
            elif c['type'] == 'player':
                combatants.append(await PlayerCombatant.from_dict(c, ctx))
            else:
                raise CombatException("Unknown combatant type")
        return cls(raw['name'], raw['init'], combatants, ctx, raw['index'])

    def to_dict(self):
        return {'name': self.name, 'init': self.init, 'combatants': [c.to_dict() for c in self.get_combatants()],
                'index': self.index, 'type': 'group'}


class Effect:
    VALID_ARGS = {'b': 'Attack Bonus', 'd': 'Damage Bonus', 'ac': 'AC'}

    def __init__(self, name: str, duration: int, remaining: int, effect: dict):
        self._name = name
        self._duration = duration
        self._remaining = remaining
        self._effect = effect

    @classmethod
    def new(cls, name, duration, effect_args):
        if not isinstance(effect_args, ParsedArguments):
            effect_args = argparse(effect_args)
        effect_dict = {}
        for arg in cls.VALID_ARGS:
            if arg in effect_args:
                effect_dict[arg] = effect_args.last(arg)
        return cls(name, duration, duration, effect_dict)

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

    def __str__(self):
        desc = self.name
        if self.remaining >= 0:
            desc += f" [{self.remaining} rounds]"
        if self.effect:
            desc += f" ({self.get_effect_str()})"
        return desc

    def get_effect_str(self):
        return ', '.join(f"{self.VALID_ARGS.get(k)}: {v}" for k, v in self.effect.items())

    def on_turn(self, num_turns=1):
        """
        :return: Whether to remove the effect.
        """
        if self.remaining >= 0:
            if self.remaining - num_turns <= 0:
                return True
            self._remaining -= num_turns
        return False

    @classmethod
    def from_dict(cls, raw):
        return cls(raw['name'], raw['duration'], raw['remaining'], raw['effect'])

    def to_dict(self):
        return {'name': self.name, 'duration': self.duration, 'remaining': self.remaining, 'effect': self.effect}


class Spellcasting:
    def __init__(self, spells=None, dc=0, sab=0, casterLevel=0):
        if spells is None:
            spells = []
        self.spells = spells
        self.dc = dc
        self.sab = sab
        self.casterLevel = casterLevel

    @classmethod
    def from_dict(cls, spelldict):
        return cls(spelldict.get('spells', []), spelldict.get('dc', 0), spelldict.get('attackBonus', 0),
                   spelldict.get('casterLevel', 0))

    def to_dict(self):
        return {'spells': self.spells, 'dc': self.dc, 'attackBonus': self.sab, 'casterLevel': self.casterLevel}
