import ast
import re
from math import ceil, floor

import simpleeval
from simpleeval import DEFAULT_NAMES, EvalWithCompoundTypes, IterableTooLong, SimpleEval

from cogs5e.funcs.dice import roll
from cogs5e.models.errors import ConsumableException, EvaluationError, FunctionRequiresCharacter, InvalidArgument
from cogs5e.models.sheet import CustomCounter
from . import MAX_ITER_LENGTH, SCRIPTING_RE
from .combat import SimpleCombat
from .functions import DEFAULT_FUNCTIONS, DEFAULT_OPERATORS
from .helpers import get_uvars, update_uvars
from .legacy import LegacyRawCharacter

if 'format_map' not in simpleeval.DISALLOW_METHODS:
    simpleeval.DISALLOW_METHODS.append('format_map')


class MathEvaluator(SimpleEval):
    """Evaluator with basic math functions exposed."""
    MATH_FUNCTIONS = {'ceil': ceil, 'floor': floor, 'max': max, 'min': min, 'round': round}

    def __init__(self, operators=None, functions=None, names=None):
        if operators is None:
            operators = DEFAULT_OPERATORS.copy()
        if functions is None:
            functions = DEFAULT_FUNCTIONS.copy()
        if names is None:
            names = DEFAULT_NAMES.copy()
        super(MathEvaluator, self).__init__(operators, functions, names)

    @classmethod
    def with_character(cls, character, spell_override=None):
        names = character.get_scope_locals()
        if spell_override is not None:
            names['spell'] = spell_override
        return cls(names=names)

    def parse(self, string):
        """Parses a dicecloud-formatted string (evaluating text in {})."""
        try:
            return re.sub(r'(?<!\\){(.+?)}', lambda m: str(self.eval(m.group(1))), string)
        except Exception as ex:
            raise EvaluationError(ex, string)


class ScriptingEvaluator(EvalWithCompoundTypes):
    """Evaluator with compound types, comprehensions, and assignments exposed."""

    def __init__(self, ctx, operators=None, functions=None, names=None):
        if operators is None:
            operators = DEFAULT_OPERATORS.copy()
        if functions is None:
            functions = DEFAULT_FUNCTIONS.copy()
        if names is None:
            names = DEFAULT_NAMES.copy()
        super(ScriptingEvaluator, self).__init__(operators, functions, names)

        self.nodes.update({
            ast.JoinedStr: self._eval_joinedstr,  # f-string
            ast.FormattedValue: self._eval_formattedvalue,  # things in f-strings
            ast.ListComp: self._eval_listcomp,
            ast.SetComp: self._eval_setcomp,
            ast.DictComp: self._eval_dictcomp,
            ast.comprehension: self._eval_comprehension
        })

        self.functions.update(  # character-only functions
            get_cc=self.needs_char, set_cc=self.needs_char, get_cc_max=self.needs_char,
            get_cc_min=self.needs_char, mod_cc=self.needs_char,
            cc_exists=self.needs_char, create_cc_nx=self.needs_char, create_cc=self.needs_char,
            get_slots=self.needs_char, get_slots_max=self.needs_char, set_slots=self.needs_char,
            use_slot=self.needs_char,
            get_hp=self.needs_char, set_hp=self.needs_char, mod_hp=self.needs_char, hp_str=self.needs_char,
            get_temphp=self.needs_char, set_temphp=self.needs_char,
            set_cvar=self.needs_char, delete_cvar=self.needs_char, set_cvar_nx=self.needs_char,
            get_raw=self.needs_char
        )

        self.functions.update(
            set=self.set, exists=self.exists, combat=self.combat,
            get_gvar=self.get_gvar,
            set_uvar=self.set_uvar, delete_uvar=self.delete_uvar, set_uvar_nx=self.set_uvar_nx,
            uvar_exists=self.uvar_exists,
            chanid=self.chanid, servid=self.servid,
            get=self.get
        )

        self.assign_nodes = {
            ast.Name: self._assign_name,
            ast.Tuple: self._assign_tuple,
            ast.Subscript: self._assign_subscript
        }

        self._loops = 0
        self._cache = {
            "gvars": {},
            "uvars": {}
        }

        self.ctx = ctx
        self.character_changed = False
        self.combat_changed = False
        self.uvars_changed = set()

    @classmethod
    async def new(cls, ctx):
        inst = cls(ctx)
        uvars = await get_uvars(ctx)
        inst.names.update(uvars)
        inst._cache['uvars'].update(uvars)
        return inst

    async def with_character(self, character):
        self.names.update(character.get_scope_locals())

        self._cache['character'] = character

        # define character-specific functions

        # helpers
        def _get_consumable(name) -> CustomCounter:
            consumable = next((con for con in character.consumables if con.name == name), None)
            if consumable is None:
                raise ConsumableException(f"There is no counter named {name}.")
            return consumable

        # funcs
        def combat():
            cmbt = self.combat()
            if cmbt and not cmbt.me:
                cmbt.func_set_character(character)
            return cmbt

        def get_cc(name):
            return _get_consumable(name).value

        def get_cc_max(name):
            return _get_consumable(name).get_max()

        def get_cc_min(name):
            return _get_consumable(name).get_min()

        def set_cc(name, value: int, strict=False):
            _get_consumable(name).set(value, strict)
            self.character_changed = True

        def mod_cc(name, val: int, strict=False):
            return set_cc(name, get_cc(name) + val, strict)

        def delete_cc(name):
            to_delete = _get_consumable(name)
            character.consumables.remove(to_delete)
            self.character_changed = True

        def create_cc_nx(name: str, minVal: str = None, maxVal: str = None, reset: str = None,
                         dispType: str = None):
            if not cc_exists(name):
                new_consumable = CustomCounter.new(character, name, minVal, maxVal, reset, dispType)
                character.consumables.append(new_consumable)
                self.character_changed = True

        def create_cc(name: str, *args, **kwargs):
            if cc_exists(name):
                delete_cc(name)
            create_cc_nx(name, *args, **kwargs)

        def cc_exists(name):
            return name in set(con.name for con in character.consumables)

        def cc_str(name):
            return str(_get_consumable(name))

        def get_slots(level: int):
            return character.spellbook.get_slots(level)

        def get_slots_max(level: int):
            return character.spellbook.get_max_slots(level)

        def slots_str(level: int):
            return character.get_remaining_slots_str(level)

        def set_slots(level: int, value: int):
            character.set_remaining_slots(level, value)
            self.character_changed = True

        def use_slot(level: int):
            character.use_slot(level)
            self.character_changed = True

        def get_hp():
            return character.hp

        def set_hp(val: int):
            character.hp = val
            self.character_changed = True

        def mod_hp(val: int, overflow: bool = True):
            character.modify_hp(val, overflow=overflow)
            self.character_changed = True

        def hp_str():
            return character.get_hp_str()

        def get_temphp():
            return character.temp_hp

        def set_temphp(val: int):
            character.temp_hp = val
            self.character_changed = True

        def set_cvar(name, val: str):
            character.set_cvar(name, val)
            self.names[name] = str(val)
            self.character_changed = True

        def set_cvar_nx(name, val: str):
            if name not in character.cvars:
                set_cvar(name, val)

        def delete_cvar(name):
            if name in character.cvars:
                del character.cvars[name]
                self.character_changed = True

        def get_raw():
            return LegacyRawCharacter(character).to_dict()

        self.functions.update(
            combat=combat,
            get_cc=get_cc, set_cc=set_cc, get_cc_max=get_cc_max, get_cc_min=get_cc_min, mod_cc=mod_cc,
            delete_cc=delete_cc, cc_exists=cc_exists, create_cc_nx=create_cc_nx, create_cc=create_cc, cc_str=cc_str,
            get_slots=get_slots, get_slots_max=get_slots_max, set_slots=set_slots, use_slot=use_slot,
            slots_str=slots_str,
            get_hp=get_hp, set_hp=set_hp, mod_hp=mod_hp, hp_str=hp_str,
            get_temphp=get_temphp, set_temphp=set_temphp,
            set_cvar=set_cvar, delete_cvar=delete_cvar, set_cvar_nx=set_cvar_nx,
            get_raw=get_raw
        )

        return self

    async def run_commits(self):
        if self.character_changed and 'character' in self._cache:
            await self._cache['character'].commit(self.ctx)
        if self.combat_changed and 'combat' in self._cache and self._cache['combat']:
            await self._cache['combat'].func_commit()
        if self.uvars_changed and 'uvars' in self._cache and self._cache['uvars']:
            await update_uvars(self.ctx, self._cache['uvars'], self.uvars_changed)

    # helpers
    def needs_char(self, *args, **kwargs):
        raise FunctionRequiresCharacter()  # no. bad.

    def set(self, name, value):
        """
        Sets the value of a name in the current scripting context.

        .. deprecated:: 0.1.0
            Use ``name = value`` instead.

        :param name: The name to set.
        :param value: The value to set it to.
        """
        self.names[name] = value

    def exists(self, name):
        """
        Returns whether or not a name is set in the current evaluation context.

        :rtype: bool
        """
        return name in self.names

    def combat(self):
        """
        Returns the combat active in the channel if one is. Otherwise, returns ``None``.

        :rtype: :class:`~cogs5e.funcs.scripting.combat.SimpleCombat`
        """
        if 'combat' not in self._cache:
            self._cache['combat'] = SimpleCombat.from_ctx(self.ctx)
        self.combat_changed = True
        return self._cache['combat']

    def uvar_exists(self, name):
        """
        Returns whether a uvar exists.

        :rtype: bool
        """
        return self.exists(name) and name in self._cache['uvars']

    def get_gvar(self, address):
        """
        Retrieves and returns the value of a gvar (global variable).

        :param str address: The gvar address.
        :return: The value of the gvar.
        :rtype: str
        """
        if address not in self._cache['gvars']:
            result = self.ctx.bot.mdb.gvars.delegate.find_one({"key": address})
            if result is None:
                return None
            self._cache['gvars'][address] = result['value']
        return self._cache['gvars'][address]

    def set_uvar(self, name: str, value: str):
        """
        Sets a user variable.

        :param str name: The name of the variable to set.
        :param str value: The value to set it to.
        """
        if not name.isidentifier():
            raise InvalidArgument("Cvar contains invalid character.")
        self._cache['uvars'][name] = str(value)
        self.names[name] = str(value)
        self.uvars_changed.add(name)

    def set_uvar_nx(self, name, value: str):
        """
        Sets a user variable if there is not already an existing name.

        :param str name: The name of the variable to set.
        :param str value: The value to set it to.
        """
        if not name in self.names:
            self.set_uvar(name, value)

    def delete_uvar(self, name):
        """
        Deletes a user variable. Does nothing if the variable does not exist.

        :param str name: The name of the variable to delete.
        """
        if name in self._cache['uvars']:
            del self._cache['uvars'][name]
            self.uvars_changed.add(name)

    def chanid(self):
        """
        Returns the ID of the active Discord channel.

        :rtype: str
        """
        return str(self.ctx.channel.id)

    def servid(self):
        """
        Returns the ID of the active Discord guild, or None if in DMs.

        :rtype: str
        """
        if self.ctx.guild:
            return str(self.ctx.guild.id)
        return None

    def get(self, name, default=None):
        """
        Gets the value of a name, or returns *default* if the name is not set.

        :param str name: The name to retrieve.
        :param default: What to return if the name is not set.
        """
        if name in self.names:
            return self.names[name]
        return default

    # evaluation
    def parse(self, string, double_curly=None, curly=None, ltgt=None):
        """Parses a scripting string (evaluating text in {{}})."""
        ops = r"([-+*/().<>=])"

        def evalrepl(match):
            try:
                if match.group(1):  # {{}}
                    double_func = double_curly or self.eval
                    evalresult = double_func(match.group(1))
                elif match.group(2):  # <>
                    if re.match(r'<a?([@#]|:.+:)[&!]{0,2}\d+>', match.group(0)):  # ignore mentions
                        return match.group(0)
                    out = match.group(2)
                    ltgt_func = ltgt or (lambda s: str(self.names.get(s, s)))
                    evalresult = ltgt_func(out)
                elif match.group(3):  # {}
                    varstr = match.group(3)

                    def default_curly_func(s):
                        curlyout = ""
                        for substr in re.split(ops, s):
                            temp = substr.strip()
                            curlyout += str(self.names.get(temp, temp)) + " "
                        return str(roll(curlyout).total)

                    curly_func = curly or default_curly_func
                    evalresult = curly_func(varstr)
                else:
                    evalresult = None
            except Exception as ex:
                raise EvaluationError(ex, match.group(0))

            return str(evalresult) if evalresult is not None else ''

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        return output

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

    # private magic
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


class SpellEvaluator(MathEvaluator):
    @classmethod
    def with_caster(cls, caster, spell_override=None):
        if spell_override is not None:
            spell = spell_override
        elif caster.spellbook.spell_mod is not None:
            spell = caster.spellbook.spell_mod
        else:
            try:
                spell = caster.spellbook.sab - caster.pb_from_level()
            except TypeError:
                spell = 0
        names = {'spell': spell, 'proficiencyBonus': caster.pb_from_level()}
        return cls(names=names)

    def parse(self, string, extra_names=None):
        """Parses a spell-formatted string (evaluating {{}} and replacing {} with rollstrings)."""
        original_names = None
        if extra_names:
            original_names = self.names.copy()
            self.names.update(extra_names)

        def evalrepl(match):
            try:
                if match.group(1):  # {{}}
                    evalresult = self.eval(match.group(1))
                elif match.group(3):  # {}
                    evalresult = self.names.get(match.group(3), match.group(0))
                else:
                    evalresult = None
            except Exception as ex:
                raise EvaluationError(ex, match.group(0))

            return str(evalresult) if evalresult is not None else ''

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        if original_names:
            self.names = original_names

        return output
