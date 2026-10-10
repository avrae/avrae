from functools import cached_property

from aliasing.api.statblock import (
    AliasAttackList,
    AliasBaseStats,
    AliasLevels,
    AliasResistances,
    AliasSaves,
    AliasSkills,
    AliasSpellbookSpell,
)
from cogs5e.models.sheet.statblock import StatBlock


def wrap_target(value):
    """Wrap an automation target, preserving placeholder statblock behavior for string/None targets."""
    if isinstance(value, (str, type(None))):
        return AutomationStatBlock(StatBlock(name=value or "Target"))
    return wrap_statblock(value)


def wrap_statblock(statblock):
    """Return the correct automation wrapper for the given actor-like object."""

    # Deferred to avoid a circular dependency with Character and Combatant.
    from cogs5e.initiative.combatant import Combatant, PlayerCombatant
    from cogs5e.initiative.group import CombatantGroup
    from cogs5e.models.character import Character

    if isinstance(statblock, CombatantGroup):
        return AutomationGroup(statblock)
    if isinstance(statblock, PlayerCombatant):
        return AutomationCharacter(statblock.character, combatant=statblock)
    if isinstance(statblock, Character):
        return AutomationCharacter(statblock)
    if isinstance(statblock, Combatant):
        return AutomationCombatant(statblock)
    if isinstance(statblock, StatBlock):
        return AutomationStatBlock(statblock)
    raise TypeError(f"Unsupported automation statblock type: {type(statblock).__name__}")


class AutomationStatBlock:
    def __init__(self, statblock: StatBlock):
        self._statblock = statblock
        self._stats = None
        self._levels = None
        self._attacks = None
        self._skills = None
        self._saves = None
        self._resistances = None
        self._spellbook = None

    @property
    def name(self):
        return self._statblock.name

    @property
    def stats(self):
        if self._stats is None:
            self._stats = AliasBaseStats(self._statblock.stats)
        return self._stats

    @property
    def levels(self):
        if self._levels is None:
            self._levels = AliasLevels(self._statblock.levels)
        return self._levels

    @property
    def attacks(self):
        if self._attacks is None:
            self._attacks = AliasAttackList(self._statblock.attacks, self._statblock)
        return self._attacks

    @property
    def skills(self):
        if self._skills is None:
            self._skills = AliasSkills(self._statblock.skills)
        return self._skills

    @property
    def saves(self):
        if self._saves is None:
            self._saves = AliasSaves(self._statblock.saves)
        return self._saves

    @property
    def resistances(self):
        if self._resistances is None:
            self._resistances = AliasResistances(self._statblock.resistances)
        return self._resistances

    @property
    def ac(self):
        return self._statblock.ac

    @property
    def max_hp(self):
        return self._statblock.max_hp

    @property
    def hp(self):
        return self._statblock.hp

    @property
    def temp_hp(self):
        return self._statblock.temp_hp

    @property
    def spellbook(self):
        if self._spellbook is None:
            self._spellbook = AutomationSpellbook(self._statblock.spellbook)
        return self._spellbook

    @property
    def creature_type(self):
        return self._statblock.creature_type

    def hp_str(self):
        return self._statblock.hp_str()

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"


class AutomationCombatant(AutomationStatBlock):
    def __init__(self, statblock):
        super().__init__(statblock)
        self._combatant = statblock

    @property
    def id(self):
        return self._combatant.id

    @property
    def note(self):
        return self._combatant.notes

    @property
    def controller(self):
        return self._combatant.controller_id

    @property
    def group(self):
        group = self._combatant.get_group()
        return group.name if group else None

    @property
    def is_hidden(self):
        return bool(self._combatant.is_private)

    @property
    def monster_name(self):
        return getattr(self._combatant, "monster_name", None)

    @property
    def monster_id(self):
        return getattr(self._combatant, "monster_id", None)

    @cached_property
    def effects(self):
        return [AutomationEffect(effect) for effect in self._combatant.get_effects()]

    def get_effect(self, name: str, strict: bool = False):
        effect = self._combatant.get_effect(str(name), strict)
        if effect:
            return AutomationEffect(effect)
        return None


class AutomationCharacter(AutomationCombatant):
    def __init__(self, character, combatant=None):
        AutomationStatBlock.__init__(self, combatant or character)
        self._character = character
        self._combatant = combatant
        self._in_combat = combatant is not None

    @property
    def owner(self):
        return self._character.owner

    @property
    def upstream(self):
        return self._character.upstream

    @property
    def sheet_type(self):
        return self._character.sheet_type

    @property
    def race(self):
        return self._character.race

    @property
    def background(self):
        return self._character.background

    @property
    def csettings(self):
        return self._character.options.dict()

    @property
    def description(self):
        return self._character.description

    @property
    def image(self):
        return self._character.image

    @property
    def id(self):
        if not self._in_combat:
            return None
        return super().id

    @property
    def note(self):
        if not self._in_combat:
            return None
        return super().note

    @property
    def controller(self):
        if not self._in_combat:
            return None
        return super().controller

    @property
    def group(self):
        if not self._in_combat:
            return None
        return super().group

    @property
    def is_hidden(self):
        if not self._in_combat:
            return False
        return super().is_hidden

    @cached_property
    def effects(self):
        if not self._in_combat:
            return []
        return super().effects

    def get_effect(self, name: str, strict: bool = False):
        if not self._in_combat:
            return None
        return super().get_effect(name, strict)


class AutomationSpellbook:
    def __init__(self, spellbook):
        self._spellbook = spellbook
        self._spells = None

    @property
    def dc(self):
        return self._spellbook.dc

    @property
    def sab(self):
        return self._spellbook.sab

    @property
    def caster_level(self):
        return self._spellbook.caster_level

    @property
    def spell_mod(self):
        return self._spellbook.spell_mod

    @property
    def spells(self):
        if self._spells is None:
            self._spells = [AliasSpellbookSpell(spell) for spell in self._spellbook.spells]
        return self._spells

    @property
    def pact_slot_level(self):
        return self._spellbook.pact_slot_level

    @property
    def num_pact_slots(self):
        return self._spellbook.num_pact_slots

    @property
    def max_pact_slots(self):
        return self._spellbook.max_pact_slots

    def find(self, spell_name: str):
        if self._spells is None:
            self._spells = [AliasSpellbookSpell(spell) for spell in self._spellbook.spells]
        return [spell for spell in self._spells if spell_name.lower() == spell.name.lower()]

    def slots_str(self, level):
        return self._spellbook.slots_str(int(level))

    def get_max_slots(self, level):
        return self._spellbook.get_max_slots(int(level))

    def get_slots(self, level):
        return self._spellbook.get_slots(int(level))

    def remaining_casts_of(self, spell, level):
        the_spell = _SpellProxy(str(spell), int(level))
        return self._spellbook.remaining_casts_of(the_spell, int(level))

    def can_cast(self, spell, level):
        the_spell = _SpellProxy(str(spell), int(level))
        return self._spellbook.can_cast(the_spell, int(level))

    def __contains__(self, item):
        return str(item) in self._spellbook


class AutomationGroup:
    def __init__(self, group):
        self._group = group
        self.combatants = [wrap_statblock(combatant) for combatant in self._group.get_combatants()]
        self.init = self._group.init

    @property
    def name(self):
        return self._group.name

    @property
    def id(self):
        return self._group.id

    def get_combatant(self, name, strict=None):
        name = str(name)
        combatant = None
        if strict is not False:
            combatant = next((c for c in self.combatants if name.lower() == c.name.lower()), None)
        if not combatant and not strict:
            combatant = next((c for c in self.combatants if name.lower() in c.name.lower()), None)
        return combatant

    def __repr__(self):
        return f"<{self.__class__.__name__} combatants={self.combatants!r}>"


class AutomationCombat:
    def __init__(self, combat):
        self._combat = combat
        self.combatants = [wrap_statblock(combatant) for combatant in combat.get_combatants()]
        self.groups = [wrap_statblock(group) for group in combat.get_groups()]
        self.round_num = self._combat.round_num
        self.turn_num = self._combat.turn_num
        current = self._combat.current_combatant
        self.current = wrap_statblock(current) if current else None
        self.name = self._combat.options.name

    def get_combatant(self, name, strict=None):
        combatant = self._combat.get_combatant(str(name), strict)
        return wrap_statblock(combatant) if combatant else None

    def get_group(self, name, strict=None):
        group = self._combat.get_group(str(name), strict)
        return wrap_statblock(group) if group else None

    def get_metadata(self, key: str, default=None) -> str:
        return self._combat.metadata.get(str(key), default)

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


class AutomationEffect:
    def __init__(self, effect):
        self._effect = effect
        self.name = self._effect.name
        self.duration = self._effect.duration
        self.remaining = self._effect.remaining
        self.effect = self._effect.effects.to_dict()
        self.attacks = [interaction.to_dict() for interaction in self._effect.attacks]
        self.buttons = [interaction.to_dict() for interaction in self._effect.buttons]
        self.conc = self._effect.concentration
        self.desc = self._effect.desc
        self.ticks_on_end = self._effect.end_on_turn_end
        self.combatant_name = self._effect.combatant.name if self._effect.combatant is not None else None
        self._parent = None
        self._children = None

    @property
    def parent(self):
        if self._parent is None:
            the_parent = self._effect.parent
            if the_parent is not None:
                self._parent = AutomationEffect(self._effect.get_parent_effect())
        return self._parent

    @property
    def children(self):
        if self._children is None:
            self._children = [AutomationEffect(effect) for effect in self._effect.get_children_effects()]
        return self._children

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} duration={self.duration!r} remaining={self.remaining!r}>"

    def __eq__(self, other):
        return isinstance(other, AutomationEffect) and self._effect is other._effect


class _SpellProxy:
    def __init__(self, name, level):
        self.name = name
        self.level = level
