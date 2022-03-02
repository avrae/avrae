import re
from collections import namedtuple
from cogs5e.initiative import Combatant

CoinsArgs = namedtuple("CoinsArgs", "pp gp ep sp cp")

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

async def send_coinpurse(ctx, character, coin="All"):
    """
    Sends the result of coinpurse
    """
    
    await ctx.send(f"Contents of Coinpurse: {character.coinpurse.to_dict()}")

def parse_coinpurse_args(args:str):
    """
    TODO: Parsing will be here
    Parsing Coinpurse String
    Regex: ([+-](\d+)(p|g|e|s|c)p\s*)+
    """
    parse = re.search("\s(([+-]?[0-9]{0,}\.?[0-9]?)([a-zA-Z]{1}p)*)+", args).group(1)
    return parse