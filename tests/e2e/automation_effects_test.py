import copy
import json
import logging
import textwrap

import disnake
import pytest

from aliasing.evaluators import AutomationEvaluator
from cogs5e.initiative.utils import InteractionMessageType, combatant_interaction_components
from cogs5e.models import automation
from cogs5e.models.sheet.statblock import StatBlock
from gamedata.compendium import compendium
from tests.utils import active_character, active_combat, end_init, requires_data, start_init

log = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio

DEFAULT_CASTER = StatBlock("Bob")
DEFAULT_EVALUATOR = AutomationEvaluator.with_caster(DEFAULT_CASTER)


@pytest.mark.parametrize(
    "attack_bonus",
    [
        # valid inputs
        "3",
        "dexterityMod",
        "{dexterityMod}",
        "dexterityMod + proficiencyBonus",
        "{dexterityMod + proficiencyBonus}",
        # inputs that should be NaN
        "foobar",
        "{}",
        "dexterymod",
        "RogueLevel",
    ],
)
async def test_attack_strs(attack_bonus):
    attack = automation.Attack(hit=[], miss=[], attackBonus=attack_bonus)
    result = attack.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"Attack str: ({attack_bonus=!r}) -> {result}")
    assert result


@pytest.mark.parametrize(
    "dc",
    [
        # valid inputs
        "12",
        "dexterityMod",
        "{dexterityMod}",
        "8 + dexterityMod + proficiencyBonus",
        "{8 + dexterityMod + proficiencyBonus}",
        # inputs that should be NaN
        "foobar",
        "{}",
        "dexterymod",
        "RogueLevel",
    ],
)
async def test_save_strs(dc):
    save = automation.Save(stat="str", fail=[], success=[], dc=dc)
    result = save.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"Save str: ({dc=!r}) -> {result}")
    assert result


# ==== IEffect ====
@pytest.mark.usefixtures("character", "init_fixture")
class TestLegacyIEffect:
    async def test_ieffect_setup(self, avrae, dhttp):
        await start_init(avrae, dhttp)
        avrae.message("!init join")
        await dhttp.drain()

    async def test_deserialize(self):
        data = {
            "type": "ieffect",
            "name": "Sleepy",
            "duration": 5,
            "effects": "-ac -1",
            "conc": False,
            "desc": "I'm just really sleepy",
            "stacking": True,
        }
        result = automation.LegacyIEffect.from_data(data)
        assert result
        assert result.name == "Sleepy"
        assert result.duration == 5
        assert result.effects == "-ac -1"
        assert result.tick_on_end is False
        assert result.concentration is False
        assert result.desc == "I'm just really sleepy"

    async def test_serialize(self):
        result = automation.LegacyIEffect("Sleepy", 5, "-ac -1").to_dict()
        assert json.dumps(result)

    async def test_stacking_e2e(self, character, avrae, dhttp):
        avrae.message(
            textwrap.dedent(
                """
        !a import {
          "name": "Stacking IEffect Test",
          "_v": 2,
          "automation": [
            {
              "type": "target",
              "target": "self",
              "effects": [
                {
                  "type": "ieffect",
                  "name": "Sleepy",
                  "duration": 5,
                  "effects": "-ac -1",
                  "conc": true,
                  "desc": "I'm just really sleepy",
                  "stacking": true
                }
              ]
            }
          ]
        }
        """
            ).strip()
        )
        await dhttp.drain()

        avrae.message('!a "Stacking IEffect Test"')
        await dhttp.drain()
        avrae.message('!a "Stacking IEffect Test"')
        await dhttp.drain()

        char = await active_character(avrae)
        combat = await active_combat(avrae)
        combatant = combat.get_combatant(char.name, strict=True)
        assert combatant.get_effect("Sleepy", strict=True)
        assert combatant.get_effect("Sleepy x2", strict=True)

    async def test_ieffect_teardown(self, avrae, dhttp):  # end init to set up for more character params
        await end_init(avrae, dhttp)


@pytest.mark.usefixtures("character", "init_fixture")
class TestIEffect:
    dict_data = {
        "type": "ieffect2",
        "name": "Burning",
        "effects": {"save_dis": ["all"], "damage_bonus": "1 [fire]"},
        "attacks": [{
            "attack": {
                "name": "Burning Hand (not the spell)",
                "_v": 2,
                "automation": [
                    {"type": "target", "target": "each", "effects": [{"type": "damage", "damage": "1d8[fire]"}]}
                ],
            }
        }],
        "buttons": [
            {
                "label": "Take Fire Damage",
                "verb": "is burning",
                "style": 4,
                "automation": [
                    {"type": "target", "target": "self", "effects": [{"type": "damage", "damage": "1d6[fire]"}]}
                ],
            },
            {
                "label": "Douse",
                "verb": "puts themself out",
                "automation": [{"type": "text", "text": "ok still no remove effect yet lol"}],
            },
        ],
    }

    attack_data = textwrap.dedent(
        """
        name: New Button Test
        _v: 2
        automation:
          - type: target
            target: self
            effects:
              - type: ieffect2
                name: Prone
                buttons:
                  - label: Stand Up
                    verb: stands up
                    style: 3
                    automation:
                      - type: text
                        text: ok I haven't implemented removing effects yet lol
              - type: ieffect2
                name: Burning
                effects:
                  save_dis: [ all ]
                  damage_bonus: 1 [fire]
                attacks:
                  - attack:
                      name: Burning Hand (not the spell)
                      _v: 2
                      automation:
                        - type: target
                          target: each
                          effects:
                            - type: damage
                              damage: 1d8[fire]
                buttons:
                  - label: Take Fire Damage
                    verb: is burning
                    style: 4
                    automation:
                      - type: target
                        target: self
                        effects:
                          - type: damage
                            damage: 1d6[fire]
                  - label: Douse
                    verb: puts themself out
                    automation:
                      - type: text
                        text: ok still no remove effect yet lol
              - type: ieffect2
                name: Parent Test
                save_as: parent_test
                buttons:
                  - label: ping children
                    verb: lists all the child effects
                    automation:
                      - type: target
                        target: children
                        effects:
                          - type: text
                            text: "{target.name} has a child effect"
          - type: target
            target: each
            effects:
              - type: ieffect2
                name: Child Effect
                parent: parent_test
                buttons:
                  - label: ping parent
                    automation:
                      - type: target
                        target: parent
                        effects:
                          - type: text
                            text: "{target.name} has the parent effect"
        """
    ).strip()

    async def test_ieffect_setup(self, avrae, dhttp):
        await start_init(avrae, dhttp)
        avrae.message("!init join")
        await dhttp.drain()

    async def test_deserialize(self):
        result = automation.IEffect.from_data(copy.deepcopy(self.dict_data))
        assert result
        assert result.name == "Burning"
        assert result.duration is None
        assert result.effects.data == {"save_dis": ["all"], "damage_bonus": "1 [fire]"}
        assert len(result.attacks) == 1
        assert result.attacks[0].attack.name == "Burning Hand (not the spell)"
        assert len(result.buttons) == 2
        assert result.buttons[0].label == "Take Fire Damage"
        assert result.buttons[1].label == "Douse"
        assert result.end_on_turn_end is False
        assert result.concentration is False
        assert result.desc is None
        assert not result.stacking
        assert result.save_as is None
        assert result.parent is None

    async def test_serialize(self):
        effect = automation.IEffect.from_data(copy.deepcopy(self.dict_data))
        serialized1 = effect.to_dict()
        # since serialization adds some attrs that are optional, we re-deserialize and serialize again to test
        # consistency
        deserialized2 = automation.IEffect.from_data(copy.deepcopy(serialized1))
        serialized2 = deserialized2.to_dict()
        assert serialized1 == serialized2

    async def test_buttons_e2e(self, character, avrae, dhttp):
        avrae.message(f"!a import {self.attack_data}")
        await dhttp.drain()

        avrae.message(f'!a "New Button Test" -t "{character.name}"')
        await dhttp.drain()

        char = await active_character(avrae)
        combat = await active_combat(avrae)
        combatant = combat.get_combatant(char.name, strict=True)

        # make sure it added all the effects
        assert combatant.get_effect("Prone", strict=True)
        assert combatant.get_effect("Burning", strict=True)
        assert combatant.get_effect("Parent Test", strict=True)
        assert combatant.get_effect("Child Effect", strict=True)

        # check the list of available buttons - should be Stand Up, Take Fire Damage, Douse, ping children, ping parent
        buttons = combatant_interaction_components(combatant, InteractionMessageType.TURN_MESSAGE)
        assert len(buttons) == 5
        assert [b.label for b in buttons] == ["Stand Up", "Take Fire Damage", "Douse", "ping children", "ping parent"]
        assert [b.style for b in buttons] == [
            disnake.ButtonStyle.success,
            disnake.ButtonStyle.danger,
            disnake.ButtonStyle.primary,
            disnake.ButtonStyle.primary,
            disnake.ButtonStyle.primary,
        ]

        # ieb:<combatant_id>:<effect_id>:<button_id>
        assert all(b.custom_id.startswith(f"ieb:{combatant.id}:") for b in buttons)

        # check parenting
        child = combatant.get_effect("Child Effect", strict=True)
        parent = combatant.get_effect("Parent Test", strict=True)
        assert child.get_parent_effect() is parent
        assert next(parent.get_children_effects()) is child

    async def test_ieffect_teardown(self, avrae, dhttp):  # end init to set up for more character params
        await end_init(avrae, dhttp)


# ==== Text ====
class TestText:
    async def test_valid_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test","automation":[{"type": "text", "text": {"id": 75, "typeId":'
            ' 12168134}}],"_v":2}'
        )
        await dhttp.drain()
        avrae.message('!a "Text Test"')
        await dhttp.drain()

    async def test_missing_entitlement_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test2","automation":[{"type": "text", "text": {"id": -75, "typeId":'
            ' 12168134}}],"_v":2}'
        )
        await dhttp.drain()
        avrae.message('!a "Text Test2"')
        await dhttp.drain()

    async def test_invalid_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test3","automation":[{"type": "text", "text": {"id": -9999999, "typeId":'
            ' 12168134}}],"_v":2}'
        )
        await dhttp.drain()
        avrae.message('!a "Text Test3"')
        await dhttp.drain()

    async def test_invalid2_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test4","automation":[{"type": "text", "text": {"id": 2102, "typeId":'
            ' 1118725998}}],"_v":2}'
        )
        await dhttp.drain()
        avrae.message('!a "Text Test4"')
        await dhttp.drain()


# ==== UseCounter ====
@requires_data()
async def import_usecounter_actions(avrae, dhttp):
    avrae.message(
        textwrap.dedent(
            """
    !a import {
        "name": "UseCounter Test",
        "automation": [{
            "type": "counter",
            "counter": "Bardic Inspiration",
            "amount": "1"
        }],
        "_v": 2
    }
    """
        ).strip()
    )
    avrae.message(
        textwrap.dedent(
            """
    !a import {
        "name": "UseCounter Test2",
        "automation": [{
            "type": "counter",
            "counter": {"slot": 3},
            "amount": "1"
        }],
        "_v": 2
    }
    """
        ).strip()
    )
    avrae.message(
        textwrap.dedent(
            """
    !a import {
        "name": "UseCounter Test3",
        "automation": [{
            "type": "counter",
            "counter": {"id": 75, "typeId": 12168134},
            "amount": "1"
        }],
        "_v": 2
    }
    """
        ).strip()
    )
    avrae.message(
        textwrap.dedent(
            """
    !a import {
        "name": "UseCounter Test4",
        "automation": [{
            "type": "counter",
            "counter": {"slot": "3 if True else 0"},
            "amount": "1"
        }],
        "_v": 2
    }
    """
        ).strip()
    )
    await dhttp.drain()


async def test_usecounter_e2e(character, avrae, dhttp):
    await import_usecounter_actions(avrae, dhttp)

    avrae.message('!a "UseCounter Test"')
    await dhttp.drain()
    char = await active_character(avrae)
    if bi := char.get_consumable("Bardic Inspiration"):
        assert bi.value < bi.get_max()
        avrae.message('!cc reset "Bardic Inspiration"')
        await dhttp.drain()

    avrae.message('!a "UseCounter Test2"')
    await dhttp.drain()
    char = await active_character(avrae)
    assert char.spellbook.get_slots(3) == 0 or char.spellbook.get_slots(3) < char.spellbook.get_max_slots(3)

    avrae.message('!a "UseCounter Test3"')
    await dhttp.drain()
    char = await active_character(avrae)
    if bi := char.get_consumable("Bardic Inspiration"):
        assert bi.value < bi.get_max()

    avrae.message('!a "UseCounter Test4"')
    await dhttp.drain()
    char = await active_character(avrae)
    assert char.spellbook.get_slots(3) == 0 or char.spellbook.get_slots(3) < char.spellbook.get_max_slots(3)


async def test_usecounter_e2e_ignore(character, avrae, dhttp):
    await import_usecounter_actions(avrae, dhttp)

    avrae.message('!a "UseCounter Test" -i')
    await dhttp.drain()
    char = await active_character(avrae)
    if bi := char.get_consumable("Bardic Inspiration"):
        assert bi.value == bi.get_max()

    avrae.message('!a "UseCounter Test2" -i')
    await dhttp.drain()
    char = await active_character(avrae)
    assert char.spellbook.get_slots(3) == char.spellbook.get_max_slots(3)

    avrae.message('!a "UseCounter Test3" -i')
    await dhttp.drain()
    char = await active_character(avrae)
    if bi := char.get_consumable("Bardic Inspiration"):
        assert bi.value == bi.get_max()


async def test_usecounter_deserialize():
    data = {
        "type": "counter",
        "counter": "Bardic Inspiration",
        "amount": "5",
        "allowOverflow": True,
        "errorBehaviour": None,
    }
    result = automation.UseCounter.from_data(data)
    assert result
    assert result.counter == "Bardic Inspiration"
    assert result.amount == "5"
    assert result.allow_overflow is True
    assert result.error_behaviour is None

    data = {"type": "counter", "counter": "Bardic Inspiration", "amount": "5"}
    result = automation.UseCounter.from_data(data)
    assert result
    assert result.allow_overflow is False
    assert result.error_behaviour == "warn"

    data = {"type": "counter", "counter": {"slot": 3}, "amount": "1"}
    result = automation.UseCounter.from_data(data)
    assert result
    assert isinstance(result.counter, automation.effects.usecounter.SpellSlotReference)
    assert result.counter.slot == 3

    data = {"type": "counter", "counter": {"id": 75, "typeId": 12168134}, "amount": "5"}
    result = automation.UseCounter.from_data(data)
    assert result
    assert isinstance(result.counter, automation.effects.usecounter.AbilityReference)
    assert result.counter.entity is compendium.lookup_entity(12168134, 75)


async def test_usecounter_serialize():
    result = automation.UseCounter("Bardic Inspiration", "1").to_dict()
    assert json.dumps(result)  # result should be JSON-encodable

    result = automation.UseCounter(automation.effects.usecounter.SpellSlotReference(1), "1").to_dict()
    assert json.dumps(result)

    result = automation.UseCounter(automation.effects.usecounter.AbilityReference(12168134, 75), "1").to_dict()
    assert json.dumps(result)


@pytest.mark.parametrize(
    "counter",
    [
        # counters by name
        "counter",
        "other counter name",
        # spell slot
        automation.effects.usecounter.SpellSlotReference(1),
        automation.effects.usecounter.SpellSlotReference(9),
        automation.effects.usecounter.SpellSlotReference("3 if True else 0"),
        # ability reference
        automation.effects.usecounter.AbilityReference(12168134, 75),
        automation.effects.usecounter.AbilityReference(-1, -1),
    ],
)
@pytest.mark.parametrize(
    "amount",
    [
        # valid inputs
        "1",
        "proficiencyBonus",
        "{proficiencyBonus}",
        "dexterityMod + proficiencyBonus",
        "{dexterityMod + proficiencyBonus}",
        # inputs that should be NaN
        "foobar",
        "{}",
        "dexterymod",
        "RogueLevel",
        "1d4",
    ],
)
async def test_usecounter_build_str(counter, amount):
    usecounter = automation.UseCounter(counter, amount)
    result = usecounter.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"UseCounter str: ({counter=!r}, {amount=!r}) -> {result}")
    assert result


# ==== Check ====
async def import_check_actions(avrae, dhttp):
    avrae.message(
        textwrap.dedent(
            """
            !a import {
              "_v": 2,
              "name": "Check Test",
              "automation": [
                {
                  "type": "target",
                  "target": "each",
                  "effects": [
                    {
                      "type": "check",
                      "ability": [
                        "arcana",
                        "dexterity",
                        "animalHandling"
                      ],
                      "dc": 15,
                      "success": [
                        {
                          "type": "text",
                          "text": "yay you passed"
                        }
                      ],
                      "fail": [
                        {
                          "type": "text",
                          "text": "you failed :("
                        }
                      ]
                    },
                    {
                      "type": "check",
                      "ability": "arcana"
                    },
                    {
                      "type": "text",
                      "text": "after arcana"
                    }
                  ]
                }
              ]
            }
            """
        ).strip()
    )
    avrae.message(
        textwrap.dedent(
            """
            !a import {
              "_v": 2,
              "name": "Contest Check Test",
              "automation": [
                {
                  "type": "target",
                  "target": "each",
                  "effects": [
                    {
                      "type": "check",
                      "ability": [
                        "arcana",
                        "dexterity",
                        "animalHandling"
                      ],
                      "contestAbility": [
                        "athletics",
                        "acrobatics"
                      ],
                      "success": [
                        {
                          "type": "text",
                          "text": "the target wins"
                        }
                      ],
                      "fail": [
                        {
                          "type": "text",
                          "text": "the caster wins"
                        }
                      ]
                    }
                  ]
                }
              ]
            }
            """
        ).strip()
    )
    await dhttp.drain()


async def test_check_e2e(character, avrae, dhttp):
    await import_check_actions(avrae, dhttp)
    await start_init(avrae, dhttp)
    avrae.message("!init join")
    await dhttp.drain()

    avrae.message(f'!a "Check Test" -t "{character.name}"')
    await dhttp.drain()

    avrae.message(f'!a "Contest Check Test" -t "{character.name}"')
    await dhttp.drain()

    await end_init(avrae, dhttp)


async def test_check_deserialize():
    data = {"type": "check", "ability": "arcana"}
    result = automation.Check.from_data(data)
    assert result
    assert result.ability_list == ["arcana"]
    assert result.contest_ability_list is None
    assert result.dc is None
    assert result.contest_tie_behaviour is None

    data = {"type": "check", "ability": ["arcana", "acrobatics"]}
    result = automation.Check.from_data(data)
    assert result
    assert result.ability_list == ["arcana", "acrobatics"]

    data = {"type": "check", "ability": ["arcana", "acrobatics"], "dc": "15"}
    result = automation.Check.from_data(data)
    assert result
    assert result.dc == "15"

    data = {"type": "check", "ability": ["arcana", "acrobatics"], "contestAbility": "athletics"}
    result = automation.Check.from_data(data)
    assert result
    assert result.contest_ability_list == ["athletics"]


async def test_check_serialize():
    result = automation.Check("acrobatics").to_dict()
    assert json.dumps(result)  # result should be JSON-encodable

    result = automation.Check(["acrobatics", "arcana"]).to_dict()
    assert json.dumps(result)


async def test_check_build_str():
    check = automation.Check(ability="arcana")
    result = check.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    assert result == "Arcana Check"

    check = automation.Check(ability=["arcana", "acrobatics"])
    result = check.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    assert result == "Arcana or Acrobatics Check"

    check = automation.Check(ability="arcana", dc="15")
    result = check.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    assert result == "DC 15 Arcana Check"

    check = automation.Check(ability="arcana", contestAbility="arcana")
    result = check.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    assert result == "Arcana Check vs. caster's Arcana Check"
