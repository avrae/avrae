import json
import logging
import textwrap

import pytest

from aliasing.evaluators import SpellEvaluator
from cogs5e.models import automation
from cogs5e.models.sheet.statblock import StatBlock
from gamedata.compendium import compendium
from tests.conftest import end_init, start_init
from tests.utils import active_character, active_combat, requires_data

log = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio

DEFAULT_CASTER = StatBlock("Bob")
DEFAULT_EVALUATOR = SpellEvaluator.with_caster(DEFAULT_CASTER)


@pytest.mark.parametrize("attack_bonus", [
    # valid inputs
    "3", "dexterityMod", "{dexterityMod}", "dexterityMod + proficiencyBonus", "{dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel"
])
async def test_attack_strs(attack_bonus):
    attack = automation.Attack(hit=[], miss=[], attackBonus=attack_bonus)
    result = attack.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"Attack str: ({attack_bonus=!r}) -> {result}")
    assert result


@pytest.mark.parametrize("dc", [
    # valid inputs
    "12", "dexterityMod", "{dexterityMod}", "8 + dexterityMod + proficiencyBonus",
    "{8 + dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel"
])
async def test_save_strs(dc):
    save = automation.Save(stat='str', fail=[], success=[], dc=dc)
    result = save.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"Save str: ({dc=!r}) -> {result}")
    assert result


# ==== IEffect ====
@pytest.mark.usefixtures("character", "init_fixture")
class TestIEffect:
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
            "stacking": True
        }
        result = automation.IEffect.from_data(data)
        assert result
        assert result.name == 'Sleepy'
        assert result.duration == 5
        assert result.effects == '-ac -1'
        assert result.tick_on_end is False
        assert result.concentration is False
        assert result.desc == "I'm just really sleepy"

    async def test_serialize(self):
        result = automation.IEffect('Sleepy', 5, '-ac -1').to_dict()
        assert json.dumps(result)

    async def test_stacking_e2e(self, character, avrae, dhttp):
        avrae.message(textwrap.dedent('''
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
        ''').strip())
        await dhttp.drain()

        avrae.message('!a "Stacking IEffect Test"')
        await dhttp.drain()
        avrae.message('!a "Stacking IEffect Test"')
        await dhttp.drain()

        char = await active_character(avrae)
        combat = await active_combat(avrae)
        combatant = combat.get_combatant(char.name, strict=True)
        assert combatant.get_effect('Sleepy', strict=True)
        assert combatant.get_effect('Sleepy x2', strict=True)

    async def test_ieffect_teardown(self, avrae, dhttp):  # end init to set up for more character params
        await end_init(avrae, dhttp)


# ==== Text ====
class TestText:
    async def test_valid_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test","automation":[{"type": "text", "text": {"id": 75, "typeId": 12168134}}],"_v":2}')
        avrae.message('!a "Text Test"')
        await dhttp.drain()

    async def test_missing_entitlement_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test2","automation":[{"type": "text", "text": {"id": -75, "typeId": 12168134}}],"_v":2}')
        avrae.message('!a "Text Test2"')
        await dhttp.drain()

    async def test_invalid_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test3","automation":[{"type": "text", "text": {"id": -9999999, "typeId": 12168134}}],"_v":2}')
        avrae.message('!a "Text Test3"')
        await dhttp.drain()

    async def test_invalid2_entityreference(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name":"Text Test4","automation":[{"type": "text", "text": {"id": 2102, "typeId": 1118725998}}],"_v":2}')
        await dhttp.drain()
        avrae.message('!a "Text Test4"')
        await dhttp.drain()


# ==== UseCounter ====
@requires_data()
async def import_usecounter_actions(avrae, dhttp):
    avrae.message(textwrap.dedent('''
    !a import {
        "name": "UseCounter Test",
        "automation": [{
            "type": "counter",
            "counter": "Bardic Inspiration",
            "amount": "1"
        }],
        "_v": 2
    }
    ''').strip())
    avrae.message(textwrap.dedent('''
    !a import {
        "name": "UseCounter Test2",
        "automation": [{
            "type": "counter",
            "counter": {"slot": 3},
            "amount": "1"
        }],
        "_v": 2
    }
    ''').strip())
    avrae.message(textwrap.dedent('''
    !a import {
        "name": "UseCounter Test3",
        "automation": [{
            "type": "counter",
            "counter": {"id": 75, "typeId": 12168134},
            "amount": "1"
        }],
        "_v": 2
    }
    ''').strip())
    avrae.message(textwrap.dedent('''
    !a import {
        "name": "UseCounter Test4",
        "automation": [{
            "type": "counter",
            "counter": {"slot": "3 if True else 0"},
            "amount": "1"
        }],
        "_v": 2
    }
    ''').strip())
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
        'type': 'counter',
        'counter': 'Bardic Inspiration',
        'amount': '5',
        'allowOverflow': True,
        'errorBehaviour': None
    }
    result = automation.UseCounter.from_data(data)
    assert result
    assert result.counter == 'Bardic Inspiration'
    assert result.amount == '5'
    assert result.allow_overflow is True
    assert result.error_behaviour is None

    data = {
        'type': 'counter',
        'counter': 'Bardic Inspiration',
        'amount': '5'
    }
    result = automation.UseCounter.from_data(data)
    assert result
    assert result.allow_overflow is False
    assert result.error_behaviour == 'warn'

    data = {
        'type': 'counter',
        'counter': {'slot': 3},
        'amount': '1'
    }
    result = automation.UseCounter.from_data(data)
    assert result
    assert isinstance(result.counter, automation.effects.usecounter.SpellSlotReference)
    assert result.counter.slot == 3

    data = {
        'type': 'counter',
        'counter': {'id': 75, 'typeId': 12168134},
        'amount': '5'
    }
    result = automation.UseCounter.from_data(data)
    assert result
    assert isinstance(result.counter, automation.effects.usecounter.AbilityReference)
    assert result.counter.entity is compendium.lookup_entity(12168134, 75)


async def test_usecounter_serialize():
    result = automation.UseCounter('Bardic Inspiration', '1').to_dict()
    assert json.dumps(result)  # result should be JSON-encodable

    result = automation.UseCounter(automation.effects.usecounter.SpellSlotReference(1), '1').to_dict()
    assert json.dumps(result)

    result = automation.UseCounter(automation.effects.usecounter.AbilityReference(12168134, 75), '1').to_dict()
    assert json.dumps(result)


@pytest.mark.parametrize("counter", [
    # counters by name
    "counter", "other counter name",
    # spell slot
    automation.effects.usecounter.SpellSlotReference(1), automation.effects.usecounter.SpellSlotReference(9),
    automation.effects.usecounter.SpellSlotReference("3 if True else 0"),
    # ability reference
    automation.effects.usecounter.AbilityReference(12168134, 75),
    automation.effects.usecounter.AbilityReference(-1, -1)
])
@pytest.mark.parametrize("amount", [
    # valid inputs
    "1", "proficiencyBonus", "{proficiencyBonus}", "dexterityMod + proficiencyBonus",
    "{dexterityMod + proficiencyBonus}",
    # inputs that should be NaN
    "foobar", "{}", "dexterymod", "RogueLevel", "1d4"
])
async def test_usecounter_build_str(counter, amount):
    usecounter = automation.UseCounter(counter, amount)
    result = usecounter.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
    log.info(f"UseCounter str: ({counter=!r}, {amount=!r}) -> {result}")
    assert result
