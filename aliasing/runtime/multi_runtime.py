import json
import re
import textwrap

import d20
import draconic
import json.scanner
from pymongo import MongoClient

from aliasing.constants import DEFAULT_BUILTINS, SCRIPTING_RE, UVAR_SIZE_LIMIT
from aliasing.errors import EvaluationError
from aliasing.functions import _roll, _vroll
from utils import config
from utils.argparser import argparse
from utils.dice import PersistentRollContext
from .context import AliasContext


class ScriptingEvaluator(draconic.DraconicInterpreter):
    """Evaluator with compound types, comprehensions, and assignments exposed."""

    def __init__(self, mdb: MongoClient, ctx: AliasContext, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.builtins.update(
            # fixme character-only functions, all deprecated now
            get_cc=self.old_get_cc, set_cc=self.old_set_cc, get_cc_max=self.old_get_cc_max,
            get_cc_min=self.old_get_cc_min, mod_cc=self.old_mod_cc,
            cc_exists=self.old_cc_exists, create_cc_nx=self.old_create_cc_nx, create_cc=self.old_create_cc,
            get_slots=self.old_get_slots, get_slots_max=self.old_get_slots_max, set_slots=self.old_set_slots,
            use_slot=self.old_use_slot,
            get_hp=self.old_get_hp, set_hp=self.old_set_hp, mod_hp=self.old_mod_hp, hp_str=self.old_hp_str,
            get_temphp=self.old_get_temphp, set_temphp=self.old_set_temphp,
            set_cvar=self.old_set_cvar, delete_cvar=self.old_delete_cvar, set_cvar_nx=self.old_set_cvar_nx,
            get_raw=self.old_get_raw,

            # char-agnostic builtins
            set=self.set, exists=self.exists, get=self.get,
            combat=self.combat, character=self.character,
            get_gvar=self.get_gvar,
            get_svar=self.get_svar,
            set_uvar=self.set_uvar, delete_uvar=self.delete_uvar, set_uvar_nx=self.set_uvar_nx,
            uvar_exists=self.uvar_exists,
            chanid=self.chanid, servid=self.servid,  # fixme deprecated - use ctx instead
            load_json=self.load_json, dump_json=self.dump_json,
            argparse=argparse, ctx=ctx
        )

        # roll limiting
        self._roller = d20.Roller(context=PersistentRollContext(max_rolls=1_000, max_total_rolls=10_000))
        self.builtins.update(
            vroll=self._limited_vroll,
            roll=self._limited_roll
        )

        # db
        self.ctx = ctx
        self.mdb = mdb

        self.character_changed = False
        self.combat_changed = False

    @classmethod
    def new(cls, initial_names, ctx_dict):
        mdb = MongoClient(config.MONGO_URL)[config.MONGODB_DB_NAME]
        ctx = AliasContext.from_dict(ctx_dict)
        return cls(mdb, ctx=ctx, builtins=DEFAULT_BUILTINS, initial_names=initial_names)

    def with_character(self, character):

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

        return self

    # helpers
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
        if 'combat' not in self._cache:  # todo
            self._cache['combat'] = combat_api.SimpleCombat.from_ctx(self.ctx)
        self.combat_changed = True
        return self._cache['combat']

    def character(self):
        """
        Returns the active character if one is. Otherwise, raises a :exc:`FunctionRequiresCharacter` error.

        :rtype: :class:`~aliasing.api.character.AliasCharacter`
        """
        if 'character' not in self._cache:  # todo
            raise ValueError('This function requires an active character.')
        self.character_changed = True
        return self._cache['character']

    def uvar_exists(self, name):
        """
        Returns whether a uvar exists.

        :rtype: bool
        """
        return self.exists(name) and name in self._cache['uvars']  # todo

    def get_gvar(self, address):
        """
        Retrieves and returns the value of a gvar (global variable).

        :param str address: The gvar address.
        :return: The value of the gvar.
        :rtype: str
        """
        result = self.mdb.gvars.find_one({"key": address})
        if result is None:
            return None
        return result['value']  # todo cache

    def get_svar(self, name, default=None):
        """
        Retrieves and returns the value of a svar (server variable).

        :param str name: The name of the svar.
        :param default: What to return if the name is not set.
        :return: The value of the svar, or the default value if it does not exist.
        :rtype: str or None
        """
        if self.ctx.guild is None:
            return default
        svar = self.mdb.svars.find_one({"owner": self.ctx.guild.id, "name": name})
        if svar is None:
            return None
        return svar['value']  # todo cache

    def set_uvar(self, name: str, value: str):
        """
        Sets a user variable.

        :param str name: The name of the variable to set.
        :param str value: The value to set it to.
        """
        if not name.isidentifier():
            raise ValueError("Cvar contains invalid character.")
        elif len(value) > UVAR_SIZE_LIMIT:
            raise ValueError(f"Uvars must be shorter than {UVAR_SIZE_LIMIT} characters.")
        self.mdb.uvars.update_one(
            {"owner": str(self.ctx.author.id), "name": name},
            {"$set": {"value": value}},
            upsert=True
        )

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
        self.mdb.uvars.delete_one({"owner": str(self.ctx.author.id), "name": name})

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

        Retrieves names in the order of local > cvar > uvar. Does not interact with svars.

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


def run(string, ctx_dict, bind_locals):
    """Main multiprocessing entrypoint to running an interpolation."""
    ops = r"([-+*/().<>=])"
    evaluator = ScriptingEvaluator.new(ctx_dict, bind_locals)

    def evalrepl(match):
        if match.group('lookup'):  # <>
            if re.match(r'<a?([@#]|:.+:)[&!]{0,2}\d+>', match.group(0)):  # ignore mentions
                return match.group(0)
            out = match.group('lookup')
            evalresult = str(evaluator.names.get(out, out))
        elif match.group('roll'):  # {}
            varstr = match.group('roll')
            curlyout = ""
            for substr in re.split(ops, varstr):
                temp = substr.strip()
                curlyout += str(evaluator.names.get(temp, temp)) + " "
            try:
                evalresult = str(evaluator._limited_roll(curlyout))
            except:
                evalresult = '0'
        elif match.group('drac1'):  # {{}}
            expr = match.group('drac1').strip()
            try:
                evalresult = evaluator.eval(expr)
            except Exception as ex:
                raise EvaluationError(ex, expr)
        elif match.group('drac2'):  # <drac2>...</drac2>
            expr = textwrap.dedent(match.group('drac2')).strip()
            try:
                evalresult = evaluator.execute(expr)
            except Exception as ex:
                raise EvaluationError(ex, expr)
        else:
            evalresult = None

        return str(evalresult) if evalresult is not None else ''

    output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

    return output
