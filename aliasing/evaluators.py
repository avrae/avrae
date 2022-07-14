import asyncio
import functools
import json
import re
import textwrap
import time
from collections import namedtuple
from functools import cached_property
from math import ceil, floor, sqrt
from types import SimpleNamespace
from typing import Optional, Union

import d20
import draconic
import json.scanner
import yaml
from yaml import composer, parser, scanner

import aliasing.api.character as character_api
import aliasing.api.combat as combat_api
from aliasing import helpers
from aliasing.api.context import AliasContext
from aliasing.api.functions import (
    _roll,
    _vroll,
    create_signature,
    err,
    parse_coins,
    rand,
    randchoice,
    randchoices,
    randint,
    roll,
    safe_range,
    typeof,
    verify_signature,
    vroll,
)
from aliasing.errors import EvaluationError, FunctionRequiresCharacter
from aliasing.personal import _CustomizationBase
from aliasing.utils import ExecutionScope
from aliasing.workshop import WorkshopCollectableObject
from cogs5e.models.errors import InvalidArgument
from utils.argparser import argparse
from utils.dice import PersistentRollContext

DEFAULT_BUILTINS = {
    # builtins
    "floor": floor,
    "ceil": ceil,
    "round": round,
    "len": len,
    "max": max,
    "min": min,
    "enumerate": enumerate,
    "range": safe_range,
    "sqrt": sqrt,
    "sum": sum,
    "any": any,
    "all": all,
    "abs": abs,
    "time": time.time,
    # ours
    "roll": roll,
    "vroll": vroll,
    "err": err,
    "typeof": typeof,
    "parse_coins": parse_coins,
    "rand": rand,
    "randint": randint,
    "randchoice": randchoice,
    "randchoices": randchoices,
}
SCRIPTING_RE = re.compile(
    r"(?<!\\)(?:"  # backslash-escape
    r"{{(?P<drac1>.+?)}}"  # {{drac1}}
    r"|(?<!{){(?P<roll>.+?)}"  # {roll}
    r"|<drac2>(?P<drac2>(?:.|\n)+?)</drac2>"  # <drac2>drac2</drac2>
    r"|<(?P<lookup>[^\s]+?)>"  # <lookup>
    r")"
)
# an alias/snippet that can invoke draconic code
_CodeInvokerT = Optional[Union[_CustomizationBase, WorkshopCollectableObject]]
ScriptingWarning = namedtuple("ScriptingWarning", "msg node expr")


class MathEvaluator(draconic.SimpleInterpreter):
    """Evaluator with basic math functions exposed."""

    @classmethod
    def with_character(cls, character, spell_override=None):
        names = character.get_scope_locals()
        if spell_override is not None:
            names["spell"] = spell_override

        builtins = {**names, **DEFAULT_BUILTINS}
        return cls(builtins=builtins)

    # also disable per-eval limits, limit should be global
    def _preflight(self):
        pass

    def eval(self, expr):
        if expr is None:
            return None
        return super().eval(expr)

    def transformed_str(self, string):
        """Transforms a dicecloud-formatted string (evaluating text in {})."""
        try:
            return re.sub(r"(?<!\\){(.+?)}", lambda m: str(self.eval(m.group(1).strip())), string)
        except Exception as ex:
            raise EvaluationError(ex, string)


class ScriptingEvaluator(draconic.DraconicInterpreter):
    """Evaluator with compound types, comprehensions, and assignments exposed."""

    def __init__(self, ctx, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # char-agnostic globals
        self.builtins.update(
            exists=self.exists,
            get=self.get,
            combat=self.combat,
            character=self.character,
            get_gvar=self.get_gvar,
            get_svar=self.get_svar,
            set_uvar=self.set_uvar,
            get_uvars=self.get_uvars,
            delete_uvar=self.delete_uvar,
            set_uvar_nx=self.set_uvar_nx,
            uvar_exists=self.uvar_exists,
            load_json=self.load_json,
            dump_json=self.dump_json,
            load_yaml=self.load_yaml,
            dump_yaml=self.dump_yaml,
            argparse=argparse,
            ctx=AliasContext(ctx),
            signature=self.signature,
            verify_signature=self.verify_signature,
            using=self.using,
        )

        # roll limiting
        self._roller = d20.Roller(context=PersistentRollContext(max_rolls=1_000, max_total_rolls=10_000))
        self.builtins.update(vroll=self._limited_vroll, roll=self._limited_roll)

        self._cache = {"gvars": {}, "svars": {}, "uvars": {}, "imports": {}}

        self.ctx = ctx
        self.character_changed = False
        self.combat_changed = False
        self.uvars_changed = set()
        self.execution_scope: ExecutionScope = ExecutionScope.UNKNOWN
        self.invoking_object: _CodeInvokerT = None

        # warnings
        self._aliasing_current_node = None
        self._nodes_with_warnings = set()
        self.warnings: list[ScriptingWarning] = []

        # imports
        self._import_stack: list[str] = []

    @classmethod
    async def new(cls, ctx):
        uvars = await helpers.get_uvars(ctx)
        inst = cls(ctx, builtins=DEFAULT_BUILTINS, initial_names=uvars)
        inst._cache["uvars"].update(uvars)
        return inst

    def with_statblock(self, statblock):
        self._names.update(statblock.get_scope_locals())
        return self

    def with_character(self, character):
        self.with_statblock(character)
        self._cache["character"] = character_api.AliasCharacter(character, self)

        # funcs
        def combat():
            cmbt = self.combat()
            if cmbt and not cmbt.me:
                cmbt.func_set_character(character)
            return cmbt

        self.builtins.update(combat=combat)
        return self

    async def run_commits(self):
        if self.character_changed and "character" in self._cache:
            await self._cache["character"].func_commit(self.ctx)
        if self.combat_changed and "combat" in self._cache and self._cache["combat"]:
            await self._cache["combat"].func_commit()
        if self.uvars_changed and "uvars" in self._cache and self._cache["uvars"] is not None:
            await helpers.update_uvars(self.ctx, self._cache["uvars"], self.uvars_changed)

    # helpers
    def exists(self, name):
        """
        Returns whether or not a name is set in the current evaluation context.

        :rtype: bool
        """
        name = str(name)
        return name in self.names

    def combat(self):
        """
        Returns the combat active in the channel if one is. Otherwise, returns ``None``.

        :rtype: :class:`~aliasing.api.combat.SimpleCombat`
        """
        if "combat" not in self._cache:
            self._cache["combat"] = combat_api.SimpleCombat.from_ctx(self.ctx, interpreter=self)
        self.combat_changed = True
        return self._cache["combat"]

    def character(self):
        """
        Returns the active character if one is. Otherwise, raises a :exc:`FunctionRequiresCharacter` error.

        :rtype: :class:`~aliasing.api.character.AliasCharacter`
        """
        if "character" not in self._cache:
            raise FunctionRequiresCharacter()
        self.character_changed = True
        return self._cache["character"]

    def uvar_exists(self, name):
        """
        Returns whether a uvar exists.

        :rtype: bool
        """
        name = str(name)
        return self.exists(name) and name in self._cache["uvars"]

    def get_gvar(self, address):
        """
        Retrieves and returns the value of a gvar (global variable).

        :param str address: The gvar address.
        :return: The value of the gvar.
        :rtype: str
        """
        address = str(address)
        if address not in self._cache["gvars"]:
            result = self.ctx.bot.mdb.gvars.delegate.find_one({"key": address})
            if result is None:
                return None
            self._cache["gvars"][address] = result["value"]
        return self._cache["gvars"][address]

    def get_svar(self, name, default=None):
        """
        Retrieves and returns the value of a svar (server variable).

        :param str name: The name of the svar.
        :param default: What to return if the name is not set.
        :return: The value of the svar, or the default value if it does not exist.
        :rtype: str or None
        """
        name = str(name)
        if self.ctx.guild is None:
            return default
        if name not in self._cache["svars"]:
            result = self.ctx.bot.mdb.svars.delegate.find_one({"owner": self.ctx.guild.id, "name": name})
            if result is None:
                return default
            self._cache["svars"][name] = result["value"]
        return self._cache["svars"][name]
    
    def get_uvars(self):
        """
        Retrieves and returns the dict of uvars.

        :return: A dict of all uvars.
        :rtype: dict
        """
        return self._cache["uvars"]

    def set_uvar(self, name: str, value: str):
        """
        Sets a user variable.

        :param str name: The name of the variable to set.
        :param str value: The value to set it to.
        """
        name = str(name)
        value = str(value)
        if not name.isidentifier():
            raise InvalidArgument("Uvar contains invalid character.")
        self._cache["uvars"][name] = value
        self._names[name] = value
        self.uvars_changed.add(name)

    def set_uvar_nx(self, name, value: str):
        """
        Sets a user variable if there is not already an existing name.

        :param str name: The name of the variable to set.
        :param str value: The value to set it to.
        """
        name = str(name)
        if not name in self.names:
            self.set_uvar(name, value)

    def delete_uvar(self, name):
        """
        Deletes a user variable. Does nothing if the variable does not exist.

        :param str name: The name of the variable to delete.
        """
        name = str(name)
        if name in self._cache["uvars"]:
            del self._cache["uvars"][name]
            self.uvars_changed.add(name)

    def get(self, name, default=None):
        """
        Gets the value of a name, or returns *default* if the name is not set.

        Retrieves names in the order of local > cvar > uvar. Does not interact with svars.

        :param str name: The name to retrieve.
        :param default: What to return if the name is not set.
        """
        name = str(name)
        if name in self.names:
            return self.names[name]
        return default

    # ==== YAML ====
    @cached_property
    def _yaml_dumper(self):
        class DraconicDumper(yaml.SafeDumper):
            def safe_dict_representer(self, data):
                return self.represent_dict(data)

            def safe_list_representer(self, data):
                return self.represent_sequence(self.DEFAULT_SEQUENCE_TAG, data)

            def safe_str_representer(self, data):
                return self.represent_str(data)

            def safe_set_representer(self, data):
                return self.represent_sequence(self.DEFAULT_SEQUENCE_TAG, data)

        DraconicDumper.add_representer(self._dict, DraconicDumper.safe_dict_representer)
        DraconicDumper.add_representer(self._list, DraconicDumper.safe_list_representer)
        DraconicDumper.add_representer(self._str, DraconicDumper.safe_str_representer)
        DraconicDumper.add_representer(self._set, DraconicDumper.safe_set_representer)

        return DraconicDumper

    @cached_property
    def _yaml_loader(self):
        # make a subclass of the baseloader and register all the constructors for valid types as SafeConstructor
        # defines it
        interpreter = self

        class DraconicConstructor(yaml.constructor.BaseConstructor):
            bool_values = yaml.constructor.SafeConstructor.bool_values

            def construct_yaml_set(self, node):
                data = interpreter._set()
                yield data
                value = self.construct_mapping(node)
                data.update(value)

            def construct_yaml_str(self, node):
                # noinspection PyArgumentList
                return interpreter._str(self.construct_scalar(node))

            def construct_yaml_seq(self, node):
                data = interpreter._list()
                yield data
                data.extend(self.construct_sequence(node))

            def construct_yaml_map(self, node):
                data = interpreter._dict()
                yield data
                value = self.construct_mapping(node)
                data.update(value)

        DraconicConstructor.add_constructor(
            "tag:yaml.org,2002:null", yaml.constructor.SafeConstructor.construct_yaml_null
        )
        DraconicConstructor.add_constructor(
            "tag:yaml.org,2002:bool", yaml.constructor.SafeConstructor.construct_yaml_bool
        )
        DraconicConstructor.add_constructor(
            "tag:yaml.org,2002:int", yaml.constructor.SafeConstructor.construct_yaml_int
        )
        DraconicConstructor.add_constructor(
            "tag:yaml.org,2002:float", yaml.constructor.SafeConstructor.construct_yaml_float
        )
        DraconicConstructor.add_constructor(
            "tag:yaml.org,2002:omap", yaml.constructor.SafeConstructor.construct_yaml_omap
        )
        DraconicConstructor.add_constructor(
            "tag:yaml.org,2002:pairs", yaml.constructor.SafeConstructor.construct_yaml_pairs
        )
        DraconicConstructor.add_constructor("tag:yaml.org,2002:set", DraconicConstructor.construct_yaml_set)
        DraconicConstructor.add_constructor("tag:yaml.org,2002:str", DraconicConstructor.construct_yaml_str)
        DraconicConstructor.add_constructor("tag:yaml.org,2002:seq", DraconicConstructor.construct_yaml_seq)
        DraconicConstructor.add_constructor("tag:yaml.org,2002:map", DraconicConstructor.construct_yaml_map)
        DraconicConstructor.add_constructor(None, DraconicConstructor.construct_yaml_str)

        class DraconicLoader(
            yaml.reader.Reader,
            yaml.scanner.Scanner,
            yaml.parser.Parser,
            yaml.composer.Composer,
            DraconicConstructor,
            yaml.resolver.Resolver,
        ):
            def __init__(self, stream):
                yaml.reader.Reader.__init__(self, stream)
                yaml.scanner.Scanner.__init__(self)
                yaml.parser.Parser.__init__(self)
                yaml.composer.Composer.__init__(self)
                DraconicConstructor.__init__(self)
                yaml.resolver.Resolver.__init__(self)

        return DraconicLoader

    def load_yaml(self, yamlstr):
        """
        Loads an object from a YAML string. See `yaml.safe_load <https://pyyaml.org/wiki/PyYAMLDocumentation>`_.
        """
        return yaml.load(str(yamlstr), self._yaml_loader)

    def dump_yaml(self, obj, indent=2):
        """
        Serializes an object to a YAML string. See `yaml.safe_dump <https://pyyaml.org/wiki/PyYAMLDocumentation>`_.
        """
        return yaml.dump(
            obj, Dumper=self._yaml_dumper, default_flow_style=False, line_break=True, indent=indent, sort_keys=False
        )

    # ==== json ====
    def _json_decoder(self):
        # noinspection PyUnresolvedReferences,PyArgumentList
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

    # noinspection PyTypeChecker,PyUnresolvedReferences
    def _dump_json_default(self, obj):
        if isinstance(obj, self._list):
            return obj.data

    def load_json(self, jsonstr):
        """
        Loads an object from a JSON string. See :func:`json.loads`.
        """
        return json.loads(str(jsonstr), cls=self._json_decoder())

    def dump_json(self, obj):
        """
        Serializes an object to a JSON string. See :func:`json.dumps`.
        """
        return json.dumps(obj, default=self._dump_json_default)

    # ==== roll limiters ====
    def _limited_vroll(self, dice, multiply=1, add=0):
        dice = str(dice)
        return _vroll(dice, multiply, add, roller=self._roller)

    def _limited_roll(self, dice):
        dice = str(dice)
        return _roll(dice, roller=self._roller)

    # ==== audit functions ====
    def signature(self, data=0):
        """
        Returns a unique signature encoding the time the alias was invoked, the channel it was invoked in, the invoker,
        the id of the workshop collection the alias originates from (if applicable), and whether the caller was a
        personal/server alias/snippet.

        This signature is signed with a secret that guarantees that valid signatures cannot be spoofed; use this when
        it is necessary to audit the invocations of an alias (e.g. to ensure that a server version of the alias is being
        used over a personal version).

        Use :meth:`verify_signature` in a separate alias to verify the integrity of a generated signature and unpack
        the encoded data.

        :param int data: Some user-supplied data to encode in the signature. This must be an unsigned integer that fits
            within 5 bits (i.e. a value [0..31]). Default 0.
        :rtype: str
        """
        data = int(data)
        workshop_collection_id = (
            self.invoking_object.collection_id if isinstance(self.invoking_object, WorkshopCollectableObject) else None
        )
        return create_signature(
            self.ctx,
            execution_scope=self.execution_scope,
            user_data=data,
            workshop_collection_id=workshop_collection_id,
        )

    def verify_signature(self, data):
        """
        Verifies that a given signature is valid. The signature should have been generated by :func:`signature`.

        If the signature is not valid, raises a ValueError. Otherwise, returns a dict with the following keys
        representing the context the given signature was generated in:

        .. code:: text

            {
                "message_id": int,
                "channel_id": int,
                "author_id": int,
                "timestamp": float,
                "workshop_collection_id": str?,  # None if the caller was not a workshop object
                "scope": str,  # one of UNKNOWN, PERSONAL_ALIAS, SERVER_ALIAS, PERSONAL_SNIPPET, SERVER_SNIPPET, COMMAND_TEST
                "user_data": int,
                "guild_id": int?,  # may be None
                "guild": AliasGuild?,  # may be None
                "channel": AliasChannel?,  # may be None
                "author": AliasAuthor?,  # may be None
            }

        :param str data: The signature to verify.
        :rtype: dict
        """
        data = str(data)
        return verify_signature(self.ctx, data)

    def using(self, **imports):
        """
        Imports Draconic global variables as modules in the current namespace. See :ref:`using-imports` for details.

        Usually this should be the first statement in a code block if imports are used.

        .. warning::

            Only import modules from trusted sources! The entire contents of an imported module is executed once upon
            import, and can do bad things like delete all of your variables.

        >>> using(
        ...     hello="50943a96-381b-427e-adb9-eea8ebf61f27"
        ... )
        >>> hello.hello()
        "Hello world!"
        """
        user_ns = self._names
        for ns, addr in imports.items():
            # prevent circular imports: if *addr* is already on the import stack, raise an ImportError
            if addr in self._import_stack:
                circle = " imports\n".join(self._import_stack)
                raise ImportError(f"Circular import detected!\n{circle} imports\n{addr}")
            self._import_stack.append(addr)
            try:
                self._import_one(ns, str(addr), user_ns)
            finally:
                self._import_stack.pop()
        self._names = user_ns

    def _import_one(self, name: str, addr: str, user_ns: dict):
        """Import the module at the gvar address *addr* into the *user_ns* under the name *name*"""
        # get the module contents
        mod_contents = self.get_gvar(addr)
        if mod_contents is None:
            raise ModuleNotFoundError(f"No gvar named {addr!r}")

        try:
            # if the module is in cache, return the ns from cache
            mod_ns = self._cache["imports"][addr]
        except KeyError:
            # create a new for the execution
            self._names = {}
            # add a recursion depth to prevent super-nested imports
            self._depth += 1
            if self._depth > self._config.max_recursion_depth:
                raise RecursionError("Maximum recursion depth exceeded")
            # run the gvar
            try:
                self.execute_module(mod_contents, module_name=addr)
            finally:
                self._depth -= 1
            # create a namespace and cache it
            mod_ns = SimpleNamespace(**self._names)
            self._cache["imports"][addr] = mod_ns

        # bind to user's global ns
        if name in self.builtins:
            raise ValueError(f"{name} is already builtin (no shadow assignments).")
        user_ns[name] = mod_ns

    # ==== warnings ====
    def _eval(self, node):
        last_node = self._aliasing_current_node
        self._aliasing_current_node = node  # record the node currently being evaluated
        try:
            return super()._eval(node)
        finally:
            self._aliasing_current_node = last_node

    def warn_deprecated(self, what: str, since: str, replacement: str | None):
        """Record a deprecated warning."""
        if self._aliasing_current_node in self._nodes_with_warnings:
            return
        self._nodes_with_warnings.add(self._aliasing_current_node)
        msg = f"`{what}` is deprecated (since {since}) and will be removed in a future version."
        if replacement:
            msg += f"\nUse `{replacement}` instead."
        warn = ScriptingWarning(msg=msg, node=self._aliasing_current_node, expr=self._expr)
        self.warnings.append(warn)

    def deprecated(self, since: str, replacement: str | None):
        """Decorator to mark a function as deprecated and record a deprecation warning when executed."""

        def wrapper(func):
            @functools.wraps(func)
            def inner(*args, **kwargs):
                self.warn_deprecated(f"{func.__name__}()", since, replacement)
                return func(*args, **kwargs)

            return inner

        return wrapper

    # ==== evaluation ====
    def _preflight(self):
        """We don't want limits to reset."""
        pass

    async def transformed_str_async(
        self, string, execution_scope: ExecutionScope = ExecutionScope.UNKNOWN, invoking_object: _CodeInvokerT = None
    ):
        """Async convenience method around :meth:`ScriptingEvaluator.transformed_str`."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.transformed_str, string, execution_scope, invoking_object
        )

    def transformed_str(
        self, string, execution_scope: ExecutionScope = ExecutionScope.UNKNOWN, invoking_object: _CodeInvokerT = None
    ):
        """
        Parses a scripting string (evaluating text in {{}}). The caller should pass the execution scope and invoking
        object in order to populate metadata about the call context.
        """
        self.execution_scope = execution_scope
        self.invoking_object = invoking_object
        ops = r"([-+*/().<>=])"

        def evalrepl(match):
            if match.group("lookup"):  # <>
                if re.match(r"<a?([@#]|:.+:)[&!]{0,2}\d+>", match.group(0)):  # ignore mentions
                    return match.group(0)
                out = match.group("lookup")
                evalresult = str(self.names.get(out, out))
            elif match.group("roll"):  # {}
                varstr = match.group("roll")
                curlyout = ""
                for substr in re.split(ops, varstr):
                    temp = substr.strip()
                    curlyout += str(self.names.get(temp, temp)) + " "
                try:
                    evalresult = str(self._limited_roll(curlyout))
                except:
                    evalresult = "0"
            elif match.group("drac1"):  # {{}}
                expr = match.group("drac1").strip()
                try:
                    evalresult = self.eval(expr)
                except Exception as ex:
                    raise EvaluationError(ex, expr)
            elif match.group("drac2"):  # <drac2>...</drac2>
                expr = textwrap.dedent(match.group("drac2")).strip()
                try:
                    evalresult = self.execute(expr)
                except Exception as ex:
                    raise EvaluationError(ex, expr)
            else:
                evalresult = None

            return str(evalresult) if evalresult is not None else ""

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        return output


class AutomationEvaluator(MathEvaluator):
    @classmethod
    def with_caster(cls, caster):
        names = caster.get_scope_locals()
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
                if match.group("drac1"):  # {{}}
                    evalresult = self.eval(match.group("drac1").strip())
                elif match.group("roll"):  # {}
                    try:
                        evalresult = self.eval(match.group("roll").strip())
                    except:
                        evalresult = match.group(0)
                else:
                    evalresult = None
            except Exception as ex:
                raise EvaluationError(ex, match.group(0))

            return str(evalresult) if evalresult is not None else ""

        output = re.sub(SCRIPTING_RE, evalrepl, string)  # evaluate

        if original_names:
            self.builtins = original_names

        return output


if __name__ == "__main__":
    e = ScriptingEvaluator(None)
    while True:
        print(e.eval(input()))
