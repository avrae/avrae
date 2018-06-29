import ast
import json
import re
from math import floor, ceil, sqrt

import simpleeval
from simpleeval import EvalWithCompoundTypes, IterableTooLong

from cogs5e.funcs.dice import roll
from cogs5e.models.errors import CombatNotFound, InvalidSaveType
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup

SCRIPTING_RE = re.compile(r'(?<!\\)(?:(?:{{(.+?)}})|(?:<([^\s]+)>)|(?:(?<!{){(.+?)}))')
MAX_ITER_LENGTH = 10000


class ScriptingEvaluator(EvalWithCompoundTypes):
    def __init__(self, operators=None, functions=None, names=None):
        super(ScriptingEvaluator, self).__init__(operators, functions, names)

        self.nodes.update({
            ast.JoinedStr: self._eval_joinedstr,  # f-string
            ast.FormattedValue: self._eval_formattedvalue,  # things in f-strings
            ast.ListComp: self._eval_listcomp,
            ast.SetComp: self._eval_setcomp,
            ast.DictComp: self._eval_dictcomp,
            ast.comprehension: self._eval_comprehension
        })

    def eval(self, expr):  # allow for ast.Assign to set names
        """ evaluate an expression, using the operators, functions and
            names previously set up. """

        # set a copy of the expression aside, so we can give nice errors...

        self.expr = expr

        # and evaluate:
        expression = ast.parse(expr.strip()).body[0]
        if isinstance(expression, ast.Expr):
            return self._eval(expression.value)
        elif isinstance(expression, ast.Assign):
            return self._eval_assign(expression)
        else:
            raise TypeError("Unknown ast body type")

    def _eval_assign(self, node):
        names = node.targets[0]
        values = node.value
        self._assign(names, values)

    def _assign(self, names, values, eval_values=True):
        if isinstance(names, ast.Tuple):  # unpacking variables
            names = [n.id for n in names.elts]  # turn ast into str
            if not isinstance(values, ast.Tuple):
                raise ValueError(f"unequal unpack: {len(names)} names, 1 value")
            if eval_values:
                values = [self._eval(n) for n in values.elts]  # get what we actually want to assign
            else:
                values = values.elts
            if not len(values) == len(names):
                raise ValueError(f"unequal unpack: {len(names)} names, {len(values)} values")
            else:
                if not isinstance(self.names, dict):
                    raise TypeError("cannot set name: incorrect name type")
                else:
                    for name, value in zip(names, values):
                        self.names[name] = value  # and assign it
        else:
            if not isinstance(self.names, dict):
                raise TypeError("cannot set name: incorrect name type")
            else:
                if eval_values:
                    self.names[names.id] = self._eval(values)
                else:
                    self.names[names.id] = values

    def _eval_joinedstr(self, node):
        return ''.join(str(self._eval(n)) for n in node.values)

    def _eval_formattedvalue(self, node):
        if node.format_spec:
            fmt = "{:" + self._eval(node.format_spec) + "}"
            return fmt.format(self._eval(node.value))
        else:
            return self._eval(node.value)

    def _eval_listcomp(self, node):
        return list(self._eval(node.elt) for generator in node.generators for _ in self._eval(generator))

    def _eval_setcomp(self, node):
        return set(self._eval(node.elt) for generator in node.generators for _ in self._eval(generator))

    def _eval_dictcomp(self, node):
        return {self._eval(node.key): self._eval(node.value) for generator in node.generators for _ in
                self._eval(generator)}

    def _eval_comprehension(self, node):
        iterable = self._eval(node.iter)
        if len(iterable) > MAX_ITER_LENGTH:
            raise IterableTooLong("This iterable is too long.")
        for item in iterable:
            self._assign(node.target, item, False)
            if all(self._eval(stmt) for stmt in node.ifs):
                yield item


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


def safe_range(start, stop=None, step=None):
    if stop is None and step is None:
        if start > MAX_ITER_LENGTH:
            raise IterableTooLong("This range is too large.")
        return list(range(start))
    elif stop is not None and step is None:
        if stop - start > MAX_ITER_LENGTH:
            raise IterableTooLong("This range is too large.")
        return list(range(start, stop))
    elif stop is not None and step is not None:
        if (stop - start) / step > MAX_ITER_LENGTH:
            raise IterableTooLong("This range is too large.")
        return list(range(start, stop, step))
    else:
        raise ValueError("Invalid arguments passed to range()")


def load_json(jsonstr):
    return json.loads(jsonstr)


def dump_json(obj):
    return json.dumps(obj)


class SimpleCombat:
    def __init__(self, combat, me):
        self._combat: Combat = combat

        self.combatants = [SimpleCombatant(c) for c in self._combat.get_combatants()]
        self.current = SimpleCombatant(self._combat.current_combatant) if isinstance(
            self._combat.current_combatant, Combatant) else SimpleGroup(self._combat.current_combatant)
        self.me = SimpleCombatant(me, False)
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
        combatant = self._combat.get_combatant(name, False)
        if combatant:
            return SimpleCombatant(combatant)
        return None

    def get_group(self, name):
        group = self._combat.get_group(name)
        if group:
            return SimpleGroup(group)
        return None

    # private functions
    def func_commit(self):
        self._combat.commit()


class SimpleCombatant:
    def __init__(self, combatant: Combatant, hidestats=True):
        self._combatant = combatant
        self._hidden = hidestats and self._combatant.isPrivate

        if not self._hidden:
            self.ac = self._combatant.ac
            self.hp = self._combatant.hp - (self._combatant.temphp or 0)
            self.maxhp = self._combatant.hpMax
            self.initmod = self._combatant.initMod
            self.temphp = self._combatant.temphp
        else:
            self.ac = None
            self.hp = None
            self.maxhp = None
            self.initmod = None
            self.temphp = None
        self.init = self._combatant.init
        self.name = self._combatant.name
        self.note = self._combatant.notes
        if self._combatant.hp is not None and self._combatant.hpMax is not None:
            self.ratio = (self._combatant.hp - (self._combatant.temphp or 0)) / self._combatant.hpMax
        else:
            self.ratio = 0

    def set_hp(self, newhp: int):
        self._combatant.hp = int(newhp)

    def mod_hp(self, mod: int):
        self._combatant.hp += int(mod)

    def hp_str(self):
        return self._combatant.get_hp_str()

    def save(self, ability: str, adv: bool = None):
        try:
            save_skill = next(s for s in ('strengthSave', 'dexteritySave', 'constitutionSave',
                                          'intelligenceSave', 'wisdomSave', 'charismaSave') if
                              ability.lower() in s.lower())
        except StopIteration:
            raise InvalidSaveType
        save_roll_mod = self._combatant.saves.get(save_skill, 0)
        adv = 0 if adv is None else 1 if adv else -1
        save_roll = roll('1d20{:+}'.format(save_roll_mod), adv=adv,
                         rollFor='{} Save'.format(save_skill[:3].upper()), inline=True, show_blurbs=False)
        return SimpleRollResult(save_roll.rolled, save_roll.total, save_roll.skeleton,
                                [part.to_dict() for part in save_roll.raw_dice.parts])

    def wouldhit(self, to_hit: int):
        if self._combatant.ac:
            return to_hit >= self._combatant.ac
        return None


class SimpleGroup:
    def __init__(self, group: CombatantGroup):
        self._group = group

    def get_combatant(self, name):
        combatant = next((c for c in self._group.get_combatants() if name.lower() in c.name.lower()), None)
        if combatant:
            return SimpleCombatant(combatant)
        return None


DEFAULT_OPERATORS = simpleeval.DEFAULT_OPERATORS.copy()
DEFAULT_OPERATORS.pop(ast.Pow)
DEFAULT_FUNCTIONS = simpleeval.DEFAULT_FUNCTIONS.copy()
DEFAULT_FUNCTIONS.update({'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min,
                          'range': safe_range, 'sqrt': sqrt,
                          'roll': simple_roll, 'vroll': verbose_roll, 'load_json': load_json, 'dump_json': dump_json})
