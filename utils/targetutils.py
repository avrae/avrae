from cogs5e.models.character import Character
from cogs5e.models.errors import CombatNotFound
from cogs5e.models.initiative import Combat, CombatantGroup


async def maybe_combat(ctx, caster, target_list, allow_groups=True):
    """
    If channel not in combat: returns caster, target_list, None unmodified.
    If channel in combat but caster not: returns caster, list of combatants, combat.
    If channel in combat and caster in combat: returns caster as combatant, list of combatants, combat.
    """
    try:
        combat = await Combat.from_ctx(ctx)
    except CombatNotFound:
        return caster, target_list, None

    # get targets as Combatants
    targets = []
    for i, t in enumerate(target_list):
        target = await combat.select_combatant(t, f"Select target #{i + 1}.", select_group=allow_groups)
        if isinstance(target, CombatantGroup):
            targets.extend(target.get_combatants())
        else:
            targets.append(target)

    # get caster as Combatant if caster in combat
    if isinstance(caster, Character):
        caster = next(
            (c for c in combat.get_combatants() if getattr(c, 'character_id', None) == caster.upstream),
            caster
        )
    return caster, targets, combat
