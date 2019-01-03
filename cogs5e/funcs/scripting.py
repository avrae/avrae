import ast
import json
import re
import shlex
import time
from math import floor, ceil, sqrt

import simpleeval
from simpleeval import EvalWithCompoundTypes, IterableTooLong, SimpleEval

import utils.argparser
from cogs5e.funcs.dice import roll
from cogs5e.funcs.sheetFuncs import sheet_damage
from cogs5e.models.errors import CombatNotFound, InvalidSaveType, AvraeException
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup, Effect

SCRIPTING_RE = re.compile(r'(?<!\\)(?:(?:{{(.+?)}})|(?:<([^\s]+)>)|(?:(?<!{){(.+?)}))')
MAX_ITER_LENGTH = 10000


async def get_uvars(ctx):
    uvars = {}
    async for uvar in ctx.bot.mdb.uvars.find({"owner": ctx.message.author.id}):
        uvars[uvar['name']] = uvar['value']
    return uvars


async def set_uvar(ctx, name, value):
    await ctx.bot.mdb.uvars.update_one(
        {"owner": ctx.message.author.id, "name": name},
        {"$set": {"value": value}},
        True)


async def get_gvar_values(ctx):
    gvars = {}
    async for gvar in ctx.bot.mdb.gvars.find():
        gvars[gvar['key']] = gvar['value']
    return gvars


async def get_aliases(ctx):
    aliases = {}
    async for alias in ctx.bot.mdb.aliases.find({"owner": ctx.message.author.id}):
        aliases[alias['name']] = alias['commands']
    return aliases


async def get_servaliases(ctx):
    servaliases = {}
    async for servalias in ctx.bot.mdb.servaliases.find({"server": ctx.message.server.id}):
        servaliases[servalias['name']] = servalias['commands']
    return servaliases


async def get_snippets(ctx):
    snippets = {}
    async for snippet in ctx.bot.mdb.snippets.find({"owner": ctx.message.author.id}):
        snippets[snippet['name']] = snippet['snippet']
    return snippets


async def get_servsnippets(ctx):
    servsnippets = {}
    if ctx.message.server:
        async for servsnippet in ctx.bot.mdb.servsnippets.find({"server": ctx.message.server.id}):
            servsnippets[servsnippet['name']] = servsnippet['snippet']
    return servsnippets


async def parse_snippets(args: str, ctx) -> str:
    """
    Parses user and server snippets.
    :param args: The string to parse. Will be split automatically
    :param ctx: The Context.
    :return: The string, with snippets replaced.
    """
    tempargs = shlex.split(args)
    snippets = await get_servsnippets(ctx)
    snippets.update(await get_snippets(ctx))
    for index, arg in enumerate(tempargs):  # parse snippets
        snippet_value = snippets.get(arg)
        if snippet_value:
            tempargs[index] = snippet_value
        elif ' ' in arg:
            tempargs[index] = shlex.quote(arg)
    return " ".join(tempargs)


class MathEvaluator(SimpleEval):
    """Evaluator with basic math functions exposed."""
    MATH_FUNCTIONS = {'ceil': ceil, 'floor': floor, 'max': max, 'min': min, 'round': round}

    def __init__(self, operators=None, functions=None, names=None):
        if not functions:
            functions = self.MATH_FUNCTIONS
        super(MathEvaluator, self).__init__(operators, functions, names)

    @classmethod
    def with_character(cls, character):
        names = {}
        names.update(character.get_cvars())
        names.update(character.get_stat_vars())
        names['spell'] = character.get_spell_ab() - character.get_prof_bonus()
        return cls(names=names)

    def parse(self, string):
        """Parses a dicecloud-formatted string (evaluating text in {})."""
        return re.sub(r'(?<!\\){(.+?)}', lambda m: str(self.eval(m.group(1))), string)


class ScriptingEvaluator(EvalWithCompoundTypes):
    """Evaluator with compound types, comprehensions, and assignments exposed."""

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

        self.assign_nodes = {
            ast.Name: self._assign_name,
            ast.Tuple: self._assign_tuple,
            ast.Subscript: self._assign_subscript
        }

        self._loops = 0

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
        try:
            handler = self.assign_nodes[type(names)]
        except KeyError:
            raise TypeError(f"Assignment to {type(names).__name__} is not allowed")
        return handler(names, values, eval_values)

    def _assign_name(self, name, value, eval_value=True):
        if not isinstance(self.names, dict):
            raise TypeError("cannot set name: incorrect name type")
        else:
            if eval_value:
                value = self._eval(value)
            self.names[name.id] = value

    def _assign_tuple(self, names, values, eval_values=True):
        if not all(isinstance(n, ast.Name) for n in names.elts):
            raise TypeError("Assigning to multiple non-names via unpack is not allowed")
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

    def _assign_subscript(self, name, value, eval_value=True):
        if eval_value:
            value = self._eval(value)

        container = self._eval(name.value)
        key = self._eval(name.slice)
        container[key] = value
        self._assign(name.value, container, eval_values=False)

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
        if len(iterable) + self._loops > MAX_ITER_LENGTH:
            raise IterableTooLong("Execution limit exceeded: too many loops.")
        self._loops += len(iterable)
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


def verbose_roll(rollStr, multiply=1, add=0):
    if multiply != 1 or add != 0:
        def subDice(matchobj):
            return str((int(matchobj.group(1)) * multiply) + add) + 'd' + matchobj.group(2)

        rollStr = re.sub(r'(\d+)d(\d+)', subDice, rollStr)
    rolled = roll(rollStr, inline=True)
    try:
        return SimpleRollResult(rolled.rolled, rolled.total, rolled.skeleton,
                                [part.to_dict() for part in rolled.raw_dice.parts])
    except AttributeError:
        return None


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
        self.me = SimpleCombatant(me, False)
        self.round_num = self._combat.round_num
        self.turn_num = self._combat.turn_num
        current = self._combat.current_combatant
        if current:
            if isinstance(current, CombatantGroup):
                self.current = SimpleGroup(current)
            else:
                self.current = SimpleCombatant(current)
        else:
            self.current = None

    @classmethod
    async def from_character(cls, character, ctx):
        try:
            combat = await Combat.from_ctx(ctx)
        except CombatNotFound:
            return None
        me = next((c for c in combat.get_combatants() if getattr(c, 'character_id', None) == character.id), None)
        if not me:
            return None
        me._character = character  # set combatant character instance
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
    async def func_commit(self):
        await self._combat.commit()

    def __str__(self):
        return str(self._combat)


class SimpleCombatant:
    def __init__(self, combatant: Combatant, hidestats=True):
        self._combatant = combatant
        self._hidden = hidestats and self._combatant.isPrivate
        self.type = "combatant"

        if not self._hidden:
            self.ac = self._combatant.ac
            if self._combatant.hp is not None:
                self.hp = self._combatant.hp - (self._combatant.temphp or 0)
            else:
                self.hp = None
            self.maxhp = self._combatant.hpMax
            self.initmod = self._combatant.initMod
            self.temphp = self._combatant.temphp
            self.resists = self._combatant.resists
        else:
            self.ac = None
            self.hp = None
            self.maxhp = None
            self.initmod = None
            self.temphp = None
            self.resists = None
        self.init = self._combatant.init
        self.name = self._combatant.name
        self.note = self._combatant.notes
        self.effects = [SimpleEffect(e) for e in self._combatant.get_effects()]
        if self._combatant.hp is not None and self._combatant.hpMax:
            self.ratio = (self._combatant.hp - (self._combatant.temphp or 0)) / self._combatant.hpMax
        else:
            self.ratio = 0

    def set_hp(self, newhp: int):
        self._combatant.set_hp(int(newhp))

    def mod_hp(self, mod: int, overheal: bool = False):
        self._combatant.mod_hp(mod, overheal)

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

    def damage(self, dice_str: str, crit=False, d=None, c=None, critdice=0, overheal=False):
        args = utils.argparser.ParsedArguments(None, {
            'critdice': [critdice],
            'resist': self._combatant.resists['resist'],
            'immune': self._combatant.resists['immune'],
            'vuln': self._combatant.resists['vuln']
        })
        if d:
            args['d'] = d
        if c:
            args['c'] = c
        result = sheet_damage(dice_str, args, 1 if crit else 0)
        result['damage'] = result['damage'].strip()
        self.mod_hp(-result['total'], overheal=overheal)
        return result

    def set_ac(self, ac: int):
        if not isinstance(ac, int) and ac is not None:
            raise ValueError("AC must be an integer or None.")
        self._combatant.ac = ac

    def set_maxhp(self, maxhp: int):
        if not isinstance(maxhp, int) and maxhp is not None:
            raise ValueError("Max HP must be an integer or None.")
        self._combatant.hpMax = maxhp

    def set_thp(self, thp: int):
        if not isinstance(thp, int):
            raise ValueError("Temp HP must be an integer.")
        self._combatant.temphp = thp

    def set_init(self, init: int):
        if not isinstance(init, int):
            raise ValueError("Initiative must be an integer.")
        self._combatant.init = init

    def set_name(self, name: str):
        if not name:
            raise ValueError("Combatants must have a name.")
        self._combatant.name = str(name)

    def set_note(self, note: str):
        if note is not None:
            note = str(note)
        self._combatant.notes = note

    def get_effect(self, name: str):
        effect = self._combatant.get_effect(name)
        if effect:
            return SimpleEffect(effect)
        return None

    def add_effect(self, name: str, args: str, duration: int = -1, concentration: bool = False, parent=None):
        existing = self._combatant.get_effect(name, True)
        if existing:
            existing.remove()
        effectObj = Effect.new(self._combatant.combat, self._combatant, duration=duration, name=name, effect_args=args,
                               concentration=concentration)
        if parent:
            effectObj.set_parent(parent._effect)
        self._combatant.add_effect(effectObj)

    def remove_effect(self, name: str):
        effect = self._combatant.get_effect(name)
        if effect:
            effect.remove()

    def __str__(self):
        return str(self._combatant)


class SimpleGroup:
    def __init__(self, group: CombatantGroup):
        self._group = group
        self.type = "group"

    def get_combatant(self, name):
        combatant = next((c for c in self._group.get_combatants() if name.lower() in c.name.lower()), None)
        if combatant:
            return SimpleCombatant(combatant)
        return None

    def __str__(self):
        return str(self._group)


class SimpleEffect:
    def __init__(self, effect: Effect):
        self._effect = effect

        self.name = self._effect.name
        self.duration = self._effect.duration
        self.remaining = self._effect.remaining
        self.effect = self._effect.effect
        self.conc = self._effect.concentration

    def __str__(self):
        return str(self._effect)

    def set_parent(self, parent):
        self._effect.set_parent(parent._effect)


class AliasException(AvraeException):
    pass


def raise_alias_exception(reason):
    raise AliasException(reason)


DEFAULT_OPERATORS = simpleeval.DEFAULT_OPERATORS.copy()
DEFAULT_OPERATORS.pop(ast.Pow)

DEFAULT_FUNCTIONS = simpleeval.DEFAULT_FUNCTIONS.copy()
DEFAULT_FUNCTIONS.update({'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min,
                          'range': safe_range, 'sqrt': sqrt, 'sum': sum, 'any': any, 'all': all,
                          'roll': simple_roll, 'vroll': verbose_roll, 'load_json': load_json, 'dump_json': dump_json,
                          'time': time.time, 'err': raise_alias_exception})

if __name__ == '__main__':
    evaluator = ScriptingEvaluator()
    while True:
        try:
            evaluator.eval(input("Evaluate: ").strip())
        except Exception as e:
            print(e)
            continue
        print(evaluator.names)
