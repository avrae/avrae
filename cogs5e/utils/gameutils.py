import re
from typing import Optional

from cogs5e.initiative import Combatant
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.coinpurse import CoinsArgs
from utils.constants import COIN_TYPES
from utils.enums import CoinsAutoConvert
from utils.functions import confirm


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


async def send_current_coin(ctx, character, coin: Optional[str] = None, deltas: CoinsArgs = None):
    """
    Sends the current contents of the CoinPurse.
    If ``coin`` is passed, it must be a valid coin type and will only show the amount of that specific coin.
    """
    if coin is not None and (coin := coin.lower()) not in COIN_TYPES:
        raise ValueError(f"{coin!r} is not a valid coin type.")
    if not deltas:
        deltas = CoinsArgs()

    delta_total = (deltas.pp * 10) + deltas.gp + (deltas.ep * 0.5) + (deltas.sp * 0.1) + (deltas.cp * 0.01)

    cp_display_embed = EmbedWithCharacter(character, name=False)
    cp_display_embed.set_thumbnail(url="https://www.dndbeyond.com/attachments/thumbnails/3/929/650/358/scag01-04.png")
    cp_display_embed.add_field(
        name="Total Value", value=character.coinpurse.compact_string(delta=delta_total), inline=False
    )
    if coin is None:
        cp_display_embed.title = f"{character.name}'s Coinpurse"
        if not character.options.compact_coins:
            cp_display_embed.description = "\n".join(
                character.coinpurse.coin_string(coin_type, getattr(deltas, coin_type)) for coin_type in COIN_TYPES
            )
    else:
        cp_display_embed.title = f"{character.name}'s {COIN_TYPES[coin]['name']} Pieces"
        cp_display_embed.description = character.coinpurse.coin_string(coin)

    await ctx.send(embed=cp_display_embed)


def parse_coin_args(args: str) -> CoinsArgs:
    """
    Parses a user's coin string into a representation of each currency.
    If the user input is a decimal number, assumes gold pieces.
    Otherwise, allows the user to specify currencies in the form ``/(([+-]?\\d+)\\s*([pgesc]p)?)+/``
    (e.g. +1gp -2sp 3cp).
    """

    # Remove commas, in the case of `+3,104gp` or `-2,000.05`
    args = args.replace(",", "")
    try:
        return _parse_coin_args_float(float(args))
    except ValueError:
        return _parse_coin_args_re(args)


def _parse_coin_args_float(coins: float) -> CoinsArgs:
    """
    Parses a float into currencies. The input is assumed to be in gp, and any sub-cp values will be truncated.
    """
    # if any sub-copper passed (i.e. 1-thousandth), truncate it
    total_copper = int(round(coins * 100, 1))

    if coins < 0:
        # If it's a negative value, remove all the lowest coins first
        return CoinsArgs(cp=total_copper)
    else:
        return CoinsArgs(gp=total_copper // 100, sp=(total_copper % 100) // 10, cp=total_copper % 10)


def _parse_coin_args_re(args: str) -> CoinsArgs:
    """
    Parses a currency string into currencies. Duplicates of the same currency will be summed.
    Examples:
    10gp -10sp 1pp -> CoinsArgs(pp=1, gp=10, ep=0, sp=-10, cp=0)
    +10gp -10pp -> CoinsArgs(pp=-10, gp=10, ep=0, sp=0, cp=0)
    -10gp 50gp 1gp -> CoinsArgs(pp=0, gp=41, ep=0, sp=0, cp=0)
    """
    is_valid = re.fullmatch(r"(([+-]?\d+)\s*([pgesc]p)\s*)+", args, re.IGNORECASE)
    if not is_valid:
        raise InvalidArgument("Coins must be a number or a currency string, e.g. `+101.2` or `10cp +101gp -2sp`.")

    out = CoinsArgs(explicit=True)
    for coin_match in re.finditer(r"(?P<amount>[+-]?\d+)\s*(?P<currency>[pgesc]p)", args, re.IGNORECASE):
        amount = int(coin_match["amount"])
        currency = coin_match["currency"]

        if currency == "pp":
            out.pp += amount
        elif currency == "gp":
            out.gp += amount
        elif currency == "ep":
            out.ep += amount
        elif currency == "sp":
            out.sp += amount
        else:
            out.cp += amount

    return out


async def resolve_strict_coins(coinpurse, coins: CoinsArgs, ctx, mode: CoinsAutoConvert = 0):
    if (coinpurse.total + coins.total) < 0:
        raise InvalidArgument("You cannot put a currency into negative numbers.")
    if not all((
        coinpurse.pp + coins.pp >= 0,
        coinpurse.gp + coins.gp >= 0,
        coinpurse.ep + coins.ep >= 0,
        coinpurse.sp + coins.sp >= 0,
        coinpurse.cp + coins.cp >= 0,
    )):
        if mode == CoinsAutoConvert.NEVER or (
            mode == CoinsAutoConvert.ASK
            and coins.explicit
            and not await confirm(
                ctx,
                (
                    "You don't have enough of the chosen coins to complete this transaction"
                    ". Auto convert from other coins? (Reply with yes/no)"
                ),
            )
        ):
            raise InvalidArgument("You cannot put a currency into negative numbers.")
        coins = coinpurse.auto_convert_down(coins)
    return coins
