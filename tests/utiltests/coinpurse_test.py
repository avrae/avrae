from cogs5e.utils.gameutils import resolve_strict_coins, parse_coin_args
from cogs5e.models.sheet.coinpurse import CoinsArgs, Coinpurse
import pytest
from cogs5e.models.errors import InvalidArgument

pytestmark = pytest.mark.asyncio


def test_parse_coin_args():
    assert parse_coin_args("+10") == CoinsArgs(gp=10, explicit=False)
    assert parse_coin_args("+10cp +10gp -8ep") == CoinsArgs(gp=10, ep=-8, cp=10, explicit=True)
    assert parse_coin_args("-10.47") == CoinsArgs(gp=-10, sp=-4, cp=-7, explicit=False)
    assert parse_coin_args("+10.388888") == CoinsArgs(gp=10, sp=3, cp=8, explicit=False)


async def test_resolve_strict_coins():
    assert await resolve_strict_coins(Coinpurse(pp=10),
                                      CoinsArgs(pp=-1, explicit=False)) == CoinsArgs(pp=-1)
    assert await resolve_strict_coins(Coinpurse(pp=10, gp=10, sp=10),
                                      CoinsArgs(cp=-1, explicit=False)) == CoinsArgs(sp=-1, cp=9)
    assert await resolve_strict_coins(Coinpurse(pp=1),
                                      CoinsArgs(cp=-1, explicit=False)) == CoinsArgs(pp=-1, gp=9, ep=1, sp=4, cp=9)
    with pytest.raises(InvalidArgument):
        await resolve_strict_coins(Coinpurse(gp=1),
                                   CoinsArgs(pp=-1, explicit=False))


def test_coin_autoconvert_down():
    assert Coinpurse(pp=10)\
               .auto_convert_down(CoinsArgs(cp=-1)) == CoinsArgs(pp=-1, gp=9, ep=1, sp=4, cp=9)
    assert Coinpurse(pp=10, gp=3, cp=1)\
               .auto_convert_down(CoinsArgs(cp=-2)) == CoinsArgs(gp=-1, ep=1, sp=4, cp=8)
    with pytest.raises(InvalidArgument):
        Coinpurse(gp=1)\
            .auto_convert_down(CoinsArgs(pp=-1, explicit=False))


def test_coin_autoconvert_up():
    assert Coinpurse(pp=10, gp=9, ep=1, sp=4, cp=9)\
               .consolidate_coins() == CoinsArgs()
    assert Coinpurse(pp=10, gp=9, ep=1, sp=4, cp=10)\
               .consolidate_coins() == CoinsArgs(pp=1, gp=-9, ep=-1, sp=-4, cp=-10)
    assert Coinpurse(pp=10, gp=9, ep=1, sp=4, cp=1234)\
               .consolidate_coins() == CoinsArgs(pp=2, gp=-7, ep=-1, sp=-2, cp=-1230)


def test_coin_compactstring():
    assert Coinpurse(pp=10, gp=3, cp=1)\
               .compact_string() == "<:DDBGold:948681049221775370> 103.01 gp"
    assert Coinpurse(pp=10, gp=1003, cp=1)\
               .compact_string() == "<:DDBGold:948681049221775370> 1,103.01 gp"
    assert Coinpurse(pp=210, gp=1003, ep=11, cp=1)\
               .compact_string() == "<:DDBGold:948681049221775370> 3,108.51 gp"
    assert Coinpurse(cp=1)\
               .compact_string() == "<:DDBGold:948681049221775370> 0.01 gp"

    assert Coinpurse(pp=10, gp=3, cp=1)\
               .compact_string(delta=-234.1) == "<:DDBGold:948681049221775370> 103.01 gp (-234.10)"
    assert Coinpurse(pp=10, gp=1003, cp=1)\
               .compact_string(delta=-234.1) == "<:DDBGold:948681049221775370> 1,103.01 gp (-234.10)"
    assert Coinpurse(pp=210, gp=1003, ep=11, cp=1)\
               .compact_string(delta=-234.1) == "<:DDBGold:948681049221775370> 3,108.51 gp (-234.10)"
    assert Coinpurse(cp=1)\
               .compact_string(delta=-2334.1) == "<:DDBGold:948681049221775370> 0.01 gp (-2,334.10)"


def test_coin_coin_string():
    assert Coinpurse(pp=10, gp=3, cp=1)\
               .coin_string('cp') == "<:DDBCopper:948681049217597480> 1 cp"
    assert Coinpurse(pp=10, gp=1003, cp=1)\
               .coin_string('gp') == "<:DDBGold:948681049221775370> 1,003 gp"
    assert Coinpurse(pp=210, gp=1003, ep=11, cp=1)\
               .coin_string('ep') == "<:DDBElectrum:948681048932364401> 11 ep"
    assert Coinpurse(cp=1)\
               .coin_string('pp') == "<:DDBPlatinum:948681049326624849> 0 pp"

    assert Coinpurse(pp=10, gp=3, cp=1)\
               .coin_string('cp', delta=-234) == "<:DDBCopper:948681049217597480> 1 cp (-234)"
    assert Coinpurse(pp=10, gp=1003, cp=1)\
               .coin_string('gp', delta=234) == "<:DDBGold:948681049221775370> 1,003 gp (+234)"
    assert Coinpurse(pp=210, gp=1003, ep=11, cp=1)\
               .coin_string('ep', delta=-234) == "<:DDBElectrum:948681048932364401> 11 ep (-234)"
    assert Coinpurse(cp=1)\
               .coin_string('pp', delta=-2334) == "<:DDBPlatinum:948681049326624849> 0 pp (-2,334)"
