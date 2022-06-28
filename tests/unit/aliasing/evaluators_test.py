import textwrap

import draconic
import pytest
import yaml.constructor

from aliasing.evaluators import ScriptingEvaluator
from tests.utils import ContextBotProxy

pytestmark = pytest.mark.asyncio


async def test_yaml_loading(draconic_evaluator):
    result = draconic_evaluator.eval("load_yaml('key: one')['key']")
    assert type(result) is draconic_evaluator._str
    assert result == "one"

    result = draconic_evaluator.eval("load_yaml('[1, 2, 3]')")
    assert type(result) is draconic_evaluator._list
    assert result == [1, 2, 3]

    result = draconic_evaluator.eval("load_yaml(4)")
    assert type(result) is int
    assert result == 4


async def test_yaml_types(draconic_evaluator):
    yaml_string = textwrap.dedent(
        """
        key1:
          nested_key1: 06-08-2012
          nested_key2: value2
          nested_key3: value3
        thing1: one
        thing2: two
        thing3:
          - 1
          - 2
          - 3
    """
    )
    draconic_evaluator.builtins["yaml_string"] = yaml_string

    result = draconic_evaluator.eval("load_yaml(yaml_string)")
    assert result == {
        "key1": {"nested_key1": "06-08-2012", "nested_key2": "value2", "nested_key3": "value3"},
        "thing1": "one",
        "thing2": "two",
        "thing3": [1, 2, 3],
    }
    assert type(result) is draconic_evaluator._dict
    assert type(result["key1"]) is draconic_evaluator._dict
    assert type(result["thing1"]) is draconic_evaluator._str
    assert type(result["thing3"]) is draconic_evaluator._list

    result = draconic_evaluator.eval("load_yaml('key: /X17unp5WZmZgAAAOfn515eXvPz7Y6O')")
    assert result == {"key": "/X17unp5WZmZgAAAOfn515eXvPz7Y6O"}
    assert type(result) is draconic_evaluator._dict
    assert type(result["key"]) is draconic_evaluator._str

    result = draconic_evaluator.eval("load_yaml('key: 3.1415')")
    assert result == {"key": 3.1415}
    assert type(result) is draconic_evaluator._dict
    assert type(result["key"]) is float

    result = draconic_evaluator.eval("load_yaml('key: true\\nkey2: \"true\"')")
    assert result == {"key": True, "key2": "true"}
    assert type(result) is draconic_evaluator._dict
    assert type(result["key"]) is bool
    assert type(result["key2"]) is draconic_evaluator._str

    result = draconic_evaluator.eval("load_yaml('key: 2001-02-03')")
    assert result == {"key": "2001-02-03"}
    assert type(result) is draconic_evaluator._dict
    assert type(result["key"]) is draconic_evaluator._str

    result = draconic_evaluator.eval("load_yaml('key: ~')")
    assert result == {"key": None}
    assert type(result) is draconic_evaluator._dict
    assert result["key"] is None


async def test_yaml_dumping(draconic_evaluator):
    # we eval instead of assigning to builtin for typing
    draconic_evaluator.eval(
        'data = {"name": "Dice", "age": "old", "languages": 3, "drinks": ["beer", "wine", "apple juice"]}'
    )
    expected_data = textwrap.dedent(
        """
    name: Dice
    age: old
    languages: 3
    drinks:
    - beer
    - wine
    - apple juice
    """
    ).strip()

    result = draconic_evaluator.eval("dump_yaml(data)")
    assert result.strip() == expected_data
    result = draconic_evaluator.eval("load_yaml(dump_yaml(data)) == data")
    assert result

    # sets are serialized as generic sequences
    result = draconic_evaluator.eval("load_yaml(dump_yaml({1, 2, 3}))")
    assert result == [1, 2, 3]


async def test_parsing_json(draconic_evaluator):
    jsonable_data = {"hello": "world", "number": 1, "bool": True, "null": None, "list": [1, "two", 3.0]}
    draconic_evaluator.builtins["data"] = jsonable_data
    result = draconic_evaluator.eval("load_yaml(dump_json(data))")
    assert result == jsonable_data


async def test_anchors(draconic_evaluator):
    # scalar anchors
    expr = textwrap.dedent(
        """
    - &flag Apple
    - Beachball
    - Cartoon
    - Duckface
    - *flag
    """
    )
    draconic_evaluator.builtins["yaml_string"] = expr
    result = draconic_evaluator.eval("load_yaml(yaml_string)")
    assert result == ["Apple", "Beachball", "Cartoon", "Duckface", "Apple"]
    assert type(result) is draconic_evaluator._list

    # mapping anchors
    expr = textwrap.dedent(
        """
    template: &foo
      game: Portal 2
      type: Turret
      functional: true
      tags:
        - 1
        - 2
        - 3
    response: *foo
    """
    )
    draconic_evaluator.builtins["yaml_string"] = expr
    result = draconic_evaluator.eval("load_yaml(yaml_string)")
    print(result)
    assert result == {
        "template": {"game": "Portal 2", "type": "Turret", "functional": True, "tags": [1, 2, 3]},
        "response": {"game": "Portal 2", "type": "Turret", "functional": True, "tags": [1, 2, 3]},
    }
    assert type(result) is draconic_evaluator._dict
    assert type(result["template"]["tags"]) is type(result["response"]["tags"]) is draconic_evaluator._list


async def test_naughty_yaml(draconic_evaluator):
    # taken from pyyaml docs
    ex1 = textwrap.dedent(
        """
    none: [~, null]
    bool: [true, false, on, off]
    int: 42
    float: 3.14159
    list: [LITE, RES_ACID, SUS_DEXT]
    dict: {hp: 13, sp: 5}
    """
    )
    draconic_evaluator.builtins["ex1"] = ex1
    assert draconic_evaluator.eval("load_yaml(ex1)") == {
        "none": [None, None],
        "int": 42,
        "float": 3.1415899999999999,
        "list": ["LITE", "RES_ACID", "SUS_DEXT"],
        "dict": {"hp": 13, "sp": 5},
        "bool": [True, False, True, False],
    }

    ex2 = textwrap.dedent(
        """
    !!python/object:__main__.Hero
    name: Welthyr Syxgon
    hp: 1200
    sp: 0
    """
    )
    draconic_evaluator.builtins["ex2"] = ex2
    with pytest.raises(draconic.AnnotatedException) as e:
        draconic_evaluator.eval("load_yaml(ex2)")
    assert isinstance(e.value.original, yaml.constructor.ConstructorError)

    # extra tests from dice
    extra_expressions = {
        """
        # map: safe
        Block style: !!map
          Clark : Evans
          Brian : Ingerson
          Oren  : Ben-Kiki
        """: {
            "Block style": {"Clark": "Evans", "Brian": "Ingerson", "Oren": "Ben-Kiki"}
        },
        """
        Bestiary: !!omap
          - aardvark: African pig-like ant eater. Ugly.
          - anteater: South-American ant eater. Two species.
          - anaconda: South-American constrictor snake. Scaly.
        """: {
            "Bestiary": [
                ("aardvark", "African pig-like ant eater. Ugly."),
                ("anteater", "South-American ant eater. Two species."),
                ("anaconda", "South-American constrictor snake. Scaly."),
            ]
        },
        """
        # pairs: Safe
        Block tasks: !!pairs
          - meeting: with team.
          - meeting: with boss.
          - break: lunch.
          - meeting: with client.
        """: {
            "Block tasks": [
                ("meeting", "with team."),
                ("meeting", "with boss."),
                ("break", "lunch."),
                ("meeting", "with client."),
            ]
        },
        """
        # set: safe
        baseball teams: !!set { Boston Red Sox, Detroit Tigers, New York Yankees }
        """: {
            "baseball teams": {"Boston Red Sox", "New York Yankees", "Detroit Tigers"}
        },
        """
        # seq: Safe
        Block style: !!seq
          - Mercury
          - Venus
          - Earth
        """: {
            "Block style": ["Mercury", "Venus", "Earth"]
        },
        """
        # bools
        canonical: y
        answer: NO
        logical: True
        option: on
        """: {
            "canonical": "y",
            "answer": False,
            "logical": True,
            "option": True,
        },
        """
        # floats
        canonical: 6.8523015e+5
        exponentioal: 685.230_15e+03
        fixed: 685_230.15
        sexagesimal: 190:20:30.15
        floater: !!float 0
        """: {
            "canonical": 685230.15,
            "exponentioal": 685230.15,
            "fixed": 685230.15,
            "sexagesimal": 685230.15,
            "floater": 0.0,
        },
        """
        # ints
        canonical: 685230
        decimal: +685_230
        octal: 02472256
        hexadecimal: 0x_0A_74_AE
        binary: 0b1010_0111_0100_1010_1110
        sexagesimal: 190:20:30
        """: {
            "canonical": 685230,
            "decimal": 685230,
            "octal": 685230,
            "hexadecimal": 685230,
            "binary": 685230,
            "sexagesimal": 685230,
        },
        """
        # nulls
        sparse:
          - ~
          - 2nd entry
          -
          - 4th entry
          - Null
        empty:
        canonical: ~
        english: null
        ~: null key
        """: {
            "sparse": [None, "2nd entry", None, "4th entry", None],
            "empty": None,
            "canonical": None,
            "english": None,
            None: "null key",
        },
        """
        # timestamps
        canonical:        2001-12-15T02:59:43.1Z
        valid iso8601:    2001-12-14t21:59:43.10-05:00
        space separated:  2001-12-14 21:59:43.10 -5
        no time zone (Z): 2001-12-15 2:59:43.10
        date (00:00:00Z): 2002-12-14
        """: {
            "canonical": "2001-12-15T02:59:43.1Z",
            "valid iso8601": "2001-12-14t21:59:43.10-05:00",
            "space separated": "2001-12-14 21:59:43.10 -5",
            "no time zone (Z)": "2001-12-15 2:59:43.10",
            "date (00:00:00Z)": "2002-12-14",
        },
        """
        # binary: mapped to str
        canonical: !!binary "\
         R0lGODlhDAAMAIQAAP//9/X17unp5WZmZgAAAOfn515eXvPz7Y6OjuDg4J+fn5\
         OTk6enp56enmlpaWNjY6Ojo4SEhP/++f/++f/++f/++f/++f/++f/++f/++f/+\
         +f/++f/++f/++f/++f/++SH+Dk1hZGUgd2l0aCBHSU1QACwAAAAADAAMAAAFLC\
         AgjoEwnuNAFOhpEMTRiggcz4BNJHrv/zCFcLiwMWYNG84BwwEeECcgggoBADs="
        """: {
            "canonical": (
                "         R0lGODlhDAAMAIQAAP//9/X17unp5WZmZgAAAOfn515eXvPz7Y6OjuDg4J+fn5"
                "         OTk6enp56enmlpaWNjY6Ojo4SEhP/++f/++f/++f/++f/++f/++f/++f/++f/+"
                "         +f/++f/++f/++f/++f/++SH+Dk1hZGUgd2l0aCBHSU1QACwAAAAADAAMAAAFLC"
                "         AgjoEwnuNAFOhpEMTRiggcz4BNJHrv/zCFcLiwMWYNG84BwwEeECcgggoBADs="
            )
        },
        """
        # pyYAML types
        py_bool: !!python/bool true
        py_bytes: !!python/bytes (bytes in Python 3)
        py_str: !!python/str str (str in Python 3)
        py_str_2: !!python/unicode unicode (str in Python 3)
        py_int: !!python/int 1
        py_long: !!python/long 1
        py_float: !!python/float 1
        py_complex: !!python/complex 1j
        py_list: !!python/list [1, 2, 3]
        py_tuple: !!python/tuple [1, 2]
        py_dict: !!python/dict {'one': 'two'}
        """: yaml.constructor.ConstructorError,
        """
        # scaries - these get mapped to strs, as if the tag doesn't exist
        scaries: 
        - !!python/name:dbot.COGS 1
        - !!python/module:dbot 1
        - !!python/object:__main__.avrae 1
        - !!python/object/new:dbot.Avrae 1
        - !!python/object/apply:dbot.Avrae 1
        """: {
            "scaries": ["1", "1", "1", "1", "1"]
        },
    }

    for expr, expected_result in extra_expressions.items():
        expr = textwrap.dedent(expr)
        draconic_evaluator.builtins["data"] = expr

        if isinstance(expected_result, type) and issubclass(expected_result, BaseException):
            with pytest.raises(draconic.AnnotatedException) as e:
                draconic_evaluator.eval("load_yaml(data)")
            assert isinstance(e.value.original, expected_result)
        else:
            result = draconic_evaluator.eval("load_yaml(data)")
            assert result == expected_result


# ==== evaulator fixture ====
@pytest.fixture(scope="function")
def draconic_evaluator(avrae):
    yield ScriptingEvaluator(ctx=ContextBotProxy(avrae))
