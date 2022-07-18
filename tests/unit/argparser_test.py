import pytest
from disnake.ext.commands import ExpectedClosingQuoteError

from cogs5e.models.errors import InvalidArgument
from utils.argparser import argparse, argquote, argsplit
from utils import argparser
from utils.enums import AdvantageType


def test_argsplit():
    assert argsplit("""foo bar "two words" yay!""") == ["foo", "bar", "two words", "yay!"]
    assert argsplit("""'some string here' in quotes""") == ["some string here", "in", "quotes"]
    assert argsplit(""""partial quoted"blocks""") == ["partial quotedblocks"]
    assert argsplit('''"'nested quotes'"''') == ["'nested quotes'"]
    assert argsplit("""-phrase "She said, \\"Hello world\\"" """) == ["-phrase", 'She said, "Hello world"']


def test_apostrophes():
    assert argsplit("foo bar") == ["foo", "bar"]
    assert argsplit("'foo bar'") == ["foo bar"]
    assert argsplit("foo's bar") == ["foo's", "bar"]
    assert argsplit('''"foo's bar"''') == ["foo's bar"]
    assert argsplit("el'ven'ame") == ["el'ven'ame"]
    assert argsplit("darius'") == ["darius'"]
    assert argsplit("Samus' Armor") == ["Samus'", "Armor"]
    with pytest.raises(ExpectedClosingQuoteError):
        argsplit("'tis")
    assert argsplit("'tis Jack's") == ["tis Jacks"]  # weird


def test_argquote():
    assert argquote("foo") == "foo"
    assert argquote("foo bar") == '"foo bar"'
    assert argquote('one "two three"') == '"one \\"two three\\""'
    assert argsplit(argquote('one "two three"')) == ['one "two three"']


def test_argparse():
    args = argparse("""-phrase "hello world" -h argument -t or1 -t or2""")
    assert args.last("phrase") == "hello world"
    assert args.get("t") == ["or1", "or2"]
    assert args.adv() == 0
    assert args.last("t") == "or2"
    assert args.last("h", type_=bool) is True
    assert "argument" in args
    assert args.last("notin", default=5) == 5

    args = argparse("""adv""")
    assert args.adv() == AdvantageType.ADV

    args = argparse("""adv dis adv""")
    assert args.adv() == AdvantageType.NONE

    args = argparse("""adv dis eadv""")
    assert args.adv(eadv=True) == AdvantageType.NONE

    args = argparse("""eadv""")
    assert args.adv(eadv=True) == AdvantageType.ELVEN

    args = argparse("""adv eadv""")
    assert args.adv(eadv=True) == AdvantageType.ELVEN


def test_argparse_adv():
    """
    16 cases: (adv, dis, ea, ea arg in .adv())

    a d e ea | out
    =========+====
    0 0 0 0  | 0
    0 0 0 1  | 0
    0 0 1 0  | 0
    0 0 1 1  | 2
    0 1 0 0  | -1
    0 1 0 1  | -1
    0 1 1 0  | -1
    0 1 1 1  | 0
    1 0 0 0  | 1
    1 0 0 1  | 1
    1 0 1 0  | 1
    1 0 1 1  | 2
    1 1 0 0  | 0
    1 1 0 1  | 0
    1 1 1 0  | 0
    1 1 1 1  | 0

    """
    args = argparse("")
    assert args.adv() == AdvantageType.NONE
    assert args.adv(eadv=True) == AdvantageType.NONE

    args = argparse("eadv")
    assert args.adv() == AdvantageType.NONE
    assert args.adv(eadv=True) == AdvantageType.ELVEN

    args = argparse("dis")
    assert args.adv() == AdvantageType.DIS
    assert args.adv(eadv=True) == AdvantageType.DIS

    args = argparse("dis eadv")
    assert args.adv() == AdvantageType.DIS
    assert args.adv(eadv=True) == AdvantageType.NONE

    args = argparse("adv")
    assert args.adv() == AdvantageType.ADV
    assert args.adv(eadv=True) == AdvantageType.ADV

    args = argparse("adv eadv")
    assert args.adv() == AdvantageType.ADV
    assert args.adv(eadv=True) == AdvantageType.ELVEN

    args = argparse("adv dis")
    assert args.adv() == AdvantageType.NONE
    assert args.adv(eadv=True) == AdvantageType.NONE

    args = argparse("adv dis eadv")
    assert args.adv() == AdvantageType.NONE
    assert args.adv(eadv=True) == AdvantageType.NONE


def test_argparse_custom_adv():
    args = argparse("custom_adv")
    custom_adv = {
        "adv": "custom_adv",
    }

    assert args.adv(custom=custom_adv) == AdvantageType.ADV
    assert args.adv() == AdvantageType.NONE

    custom_dis = {"dis": "custom_dis"}
    assert args.adv(custom=custom_dis) == AdvantageType.NONE

    args = argparse("custom_dis")

    assert args.adv(custom=custom_dis) == AdvantageType.DIS
    assert args.adv() == AdvantageType.NONE

    custom_ea = {"eadv": "custom_ea"}
    args = argparse("custom_ea")

    assert args.adv(eadv=True, custom=custom_ea) == AdvantageType.ELVEN
    assert args.adv() == AdvantageType.NONE


def test_argparse_ephem():
    args = argparse("""-d 1 -d5 1d6 adv1""")
    for _ in range(4):
        assert args.join("d", "+", ephem=True) == "1+1d6"
    assert args.last("d", ephem=True) == "1d6"

    # we have consumed all 5 uses of ephem:d
    assert args.join("d", "+", ephem=True) == "1"
    assert args.last("d", ephem=True) == "1"

    # one ephem:adv
    # yes, this looks weird
    assert not args.adv(ephem=False)
    assert args.adv(ephem=True)
    assert not args.adv(ephem=True)

    # multiple different durations
    args = argparse("""-d2 1d6 -d1 1d4 -d 1 -d3 1d8""")
    assert args.last("d", ephem=True) == "1d8"
    assert args.join("d", "+", ephem=True) == "1d6+1d4+1+1d8"
    assert args.join("d", "+", ephem=True) == "1d6+1+1d8"
    assert args.join("d", "+", ephem=True) == "1"


def test_argparse_idempotency():
    args = argparse("")
    assert "foo" not in args
    assert args.get("foo") == []
    assert args.get("foo") == args.get("foo")
    assert "foo" not in args
    assert args.last("foo") is None
    assert args.last("foo") == args.last("foo")
    assert "foo" not in args
    assert args.join("foo", ",") is None
    assert args.join("foo", ",") == args.join("foo", ",")
    assert "foo" not in args


def test_contextual_argparse():
    args = argparse("-d 5")
    args.add_context("foo", argparse('-d 1 -phrase "I am foo"'))
    args.add_context("bar", argparse('-d 2 -phrase "I am bar"'))
    args.add_context("baz", {"d": ["3"], "phrase": ["I am baz"]})

    with pytest.raises(InvalidArgument):
        args.add_context(1, {1: ["a", "b"]})
    with pytest.raises(InvalidArgument):
        args.add_context(2, {"a": [1, "b"]})
    with pytest.raises(InvalidArgument):
        args.add_context(3, 1)

    args.set_context("foo")
    assert args.last("d") == "1"
    assert args.get("d") == ["5", "1"]
    assert args.last("phrase") == "I am foo"
    assert args.get("phrase") == ["I am foo"]

    args.set_context("bar")
    assert args.last("d") == "2"
    assert args.get("d") == ["5", "2"]
    assert args.last("phrase") == "I am bar"
    assert args.get("phrase") == ["I am bar"]

    args.set_context("baz")
    assert args.last("d") == "3"
    assert args.get("d") == ["5", "3"]
    assert args.last("phrase") == "I am baz"
    assert args.get("phrase") == ["I am baz"]

    args.set_context("bletch")
    assert args.last("d") == "5"
    assert args.get("d") == ["5"]
    assert args.last("phrase") is None
    assert args.get("phrase") == []

    args.set_context(None)
    assert args.last("d") == "5"
    assert args.get("d") == ["5"]
    assert args.last("phrase") is None
    assert args.get("phrase") == []


def test_contextual_ephemeral_argparse():
    args = argparse("-d3 5")
    args.add_context("foo", argparse('-d 3 -d1 1 -phrase "I am foo"'))
    args.add_context("bar", argparse('-d1 2 -phrase "I am bar"'))
    args.add_context("baz", {"d1": ["3"], "phrase": ["I am baz"]})

    args.set_context("foo")
    assert args.get("d", ephem=True) == ["5", "3", "1"]
    assert args.get("d", ephem=True) == ["5", "3"]

    args.set_context("bar")
    assert args.get("d", ephem=True) == ["5", "2"]
    assert args.get("d", ephem=True) == []

    args.set_context("baz")
    assert args.get("d", ephem=True) == ["3"]
    assert args.get("d", ephem=True) == []

    args.set_context(None)
    assert args.get("d", ephem=True) == []

    args.set_context("foo")
    assert args.get("d", ephem=True) == ["3"]


def test_argparse_random_manual_things():
    """A random manual test case when I was building the grammar, I'm lazy so this is kind of an e2e test"""
    expr = r"""
    -d1 
    -d2
    -d1 -1d6
    -d1 -15
    -t d1
    -d 
    "-d6"
    hello
    world
    t
    -phrase "hello world"
    -phrase "and I said \"hello world\""
    -phrase hello
    -i
    -t -i
    adv
    -dtype fire>cold
    adv1
    -d1 ea2
    "this is junk"
    12345
    !*&^#&(*#
    """
    args = argparse(expr)
    assert args.get("d", ephem=True) == ["True", "True", "-1d6", "-15", "True", "hello", "ea2"]
    assert args.get("t") == ["d1", "True", "True"]
    assert args.get("phrase") == ["hello world", 'and I said "hello world"', "hello"]
    assert args.get("i") == ["True", "True"]
    assert args.get("adv", ephem=True) == ["True", "True"]
    assert args.get("ea") == []


def test_argparse_arg_yielder():
    assert argparser._argparse_arg(name="d", ephem=None, value=True, idx=0, parse_ephem=True) == argparser.Argument(
        "d", True, 0
    )
    assert argparser._argparse_arg(
        name="d", ephem="1", value=True, idx=0, parse_ephem=True
    ) == argparser.EphemeralArgument("d", True, 0, 1)
    assert argparser._argparse_arg(name="d", ephem=None, value=True, idx=0, parse_ephem=False) == argparser.Argument(
        "d", True, 0
    )
    assert argparser._argparse_arg(name="d", ephem="1", value=True, idx=0, parse_ephem=False) == argparser.Argument(
        "d1", True, 0
    )


def test_argparse_iter_dfa():
    """
    The argparse iterator is a DFA: https://cdn.discordapp.com/attachments/755143872321028206/997195043666399272/36A37A81-E068-445A-A113-3639709D9D11.jpg
    We can test it by testing each state transition.
    """
    # None -> None -...> EOF
    assert list(argparser._argparse_iterator(["12345", "this is junk", "!*&^#&(*#"], True)) == []
    # None -(emit!)-> None -...> EOF
    assert list(argparser._argparse_iterator(["d", "d1", "adv1", "adv", "-i"], True)) == [
        argparser.Argument("d", True, 0),
        argparser.EphemeralArgument("d", True, 1, 1),
        argparser.EphemeralArgument("adv", True, 2, 1),
        argparser.Argument("adv", True, 3),
        argparser.Argument("i", True, 4),
    ]
    # None -> EOF
    assert list(argparser._argparse_iterator([], True)) == []
    # None -> flag -> EOF
    assert list(argparser._argparse_iterator(["-d"], True)) == [argparser.Argument("d", True, 0)]
    assert list(argparser._argparse_iterator(["-d1"], True)) == [argparser.EphemeralArgument("d", True, 0, 1)]
    # None -> flag -(value)-> None -> EOF
    assert list(argparser._argparse_iterator(["-d", "5"], True)) == [argparser.Argument("d", "5", 0)]
    assert list(argparser._argparse_iterator(["-d1", "5"], True)) == [argparser.EphemeralArgument("d", "5", 0, 1)]
    assert list(argparser._argparse_iterator(["-d", "-1d6"], True)) == [argparser.Argument("d", "-1d6", 0)]
    assert list(argparser._argparse_iterator(["-d1", "-1d6"], True)) == [argparser.EphemeralArgument("d", "-1d6", 0, 1)]
    # None -> flag -(single arg)-> None -> EOF
    assert list(argparser._argparse_iterator(["-t", "d5"], True)) == [argparser.Argument("t", "d5", 0)]
    # None -> flag -(single arg exception)-> None -> EOF
    assert list(argparser._argparse_iterator(["-t", "-i"], True)) == [
        argparser.Argument("t", True, 0),
        argparser.Argument("i", True, 1),
    ]
    # None -> flag -> flag -> EOF
    assert list(argparser._argparse_iterator(["-t", "-t"], True)) == [
        argparser.Argument("t", True, 0),
        argparser.Argument("t", True, 1),
    ]
    # since we have tested every state transition, it follows by induction that the whole thing works for arbitrary
    # length lists :D
