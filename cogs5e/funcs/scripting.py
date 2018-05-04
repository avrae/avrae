import re

from cogs5e.funcs.dice import roll
from cogs5e.models.errors import CombatNotFound
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup

SCRIPTING_RE = re.compile(r'(?<!\\)(?:(?:{{(.+?)}})|(?:<([^\s]+)>)|(?:(?<!{){(.+?)}))')


def simple_roll(rollStr):
    return roll(rollStr).total


class SimpleRollResult:
    def __init__(self, dice, total, full, raw):
        self.dice = dice.strip()
        self.total = total
        self.full = full.strip()
        self.raw = raw

    def __str__(self):
        return self.full


def verbose_roll(rollStr):
    rolled = roll(rollStr, inline=True)
    return SimpleRollResult(rolled.rolled, rolled.total, rolled.skeleton,
                            [part.to_dict() for part in rolled.raw_dice.parts])


class SimpleCombat:
    def __init__(self, combat, me):
        self._combat: Combat = combat

        self.combatants = [SimpleCombatant(c) for c in self._combat.get_combatants()]
        self.current = SimpleCombatant(self._combat.current_combatant) if isinstance(
            self._combat.current_combatant, Combatant) else SimpleGroup(self._combat.current_combatant)
        self.me = SimpleCombatant(me, True)
        self.round_num = self._combat.round_num
        self.turn_num = self._combat.turn_num

    @classmethod
    def from_character(cls, character, ctx):
        try:
            combat = Combat.from_ctx(ctx)
        except CombatNotFound:
            return None
        me = next((c for c in combat.get_combatants() if getattr(c, 'character_id', None) == character.id), None)
        if not me:
            return None
        return cls(combat, me)

    # public methods
    def get_combatant(self, name):
        return self._combat.get_combatant(name, False)

    def get_group(self, name):
        return self._combat.get_group(name)

    # private functions
    def func_commit(self):
        self._combat.commit()


class SimpleCombatant:
    def __init__(self, combatant: Combatant, hidestats=False):
        self._combatant = combatant
        self._hidden = not hidestats and self._combatant.isPrivate

        if self._hidden:
            self.ac = self._combatant.ac
            self.hp = self._combatant.hp
            self.maxhp = self._combatant.hpMax
            self.initmod = self._combatant.initMod
        else:
            self.ac = None
            self.hp = None
            self.maxhp = None
            self.initmod = None
        self.init = self._combatant.init
        self.name = self._combatant.name
        self.note = self._combatant.notes

    def set_hp(self, newhp: int):
        self._combatant.hp = int(newhp)

    def mod_hp(self, mod: int):
        self._combatant.hp += int(mod)


class SimpleGroup:
    def __init__(self, group: CombatantGroup):
        self._group = group

    def get_combatant(self, name):
        return next((c for c in self._group.get_combatants() if name.lower() in c.name.lower()), None)
