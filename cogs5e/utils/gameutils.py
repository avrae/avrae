from cogs5e.models.initiative import Combatant


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
