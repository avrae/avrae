from cogs5e.initiative.combatant import Combatant
from cogs5e.initiative.effects import InitiativeEffect
from cogs5e.models.automation.entities import AutomationCombatant, AutomationEffect
from tests.utils import ContextBotProxy


def make_combatant(bot, name: str) -> Combatant:
    return Combatant(
        ctx=ContextBotProxy(bot),
        combat=None,
        id=name.lower(),
        name=name,
        controller_id=1,
        private=False,
        init=10,
    )


def add_effect(combatant: Combatant, name: str) -> InitiativeEffect:
    effect = InitiativeEffect.new(combat=None, combatant=combatant, name=name)
    combatant.add_effect(effect)
    return effect


def test_get_effect_by_name_matches_strict_and_partial(avrae):
    combatant = make_combatant(avrae, "Fighter")
    add_effect(combatant, "Bless")
    add_effect(combatant, "Bane")

    auto = AutomationCombatant(combatant)

    effect = auto.get_effect_by_name("bless")
    assert isinstance(effect, AutomationEffect)
    assert effect.name == "Bless"

    exact_on_partial_flag = auto.get_effect_by_name("Bless", strict=False)
    assert exact_on_partial_flag and exact_on_partial_flag.name == "Bless"

    partial = auto.get_effect_by_name("ban", strict=False)
    assert partial and partial.name == "Bane"

    assert auto.get_effect_by_name("nope", strict=True) is None
    assert not isinstance(effect, InitiativeEffect)
