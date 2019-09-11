from cogs5e.models.character import Character
from cogs5e.models.errors import CombatNotFound
from cogs5e.models.initiative import Combat, CombatantGroup
from utils.argparser import argparse


async def maybe_combat(ctx, caster, args, allow_groups=True):
    """
    If channel not in combat: returns caster, target_list, None unmodified.
    If channel in combat but caster not: returns caster, list of combatants, combat.
    If channel in combat and caster in combat: returns caster as combatant, list of combatants, combat.
    """
    target_args = args.get('t')
    targets = []

    try:
        combat = await Combat.from_ctx(ctx)
    except CombatNotFound:
        for i, target in enumerate(target_args):
            if '|' in target:
                target, contextargs = target.split('|', 1)
                args.add_context(target, argparse(contextargs))
            targets.append(target)
        return caster, targets, None

    # get targets as Combatants
    for i, t in enumerate(target_args):
        contextargs = None
        if '|' in t:
            t, contextargs = t.split('|', 1)
            contextargs = argparse(contextargs)

        target = await combat.select_combatant(t, f"Select target #{i + 1}.", select_group=allow_groups)

        if isinstance(target, CombatantGroup):
            for combatant in target.get_combatants():
                if contextargs:
                    args.add_context(combatant, contextargs)
                targets.append(combatant)
        else:
            if contextargs:
                args.add_context(target, contextargs)
            targets.append(target)

    # get caster as Combatant if caster in combat
    if isinstance(caster, Character):
        caster = next(
            (c for c in combat.get_combatants() if getattr(c, 'character_id', None) == caster.upstream),
            caster
        )
    return caster, targets, combat
