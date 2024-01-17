from contextlib import suppress
from typing import Literal, TYPE_CHECKING

from cogs5e.initiative import CombatNotFound, CombatantGroup
from cogs5e.models.character import Character
from cogs5e.models.errors import InvalidArgument, SelectionException
from utils.argparser import ParsedArguments, argparse
from utils.functions import ordinal

if TYPE_CHECKING:
    from utils.context import AvraeContext
    from cogs5e.initiative import Combat


async def maybe_combat_caster(ctx, caster, combat=None):
    """
    Given a character caster, return the character's PlayerCombatant if they are in a combat in the given combat
    or current channel if combat is not passed.
    """
    if combat is None:
        with suppress(CombatNotFound):
            combat = await ctx.get_combat()

    if combat is not None and isinstance(caster, Character):
        combatant = next(
            (
                c
                for c in combat.get_combatants()
                if getattr(c, "character_id", None) == caster.upstream
                and getattr(c, "character_owner", None) == caster.owner
            ),
            None,
        )
        if combatant is not None:
            await combatant.update_character_ref(ctx, inst=caster)
            caster = combatant

    ctx.nlp_caster = caster  # NLP: save a reference to the caster
    return caster


async def maybe_combat(ctx, caster, args, allow_groups=True):
    """
    If channel not in combat: returns caster, target_list, None unmodified.
    If channel in combat but caster not: returns caster, list of combatants, combat.
    If channel in combat and caster in combat: returns caster as combatant, list of combatants, combat.
    """
    target_args = args.get("t")
    targets = []

    try:
        combat = await ctx.get_combat()
    except CombatNotFound:
        for i, target in enumerate(target_args):
            if "|" in target:
                target, contextargs = target.split("|", 1)
                args.add_context(target, argparse(contextargs))
            targets.append(target)
        return caster, targets, None

    # get targets as Combatants
    targets = await definitely_combat(ctx, combat, args, allow_groups)

    # get caster as Combatant if caster in combat
    caster = await maybe_combat_caster(ctx, caster, combat=combat)
    return caster, targets, combat


async def definitely_combat(ctx: "AvraeContext", combat: "Combat", args: ParsedArguments, allow_groups: bool = True):
    allow_groups: Literal[True, False]  # weird type-checking requirement to typehint the select_combatant overload
    target_args = args.get("t")
    targets = []

    for i, t in enumerate(target_args):
        contextargs = None
        if "|" in t:
            t, contextargs = t.split("|", 1)
            contextargs = argparse(contextargs)

        try:
            target = await combat.select_combatant(
                ctx,
                t,
                f"Pick your {ordinal(i+1)} target.",
                select_group=allow_groups,
            )
        except SelectionException:
            raise InvalidArgument(f"Target {t} not found.")

        if isinstance(target, CombatantGroup):
            for combatant in target.get_combatants():
                if contextargs:
                    args.add_context(combatant, contextargs)
                targets.append(combatant)
        else:
            if contextargs:
                args.add_context(target, contextargs)
            targets.append(target)

    ctx.nlp_targets = targets  # NLP: save a reference to the targets list
    return targets
