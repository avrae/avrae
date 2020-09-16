import json
import re
import textwrap
import time
from math import ceil, floor, sqrt

import d20
import draconic
import json.scanner

import aliasing.api.character as character_api
import aliasing.api.combat as combat_api
import cogs5e.models.sheet.player as player_api
from aliasing import helpers
from aliasing.api.context import AliasContext
from aliasing.api.functions import _roll, _vroll, err, rand, randint, roll, safe_range, typeof, vroll
from aliasing.api.legacy import LegacyRawCharacter
from aliasing.errors import EvaluationError, FunctionRequiresCharacter
from cogs5e.models.errors import ConsumableException, InvalidArgument
from utils.argparser import argparse
from utils.dice import PersistentRollContext

DEFAULT_BUILTINS = {
    # builtins
    'floor': floor, 'ceil': ceil, 'round': round, 'len': len, 'max': max, 'min': min,
    'range': safe_range, 'sqrt': sqrt, 'sum': sum, 'any': any, 'all': all, 'time': time.time,
    # ours
    'roll': roll, 'vroll': vroll, 'err': err, 'typeof': typeof,
    # legacy from simpleeval
    'rand': rand, 'randint': randint
}
SCRIPTING_RE = re.compile(
    r'(?<!\\)(?:'  # backslash-escape
    r'{{(?P<drac1>.+?)}}'  # {{drac1}}
    r'|(?<!{){(?P<roll>.+?)}'  # {roll}
    r'|<drac2>(?P<drac2>(?:.|\n)+?)</drac2>'  # <drac2>drac2</drac2>
    r'|<(?P<lookup>[^\s]+?)>'  # <lookup>
    r')'
)


class MathEvaluator(draconic.SimpleInterpreter):
    """Evaluator with basic math functions exposed."""

    @classmethod
    def with_character(cls, character, spell_override=None):
        names = character.get_scope_locals()
        if spell_override is not None:
            names['spell'] = spell_override

        builtins = {**names, **DEFAULT_BUILTINS}
        return cls(builtins=builtins)

    # also disable per-eval limits, limit should be global
    def _preflight(self):
        pass

    def transformed_str(self, string):
        """Transforms a dicecloud-formatted string (evaluating text in {})."""
        try:
            return re.sub(r'(?<!\\){(.+?)}', lambda m: str(self.eval(m.group(1).strip())), string)
        except Exception as ex:
            raise EvaluationError(ex, string)


class ScriptingEvaluator(draconic.DraconicInterpreter):
    """Evaluator with compound types, comprehensions, and assignments exposed."""

    def __init__(self, ctx, *args, **kwargs):
        super(ScriptingEvaluator, self).__init__(*args, **kwargs)

        self.builtins.update(  # fixme character-only functions, all deprecated now
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

        # char-agnostic globals
        self.builtins.update(
            set=self.set, exists=self.exists, get=self.get,
            combat=self.combat, character=self.character,
            get_gvar=self.get_gvar,
            set_uvar=self.set_uvar, delete_uvar=self.delete_uvar, set_uvar_nx=self.set_uvar_nx,
            uvar_exists=self.uvar_exists,
            chanid=self.chanid, servid=self.servid,  # fixme deprecated - use ctx instead
            load_json=self.load_json, dump_json=self.dump_json,
            argparse=argparse, ctx=AliasContext(ctx)
        )

        # roll limiting
        self._roller = d20.Roller(context=PersistentRollContext(max_rolls=1_000, max_total_rolls=10_000))
        self.builtins.update(
            vroll=self._limited_vroll,
            roll=self._limited_roll
        )

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
        uvars = await helpers.get_uvars(ctx)
        inst = cls(ctx, builtins=DEFAULT_BUILTINS, initial_names=uvars)
        inst._cache['uvars'].update(uvars)
        return inst

    def with_statblock(self, statblock):
        self._names.update(statblock.get_scope_locals())
        return self

    def with_character(self, character):
        self.with_statblock(character)

        self._cache['character'] = character_api.AliasCharacter(character, self)

        # define character-specific functions
        # fixme deprecated

        # helpers
        def _get_consumable(name):
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
                new_consumable = player_api.CustomCounter.new(character, name, minVal, maxVal, reset, dispType)
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
            return character.spellbook.slots_str(level)

        def set_slots(level: int, value: int):
            character.spellbook.set_slots(level, value)
            self.character_changed = True

        def use_slot(level: int):
            character.spellbook.use_slot(level)
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
            return character.hp_str()

        def get_temphp():
            return character.temp_hp

        def set_temphp(val: int):
            character.temp_hp = val
            self.character_changed = True

        def set_cvar(name, val: str):
            helpers.set_cvar(character, name, val)
            self._names[name] = str(val)
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

        self.builtins.update(
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
            await self._cache['character'].func_commit(self.ctx)
        if self.combat_changed and 'combat' in self._cache and self._cache['combat']:
            await self._cache['combat'].func_commit()
        if self.uvars_changed and 'uvars' in self._cache and self._cache['uvars']:
            await helpers.update_uvars(self.ctx, self._cache['uvars'], self.uvars_changed)

    # helpers
    def needs_char(self, *args, **kwargs):
        raise FunctionRequiresCharacter()  # no. bad.

    def set(self, name, value):  # todo
        """
        Sets the value of a name in the current scripting context.

        .. deprecated:: 0.1.0
            Use ``name = value`` instead.

        :param name: The name to set.
        :param value: The value to set it to.
        """
        if name in self.builtins:
            raise ValueError(f"{name} is already builtin (no shadow assignments).")
        self._names[name] = value

    def exists(self, name):
        """
        Returns whether or not a name is set in the current evaluation context.

        :rtype: bool
        """
        return name in self.names

    def combat(self):
        """
        Returns the combat active in the channel if one is. Otherwise, returns ``None``.

        :rtype: :class:`~aliasing.api.combat.SimpleCombat`
        """
        if 'combat' not in self._cache:
            self._cache['combat'] = combat_api.SimpleCombat.from_ctx(self.ctx)
        self.combat_changed = True
        return self._cache['combat']

    def character(self):
        """
        Returns the active character if one is. Otherwise, raises a :exc:`FunctionRequiresCharacter` error.

        :rtype: :class:`~aliasing.api.character.AliasCharacter`
        """
        if 'character' not in self._cache:
            raise FunctionRequiresCharacter()
        self.character_changed = True
        return self._cache['character']

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
        self._names[name] = str(value)
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

        .. deprecated:: 2.5.0
            Use ``ctx.channel.id`` instead.

        :rtype: str
        """
        return str(self.ctx.channel.id)

    def servid(self):
        """
        Returns the ID of the active Discord guild, or None if in DMs.

        .. deprecated:: 2.5.0
            Use ``ctx.guild.id`` instead.

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

    # ==== json ====
    def _json_decoder(self):
        class MyDecoder(json.JSONDecoder):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parse_array = self._parse_array
                self.object_hook = self._object_hook
                # use the python implementation rather than C, so this works
                self.scan_once = json.scanner.py_make_scanner(self)

            @staticmethod
            def _parse_array(*args, **kwargs):
                values, end = json.decoder.JSONArray(*args, **kwargs)
                values = self._list(values)
                return values, end

            @staticmethod
            def _object_hook(obj):
                return self._dict(obj)

        return MyDecoder

    def _dump_json_default(self, obj):
        if isinstance(obj, self._list):
            return obj.data

    def load_json(self, jsonstr):
        """
        Loads an object from a JSON string. See :func:`json.loads`.
        """
        return json.loads(jsonstr, cls=self._json_decoder())

    def dump_json(self, obj):
        """
        Serializes an object to a JSON string. See :func:`json.dumps`.
        """
        return json.dumps(obj, default=self._dump_json_default)

    # ==== roll limiters ====
    def _limited_vroll(self, dice, multiply=1, add=0):
        return _vroll(dice, multiply, add, roller=self._roller)

    def _limited_roll(self, dice):
        return _roll(dice, roller=self._roller)

    # evaluation
    def _preflight(self):
        """We don't want limits to reset."""
        pass

    def transformed_str(self, string):
        """Parses a scripting string (evaluating text in {{}})."""
        ops = r"([-+*/().<>=])"

        def evalrepl(match):
            if match.group('lookup'):  # <>
                if re.match(r'<a?([@#]|:.+:)[&!]{0,2}\d+>', match.group(0)):  # ignore mentions
                    return match.group(0)
                out = match.group('lookup')
                evalresult = str(self.names.get(out, out))
            elif match.group('roll'):  # {}
                varstr = match.group('roll')
                curlyout = ""
                for substr in re.split(ops, varstr):
                    temp = substr.strip()
                    curlyout += str(self.names.get(temp, temp)) + " "
                try:
                    evalresult = str(self._limited_roll(curlyout))
                except:
                    evalresult = '0'
            elif match.group('drac1'):  # {{}}
                expr = match.group('drac1').strip()
                try:
                    evalresult = self.eval(expr)
                except Exception as ex:
                    raise EvaluationError(ex, expr)
            elif match.group('drac2'):  # <drac2>...</drac2>
                expr = textwrap.dedent(match.group('drac2')).strip()
                try:
                    evalresult = self.execute(expr)
                except Exception as ex:
                    raise EvaluationError(ex, expr)
            else:
                evalresult = None

            return str(evalresult) if evalresult is not None else ''

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        return output


class SpellEvaluator(MathEvaluator):
    @classmethod
    def with_caster(cls, caster, spell_override=None):
        names = caster.get_scope_locals()
        if spell_override is not None:
            names['spell'] = spell_override

        builtins = {**names, **DEFAULT_BUILTINS}
        return cls(builtins=builtins)

    def transformed_str(self, string, extra_names=None):
        """Parses a spell-formatted string (evaluating {{}} and replacing {} with rollstrings)."""
        original_names = None
        if extra_names:
            original_names = self.builtins.copy()
            self.builtins.update(extra_names)

        def evalrepl(match):
            try:
                if match.group('drac1'):  # {{}}
                    evalresult = self.eval(match.group('drac1').strip())
                elif match.group('roll'):  # {}
                    try:
                        evalresult = self.eval(match.group('roll').strip())
                    except:
                        evalresult = match.group(0)
                else:
                    evalresult = None
            except Exception as ex:
                raise EvaluationError(ex, match.group(0))

            return str(evalresult) if evalresult is not None else ''

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        if original_names:
            self.builtins = original_names

        return output


if __name__ == '__main__':
    e = ScriptingEvaluator(None)
    while True:
        print(e.eval(input()))
