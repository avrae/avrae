import copy
import shlex

import cachetools

from cogs5e.funcs.dice import roll
from cogs5e.models.character import Character
from cogs5e.models.errors import CombatException, CombatNotFound, RequiresContext, ChannelInCombat, \
    CombatChannelNotFound, NoCombatants
from utils.functions import get_selection, parse_args_3

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
    def from_ctx(cls, ctx):
        raw = ctx.bot.db.jget(f"{ctx.message.channel.id}.combat")
        if raw is None:
            raise CombatNotFound
        return cls.from_dict(raw, ctx)

    @classmethod
    def from_dict(cls, raw, ctx):
        combatants = []
        for c in raw['combatants']:
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx))
            elif c['type'] == 'player':
                combatants.append(PlayerCombatant.from_dict(c, ctx))
            elif c['type'] == 'group':
                combatants.append(CombatantGroup.from_dict(c, ctx))
            else:
                raise CombatException("Unknown combatant type")
        return cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, combatants, raw['round'],
                   raw['turn'], raw['current'])

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
        return next(c for c in self._combatants if c.index == self.index) if self.index is not None else None

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

    def remove_combatant(self, combatant):
        if not combatant.group:
            self._combatants.remove(combatant)
            self.sort_combatants()
        else:
            self.get_group(combatant.group).remove_combatant(combatant)
            self.check_empty_groups()

    def sort_combatants(self):
        current = self.current_combatant
        self._combatants = sorted(self._combatants, key=lambda k: (k.init, k.initMod), reverse=True)
        for n, c in enumerate(self._combatants):
            c.index = n
        self._current_index = current.index if current is not None else None

    def get_combatant(self, name):
        return next((c for c in self.get_combatants() if c.name == name), None)

    def get_group(self, name, create=None):
        """
        Gets a combatant group.
        :rtype: CombatantGroup
        :param name: The name of the combatant group.
        :param create: The initiaitve to create a group at if a group is not found.
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

    @staticmethod
    def ensure_unique_chan(ctx):
        if ctx.bot.db.exists(f"{ctx.message.channel.id}.combat"):
            raise ChannelInCombat

    def get_db_key(self):
        return f"{self.channel}.combat"

    def commit(self):
        """Commits the combat to db."""
        if not self.ctx:
            raise RequiresContext
        self.ctx.bot.db.jsetex(self.get_db_key(), self.to_dict(), COMBAT_TTL)

    def get_summary(self, private=False):
        """Returns the generated summary message content."""
        combatants = sorted(self._combatants, key=lambda k: (k.init, k.initMod), reverse=True)
        outStr = "```markdown\n{}: {} (round {})\n".format(
            self.options.get('name') if self.options.get('name') else "Current initiative",
            self.turn_num, self.round_num)
        outStr += '=' * (len(outStr) - 13)
        outStr += '\n'
        for c in combatants:
            outStr += ("# " if self.index == c.index else "  ") + c.get_summary(private) + "\n"
        outStr += "```"
        return outStr

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
        self.commit()
        await self.update_summary()

    def end(self):
        """Ends combat in a channel."""
        for c in self._combatants:
            c.on_remove()
        self.ctx.bot.db.delete(self.get_db_key())


class Combatant:
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx,
                 index=None, notes=None, effects=None, group=None, *args, **kwargs):
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
        self._notes = notes
        self._effects = effects
        self._group = group

    @classmethod
    def new(cls, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx):
        return cls(name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, saves, ctx)

    @classmethod
    def from_dict(cls, raw, ctx):
        effects = [Effect.from_dict(e) for e in raw['effects']]
        return cls(raw['name'], raw['controller'], raw['init'], raw['mod'], raw['hpMax'], raw['hp'], raw['ac'],
                   raw['private'], raw['resists'], raw['attacks'], raw['saves'], ctx, index=raw['index'],
                   notes=raw['notes'], effects=effects, group=raw['group'])

    def to_dict(self):
        return {'name': self.name, 'controller': self.controller, 'init': self.init, 'mod': self.initMod,
                'hpMax': self._hpMax, 'hp': self._hp, 'ac': self._ac, 'private': self.isPrivate,
                'resists': self.resists, 'attacks': self._attacks, 'saves': self._saves, 'index': self.index,
                'notes': self.notes, 'effects': [e.to_dict() for e in self.get_effects()], 'group': self.group,
                'type': 'common'}

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
    def hp(self, new_hp):
        self._hp = new_hp

    def get_hp_str(self, private=False):
        """Returns a string representation of the combatant's HP."""
        hpStr = ''
        if not self.isPrivate or private:
            hpStr = '<{}/{} HP>'.format(self.hp, self.hpMax) if self.hpMax is not None else '<{} HP>'.format(
                self.hp) if self.hp is not None else ''
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
    def ac(self):
        return self._ac

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
        to_parse = ''
        for e in self.get_effects():
            if e.effect:
                to_parse += f' {e.effect}'
        args = parse_args_3(shlex.split(to_parse))
        for a in at:
            if a['attackBonus'] is not None:
                a['attackBonus'] += f' + {"+".join(args["b"])}' if 'b' in args else ''
            if a['damage'] is not None:
                a['damage'] += f' + {"+".join(args["d"])}' if 'd' in args else ''
        return at

    def controller_mention(self):
        return f"<@{self.controller}>"

    def on_turn(self):
        """
        A method called at the start of each of the combatant's turns.
        :return: None
        """
        for e in self.get_effects():
            if e.on_turn():
                self.remove_effect(e)

    def get_summary(self, private=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        status = "{}: {} {}({})".format(self.init,
                                        self.name,
                                        self.get_hp_str(private) + ' ' if self.get_hp_str() is not '' else '',
                                        self.get_effects_and_notes())
        return status

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        csFormat = "{} {} {}{}{}"
        status = csFormat.format(self.name,
                                 self.get_hp_and_ac(private),
                                 self.get_resist_string(private),
                                 '\n# ' + self.notes if self.notes else '',
                                 self.get_long_effects())
        return status

    def get_long_effects(self):
        out = ''
        for e in self.get_effects():
            edesc = e.name
            if e.remaining >= 0:
                edesc += " [{} rounds]".format(e.remaining)
            if getattr(e, 'effect', None):
                edesc += " ({})".format(e.effect)
            out += '\n* ' + edesc
        return out

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
                 index=None, monster_name=None, notes=None, effects=None, group=None):
        super(MonsterCombatant, self).__init__(name, controllerId, init, initMod, hpMax, hp, ac, private, resists,
                                               attacks, saves, ctx, index, notes, effects, group)
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
            for t in (resist, immune, vuln):
                for e in t:
                    for d in ('bludgeoning', 'piercing', 'slashing'):
                        if d in e.lower(): t.remove(e)
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

        return cls(name, controllerId, init, initMod, hp, hp, ac, private, resists, attacks, saves, ctx, index,
                   monster_name)

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
                 index=None, character_id=None, character_owner=None, notes=None, effects=None, group=None):
        super(PlayerCombatant, self).__init__(name, controllerId, init, initMod, hpMax, hp, ac, private, resists,
                                              attacks, saves, ctx, index, notes, effects, group)
        self._character_id = character_id
        self._character_owner = character_owner
        self._character = None  # only grab the Character instance if we have to

    @classmethod
    def from_character(cls, name, controllerId, init, initMod, ac, private, resists, ctx, character_id,
                       character_owner):
        return cls(name, controllerId, init, initMod, None, None, ac, private, resists, None, None, ctx,
                   character_id=character_id, character_owner=character_owner)

    @property
    def character(self):
        if self._character is None:
            c = Character.from_bot_and_ids(self.ctx.bot, self._character_owner, self._character_id)

            def new_commit(ctx):
                c.manual_commit(ctx.bot, self._character_owner)

            c.commit = new_commit
            self._character = c
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
        self.character.set_hp(new_hp).commit(self.ctx)

    @property
    def attacks(self):
        return self.attack_effects(self.character.get_attacks())

    @property
    def saves(self):
        return self.character.get_saves()

    def on_remove(self):
        super(PlayerCombatant, self).on_remove()
        self.character.leave_combat().commit(self.ctx)

    @classmethod
    def from_dict(cls, raw, ctx):
        inst = super(PlayerCombatant, cls).from_dict(raw, ctx)
        inst._character_id = raw['character_id']
        inst._character_owner = raw['character_owner']
        return inst

    def to_dict(self):
        raw = super(PlayerCombatant, self).to_dict()
        raw['character_id'] = self._character_id
        raw['character_owner'] = self._character_owner
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

    def get_summary(self, private=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        if len(self._combatants) > 7 and not private:
            status = f"{self.init}: {self.name} ({len(self.get_combatants())} combatants)"
        else:
            status = f"{self.init}: {self.name}"
            for c in self.get_combatants():
                status += f'\n    - {": ".join(c.get_summary(private).split(": ")[1:])}'
        return status

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        return '\n'.join(c.get_status(private) for c in self.get_combatants())

    def on_turn(self):
        for c in self.get_combatants():
            c.on_turn()

    def on_remove(self):
        for c in self.get_combatants():
            c.on_remove()

    def controller_mention(self):
        return ", ".join({c.controller_mention() for c in self.get_combatants()})

    @classmethod
    def from_dict(cls, raw, ctx):
        combatants = []
        for c in raw['combatants']:
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx))
            elif c['type'] == 'monster':
                combatants.append(MonsterCombatant.from_dict(c, ctx))
            elif c['type'] == 'player':
                combatants.append(PlayerCombatant.from_dict(c, ctx))
            else:
                raise CombatException("Unknown combatant type")
        return cls(raw['name'], raw['init'], combatants, ctx, raw['index'])

    def to_dict(self):
        return {'name': self.name, 'init': self.init, 'combatants': [c.to_dict() for c in self.get_combatants()],
                'index': self.index, 'type': 'group'}


class Effect:
    def __init__(self, name, duration, remaining, effect):
        self._name = name
        self._duration = duration
        self._remaining = remaining
        self._effect = effect

    @classmethod
    def new(cls, name, duration, effect):
        return cls(name, duration, duration, effect)

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

    def on_turn(self):
        """
        :return: Whether to remove the effect.
        """
        if self.remaining > 0:
            self._remaining -= 1
        if self.remaining == 0:
            return True
        return False

    @classmethod
    def from_dict(cls, raw):
        return cls(raw['name'], raw['duration'], raw['remaining'], raw['effect'])

    def to_dict(self):
        return {'name': self.name, 'duration': self.duration, 'remaining': self.remaining, 'effect': self.effect}
