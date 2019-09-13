import pytest
from discord.ext.commands import ExpectedClosingQuoteError

from utils.argparser import argparse, argquote, argsplit


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
    assert args.last('phrase') == 'hello world'
    assert args.get('t') == ['or1', 'or2']
    assert args.adv() == 0
    assert args.last('t') == 'or2'
    assert args.last('h', type_=bool) is True
    assert 'argument' in args
    assert args.last('notin', default=5) == 5

    args = argparse("""adv""")
    assert args.adv() == 1

    args = argparse("""adv dis adv""")
    assert args.adv() == 0


def test_argparse_ephem():
    args = argparse("""-d5 1d6 adv1 -d 1""")
    for _ in range(4):
        assert args.join('d', '+', ephem=True) == '1+1d6'
    assert args.last('d', ephem=True) == '1d6'

    # we have consumed all 5 uses of ephem:d
    assert args.join('d', '+', ephem=True) == '1'
    assert args.last('d', ephem=True) == '1'

    # one ephem:adv
    # yes, this looks weird
    assert not args.adv(ephem=False)
    assert args.adv(ephem=True)
    assert not args.adv(ephem=True)

    # multiple different durations
    args = argparse("""-d2 1d6 -d1 1d4 -d 1 -d3 1d8""")
    assert args.last('d', ephem=True) == '1d8'
    assert args.join('d', '+', ephem=True) == '1+1d6+1d4+1d8'
    assert args.join('d', '+', ephem=True) == '1+1d6+1d8'
    assert args.join('d', '+', ephem=True) == '1'


def test_argparse_idempotency():
    args = argparse("")
    assert 'foo' not in args
    assert args.get('foo') == []
    assert args.get('foo') == args.get('foo')
    assert 'foo' not in args
    assert args.last('foo') is None
    assert args.last('foo') == args.last('foo')
    assert 'foo' not in args
    assert args.join('foo', ',') is None
    assert args.join('foo', ',') == args.join('foo', ',')
    assert 'foo' not in args


def test_contextual_argparse():
    args = argparse("-d 5")
    args.add_context("foo", argparse('-d 1 -phrase "I am foo"'))
    args.add_context("bar", argparse('-d 2 -phrase "I am bar"'))

    args.set_context('foo')
    assert args.last("d") == '1'
    assert args.get("d") == ['5', '1']
    assert args.last("phrase") == "I am foo"
    assert args.get("phrase") == ["I am foo"]

    args.set_context('bar')
    assert args.last("d") == '2'
    assert args.get("d") == ['5', '2']
    assert args.last("phrase") == "I am bar"
    assert args.get("phrase") == ["I am bar"]

    args.set_context('bletch')
    assert args.last("d") == '5'
    assert args.get("d") == ['5']
    assert args.last("phrase") is None
    assert args.get("phrase") == []

    args.set_context(None)
    assert args.last("d") == '5'
    assert args.get("d") == ['5']
    assert args.last("phrase") is None
    assert args.get("phrase") == []


def test_contextual_ephemeral_argparse():
    args = argparse("-d3 5")
    args.add_context("foo", argparse('-d 3 -d1 1 -phrase "I am foo"'))
    args.add_context("bar", argparse('-d1 2 -phrase "I am bar"'))

    args.set_context('foo')
    assert args.get("d", ephem=True) == ['3', '5', '1']
    assert args.get("d", ephem=True) == ['3', '5']

    args.set_context('bar')
    assert args.get("d", ephem=True) == ['5', '2']
    assert args.get("d", ephem=True) == []

    args.set_context(None)
    assert args.get("d", ephem=True) == []

    args.set_context('foo')
    assert args.get("d", ephem=True) == ['3']
