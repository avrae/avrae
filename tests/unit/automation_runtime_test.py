import disnake

from cogs5e.initiative.combatant import Combatant
from cogs5e.initiative.group import CombatantGroup
from cogs5e.models.automation.entities import AutomationCombatant, AutomationGroup
from cogs5e.models.automation.runtime import AutomationContext
from cogs5e.models.sheet.statblock import StatBlock
from tests.utils import ContextBotProxy
from utils.argparser import ParsedArguments


class DummyCombat:
    def __init__(self, round_num=1, current=None):
        self.round_num = round_num
        self._current = current

    @property
    def current_combatant(self):
        return self._current


def build_context(bot, combat, *, targets=None, caster=None):
    return AutomationContext(
        ctx=ContextBotProxy(bot),
        embed=disnake.Embed(),
        caster=caster or StatBlock("Caster"),
        targets=targets or [],
        args=ParsedArguments.empty_args(),
        combat=combat,
    )


def make_combatant(bot, name: str, *, init_value: int = 10):
    return Combatant(
        ctx=ContextBotProxy(bot),
        combat=None,
        id=name.lower(),
        name=name,
        controller_id=1,
        private=False,
        init=init_value,
    )


def test_automation_context_turn_metavars_wrap_combatant(avrae):
    current = make_combatant(avrae, "Rogue", init_value=14)
    combat = DummyCombat(round_num=4, current=current)

    autoctx = build_context(avrae, combat)

    assert autoctx.metavars["combatRound"] == 4
    assert isinstance(autoctx.metavars["turnCombatant"], AutomationCombatant)
    assert autoctx.metavars["turnCombatant"].init == 14
    assert [c.name for c in autoctx.metavars["turnCombatants"]] == ["Rogue"]


def test_automation_context_turn_metavars_for_group(avrae):
    members = [make_combatant(avrae, "Goblin A"), make_combatant(avrae, "Goblin B")]
    group = CombatantGroup(
        ctx=ContextBotProxy(avrae), combat=None, id="grp", combatants=members, name="Goblin Mob", init=12
    )
    combat = DummyCombat(round_num=2, current=group)

    autoctx = build_context(avrae, combat)

    assert isinstance(autoctx.metavars["turnCombatant"], AutomationGroup)
    assert [c.name for c in autoctx.metavars["turnCombatants"]] == ["Goblin A", "Goblin B"]


def test_target_metavars_wrap_combatants(avrae):
    target = make_combatant(avrae, "Bandit")
    combat = DummyCombat(round_num=1, current=None)

    autoctx = build_context(avrae, combat, targets=[target])

    assert isinstance(autoctx.metavars["targets"][0], AutomationCombatant)
