import dataclasses
import re
from typing import Tuple

from cogs5e.models.embeds import EmbedWithColor
from cogs5e.models.sheet.coinpurse import CoinTypes
from cogs5e.initiative import Combatant
from cogs5e.models.errors import InvalidArgument


@dataclasses.dataclass
class CoinsArgs:
    pp: int = 0
    gp: int = 0
    ep: int = 0
    sp: int = 0
    cp: int = 0


async def send_hp_result(ctx, caster, delta=None):
    """
    Sends the result of an HP modification to the appropriate channels.

    :param ctx: Discord context
    :type caster: cogs5e.models.sheet.statblock.StatBlock
    :param str delta: Optional string to display in parentheses after the hp output.
    """
    deltaend = f" ({delta})" if delta else ""

    if isinstance(caster, Combatant) and caster.is_private:
        await ctx.send(f"{caster.name}: {caster.hp_str()}")
        await caster.message_controller(ctx, f"{caster.name}'s HP: {caster.hp_str(True)}{deltaend}")
    else:
        await ctx.send(f"{caster.name}: {caster.hp_str()}{deltaend}")


async def send_current_coin(ctx, character, coin="All"):
    """
    Sends the current contents of the CoinPurse
    """
    cp_display_embed = EmbedWithColor()
    cp_display_embed.colour = 15844367
    cp_display_embed.set_footer(text=f"For help managing your coins, use !game coinpurse")
    cp_display_embed.set_thumbnail(url="https://www.dndbeyond.com/attachments/thumbnails/3/929/650/358/scag01-04.png")
    if coin == "All":
        cp_display_embed.title = f"{character.name}'s Coinpurse"
        if character.options.compact_coins:
            cp_display_embed.description = character.coinpurse.str_styled('compact')
        else:
            cp_display_embed.description = str(character.coinpurse)
    else:
        cp_display_embed.title = f"{character.name}'s {CoinTypes[coin]['name']} pieces."
        cp_display_embed.description=f"{CoinTypes[coin]['icon']} {coin}: {character.coinpurse.to_dict()[coin]:,}"

    await ctx.send(embed=cp_display_embed)


def parse_coin_args(args: str) -> tuple[CoinsArgs, bool]:
    """
    Parses a user's coin string into a representation of each currency.
    If the user input is a decimal number, assumes gold pieces.
    Otherwise, allows the user to specify currencies in the form ``/(([+-]?\d+)\s*([pgesc]p)?)+/``
    (e.g. +1gp -2sp 3cp).
    """
    try:
        return _parse_coin_args_float(float(args)), False
    except ValueError:
        return _parse_coin_args_re(args), True


def _parse_coin_args_float(coins: float) -> CoinsArgs:
    """
    Parses a float into currencies. The input is assumed to be in gp, and any sub-cp values will be truncated.
    """
    # 0.01
    # 1.12313
    total_copper = int(coins * 100)  # if any sub-copper passed (i.e. 1-thousandth), truncate it
    return CoinsArgs(
        # pp=total_copper // 1000,  #  If we are going to utilize Platinum Uncomment This
        gp=total_copper // 100,  # (total_copper % 1000) // 100  # if allowing plat
        sp=(total_copper % 100) // 10,
        cp=total_copper % 10
    )


def _parse_coin_args_re(args: str) -> CoinsArgs:
    """
    Parses a currency string into currencies. Duplicates of the same currency will be summed.
    Examples:
    10gp -10sp 1pp -> CoinsArgs(pp=1, gp=10, ep=0, sp=-10, cp=0)
    +10gp -10pp -> CoinsArgs(pp=-10, gp=10, ep=0, sp=0, cp=0)
    -10gp 50gp 1gp -> CoinsArgs(pp=0, gp=41, ep=0, sp=0, cp=0)
    """
    is_valid = re.fullmatch(r"(([+-]?\d+)\s*([pgesc]p)?\s*)+", args, re.IGNORECASE)
    if not is_valid:
        raise InvalidArgument("Coins must be a number or a currency string, e.g. `+101.2` or `10cp +101gp -2sp`.")

    out = CoinsArgs()
    for coin_match in re.finditer(r"(?P<amount>[+-]?\d+)\s*(?P<currency>[pgesc]p)?", args, re.IGNORECASE):
        amount = int(coin_match["amount"])
        currency = coin_match["currency"]

        if currency == 'pp':
            out.pp += amount
        elif currency == 'gp':
            out.gp += amount
        elif currency == 'ep':
            out.ep += amount
        elif currency == 'sp':
            out.sp += amount
        else:
            out.cp += amount

    return out
