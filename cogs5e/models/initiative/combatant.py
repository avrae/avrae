import discord

from cogs5e.models.errors import NoCharacter
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistance, Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP, StatBlock
from gamedata.monster import MonsterCastableSpellbook
from utils.constants import RESIST_TYPES
from utils.functions import get_guild_member, maybe_mod, search_and_select
from .effect import Effect
from .errors import CombatException, RequiresContext
from .types import BaseCombatant
from .utils import CombatantType, create_combatant_id


class Combatant(BaseCombatant, StatBlock):
    DESERIALIZE_MAP = DESERIALIZE_MAP  # allow making class-specific deser maps
    type = CombatantType.GENERIC

    def __init__(self,
                 # init metadata
                 ctx, combat, id: str, name: str, controller_id: str, private: bool, init: int, index: int = None,
                 notes: str = None, effects: list = None, group_id: str = None,
                 # statblock info
                 stats: BaseStats = None, levels: Levels = None, attacks: AttackList = None,
                 skills: Skills = None, saves: Saves = None, resistances: Resistances = None,
                 spellbook: Spellbook = None, ac: int = None, max_hp: int = None, hp: int = None, temp_hp: int = 0,
                 **_):
        super().__init__(
            name=name, stats=stats, levels=levels, attacks=attacks, skills=skills, saves=saves, resistances=resistances,
            spellbook=spellbook,
            ac=ac, max_hp=max_hp, hp=hp, temp_hp=temp_hp
        )
        if effects is None:
            effects = []
        self.ctx = ctx
        self.combat = combat
        self.id = id

        self._controller = controller_id
        self._init = init
        self._private = private
        self._index = index  # combat write only; position in combat
        self._notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    @classmethod
    def new(cls, name: str, controller_id: str, init: int, init_skill: Skill, max_hp: int, ac: int, private: bool,
            resists: Resistances, ctx, combat):
        skills = Skills.default()
        skills.update({"initiative": init_skill})
        levels = Levels({"Monster": 0})
        id = create_combatant_id()
        return cls(ctx, combat, id, name, controller_id, private, init,
                   levels=levels, resistances=resists, skills=skills, max_hp=max_hp, ac=ac)

    @classmethod
    def from_dict(cls, raw, ctx, combat):
        for key, klass in cls.DESERIALIZE_MAP.items():
            if key in raw:
                raw[key] = klass.from_dict(raw[key])
        del raw['type']
        effects = raw.pop('effects')

        if 'id' not in raw:  # fixme id translator, remove apr 2021
            raw['id'] = create_combatant_id()

        inst = cls(ctx, combat, **raw)
        inst._effects = [Effect.from_dict(e, combat, inst) for e in effects]
        return inst

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'controller_id': self.controller, 'init': self.init, 'private': self.is_private,
            'index': self.index, 'notes': self.notes, 'effects': [e.to_dict() for e in self._effects],
            'group_id': self._group_id, 'type': self.type.value, 'id': self.id
        })
        return d

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
        out = ''
        if not self.is_private or private:
            if self.max_hp is not None:
                out = f'<{self.hp}/{self.max_hp} HP>'
            elif self.hp is not None:
                out = f'<{self.hp} HP>'
            else:
                out = ''

            if self.temp_hp and self.temp_hp > 0:
                out += f' (+{self.temp_hp} temp)'
        elif self.max_hp is not None and self.max_hp > 0:
            ratio = self.hp / self.max_hp
            if ratio >= 1:
                out = "<Healthy>"
            elif 0.5 < ratio < 1:
                out = "<Injured>"
            elif 0.15 < ratio <= 0.5:
                out = "<Bloodied>"
            elif 0 < ratio <= 0.15:
                out = "<Critical>"
            elif ratio <= 0:
                out = "<Dead>"
        return out

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
        return self._group_id

    @group.setter
    def group(self, value):
        self._group_id = value

    @property
    def _effect_id_map(self):
        return {e.id: e for e in self._effects}

    def set_group(self, group_name):
        current = self.combat.current_combatant
        was_current = self is current \
                      or (current.type == CombatantType.GROUP and self in current and len(current) == 1)
        self.combat.remove_combatant(self, ignore_remove_hook=True)
        if isinstance(group_name, str) and group_name.lower() == 'none':
            group_name = None
        if group_name is None:
            self.combat.add_combatant(self)
            if was_current:
                self.combat.goto_turn(self, True)
            return None
        else:
            c_group = self.combat.get_group(group_name, create=self.init)
            c_group.add_combatant(self)
            if was_current:
                self.combat.goto_turn(self, True)
            return c_group

    # effects
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

    def effect_by_id(self, effect_id):
        return self._effect_id_map.get(effect_id)

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
        return await search_and_select(self.ctx, self.get_effects(), name, lambda e: e.name)

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

    # controller stuff
    def controller_mention(self):
        return f"<@{self.controller}>"

    async def message_controller(self, ctx, *args, **kwargs):
        """Sends a message to the combatant's controller."""
        if ctx.guild is None:
            raise RequiresContext("message_controller requires a guild context.")
        member = await get_guild_member(ctx.guild, int(self.controller))
        if member is None:  # member is not in the guild, oh well
            return
        try:
            await member.send(*args, **kwargs)
        except discord.Forbidden:  # member is not accepting PMs from us, oh well
            pass

    # hooks
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

    def on_remove(self):
        """
        Called when the combatant is removed from combat, either through !i remove or the combat ending.
        """
        pass

    # stringification
    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        hpStr = f"{self.hp_str(private)} " if self.hp_str(private) else ''
        if not no_notes:
            return f"{self.init:>2}: {self.name} {hpStr}{self._get_effects_and_notes()}"
        else:
            return f"{self.init:>2}: {self.name} {hpStr}"

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        name = self.name
        hp_ac = self._get_hp_and_ac(private)
        resists = self._get_resist_string(private)
        notes = '\n# ' + self.notes if self.notes else ''
        effects = self._get_long_effects()
        return f"{name} {hp_ac} {resists}{notes}\n{effects}".strip()

    def _get_long_effects(self):
        return '\n'.join(f"* {str(e)}" for e in self.get_effects())

    def _get_effects_and_notes(self):
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

    def _get_hp_and_ac(self, private: bool = False):
        out = [self.hp_str(private)]
        if self.ac is not None and (not self.is_private or private):
            out.append("(AC {})".format(self.ac))
        return ' '.join(out)

    def _get_resist_string(self, private: bool = False):
        resist_str = ''
        if not self.is_private or private:
            if len(self.resistances.resist) > 0:
                resist_str += "\n> Resistances: " + ', '.join([str(r) for r in self.resistances.resist])
            if len(self.resistances.immune) > 0:
                resist_str += "\n> Immunities: " + ', '.join([str(r) for r in self.resistances.immune])
            if len(self.resistances.vuln) > 0:
                resist_str += "\n> Vulnerabilities: " + ', '.join([str(r) for r in self.resistances.vuln])
        return resist_str

    def __str__(self):
        return f"{self.name}: {self.hp_str()}".strip()

    def __hash__(self):
        return hash(f"{self.combat.channel}.{self.name}")


class MonsterCombatant(Combatant):
    DESERIALIZE_MAP = {**DESERIALIZE_MAP, "spellbook": MonsterCastableSpellbook}
    type = CombatantType.MONSTER

    def __init__(self,
                 # init metadata
                 ctx, combat, id: str, name: str, controller_id: str, private: bool, init: int, index: int = None,
                 notes: str = None, effects: list = None, group_id: str = None,
                 # statblock info
                 stats: BaseStats = None, levels: Levels = None, attacks: AttackList = None,
                 skills: Skills = None, saves: Saves = None, resistances: Resistances = None,
                 spellbook: Spellbook = None,
                 ac: int = None, max_hp: int = None, hp: int = None, temp_hp: int = 0,
                 # monster specific
                 monster_name=None, monster_id=None,
                 **_):
        super(MonsterCombatant, self).__init__(
            ctx, combat, id, name, controller_id, private, init, index, notes, effects, group_id,
            stats, levels, attacks, skills, saves, resistances, spellbook, ac, max_hp, hp, temp_hp)
        self._monster_name = monster_name
        self._monster_id = monster_id

    @classmethod
    def from_monster(cls, monster, ctx, combat, name, controller_id, init, private, hp=None, ac=None):
        monster_name = monster.name
        hp = int(monster.hp) if not hp else int(hp)
        ac = int(monster.ac) if not ac else int(ac)
        id = create_combatant_id()

        # copy spellbook
        spellbook = None
        if monster.spellbook is not None:
            spellbook = MonsterCastableSpellbook.copy(monster.spellbook)

        # copy resistances (#1134)
        resistances = monster.resistances.copy()

        return cls(ctx, combat, id, name, controller_id, private, init,
                   # statblock info
                   stats=monster.stats, levels=monster.levels, attacks=monster.attacks,
                   skills=monster.skills, saves=monster.saves, resistances=resistances,
                   spellbook=spellbook, ac=ac, max_hp=hp,
                   # monster specific
                   monster_name=monster_name, monster_id=monster.entity_id)

    # ser/deser
    @classmethod
    def from_dict(cls, raw, ctx, combat):
        inst = super().from_dict(raw, ctx, combat)
        inst._monster_name = raw['monster_name']
        inst._monster_id = raw.get('monster_id')
        return inst

    def to_dict(self):
        raw = super().to_dict()
        raw.update({
            'monster_name': self._monster_name, 'monster_id': self._monster_id
        })
        return raw

    # members
    @property
    def monster_name(self):
        return self._monster_name


class PlayerCombatant(Combatant):
    type = CombatantType.PLAYER

    def __init__(self,
                 # init metadata
                 ctx, combat, id: str, name: str, controller_id: str, private: bool, init: int, index: int = None,
                 notes: str = None, effects: list = None, group_id: str = None,
                 # statblock info
                 attacks: AttackList = None, resistances: Resistances = None,
                 ac: int = None, max_hp: int = None,
                 # character specific
                 character_id=None, character_owner=None,
                 **_):
        # note that the player combatant doesn't initialize the statblock
        # because we want the combatant statblock attrs to reference the character attrs
        super().__init__(
            ctx, combat, id, name, controller_id, private, init, index, notes, effects, group_id,
            attacks=attacks, resistances=resistances, ac=ac, max_hp=max_hp
        )
        self.character_id = character_id
        self.character_owner = character_owner

        self._character = None  # cache

    @classmethod
    async def from_character(cls, character, ctx, combat, controller_id, init, private):
        id = create_combatant_id()
        inst = cls(ctx, combat, id, character.name, controller_id, private, init,
                   # statblock copies
                   resistances=character.resistances.copy(),
                   # character specific
                   character_id=character.upstream, character_owner=character.owner)
        inst._character = character
        return inst

    # ==== serialization ====
    @classmethod
    async def from_dict(cls, raw, ctx, combat):
        inst = super().from_dict(raw, ctx, combat)
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
        inst = super().from_dict(raw, ctx, combat)
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
        raw = super().to_dict()
        for attr in IGNORED_ATTRIBUTES:
            del raw[attr]
        raw.update({
            'character_id': self.character_id, 'character_owner': self.character_owner
        })
        return raw

    # members
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

    def get_color(self):
        return self.character.get_color()
