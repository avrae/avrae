from cogs5e.models.character import Character
from cogs5e.models.errors import InvalidArgument, SelectionException
from cogs5e.models.initiative.errors import CombatNotFound
from cogs5e.models.initiative.group import CombatantGroup
from utils.argparser import argparse


async def maybe_combat_caster(ctx, caster, combat=None):
    """
    Given a character caster, return the character's PlayerCombatant if they are in a combat in the given combat
    or current channel if combat is not passed.
    """
    if combat is None:
        try:
            combat = await ctx.get_combat()
        except CombatNotFound:
            return caster

    if isinstance(caster, Character):
        return next(
            (c for c in combat.get_combatants() if getattr(c, 'character_id', None) == caster.upstream
             and getattr(c, 'character_owner', None) == caster.owner),
            caster
        )
    return caster


async def maybe_combat(ctx, caster, args, allow_groups=True):
    """
    If channel not in combat: returns caster, target_list, None unmodified.
    If channel in combat but caster not: returns caster, list of combatants, combat.
    If channel in combat and caster in combat: returns caster as combatant, list of combatants, combat.
    """
    target_args = args.get('t')
    targets = []

    try:
        combat = await ctx.get_combat()
    except CombatNotFound:
        for i, target in enumerate(target_args):
            if '|' in target:
                target, contextargs = target.split('|', 1)
                args.add_context(target, argparse(contextargs))
            targets.append(target)
        return caster, targets, None

    # get targets as Combatants
    targets = await definitely_combat(combat, args, allow_groups)

    # get caster as Combatant if caster in combat
    caster = await maybe_combat_caster(ctx, caster, combat=combat)
    return caster, targets, combat


async def definitely_combat(combat, args, allow_groups=True):
    target_args = args.get('t')
    targets = []

    for i, t in enumerate(target_args):
        contextargs = None
        if '|' in t:
            t, contextargs = t.split('|', 1)
            contextargs = argparse(contextargs)

        try:
            target = await combat.select_combatant(t, f"Select target #{i + 1}.", select_group=allow_groups)
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

    return targets
