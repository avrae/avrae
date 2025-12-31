from types import SimpleNamespace

from aliasing.api.combat import SimpleEffect
from cogs5e.initiative.effects.effect import InitiativeEffect


def test_simpleeffect_exposes_tick_on_combatant_id():
    combatant = SimpleNamespace(name="Target")
    effect = InitiativeEffect(
        combat=None,
        combatant=combatant,  # type: ignore
        id="effect-1",
        name="Test Effect",
        tick_on_combatant_id="caster-123",
    )

    simple_effect = SimpleEffect(effect)

    assert simple_effect.tick_on_combatant_id == "caster-123"
