import json
import logging

import pytest

from aliasing.evaluators import SpellEvaluator
from cogs5e.models import automation
from cogs5e.models.sheet.statblock import StatBlock
from tests.utils import active_character

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


# ==== UseCounter ====
class TestUseCustomCounter:
    async def test_e2e(self, character, avrae, dhttp):
        avrae.message(
            '!a import {"name": "UseCounter Test", "automation": [{"type": "counter", "counter": "Bardic Inspiration", "amount": "1"}], "_v": 2}')
        avrae.message(
            '!a import {"name": "UseCounter Test2", "automation": [{"type": "counter", "counter": {"slot": 3}, "amount": "1"}], "_v": 2}')
        await dhttp.drain()

        avrae.message('!a "UseCounter Test"')
        await dhttp.drain()
        char = await active_character(avrae)
        if bi := char.get_consumable("Bardic Inspiration"):
            assert bi.value < bi.get_max()

        avrae.message('!a "UseCounter Test2"')
        await dhttp.drain()
        char = await active_character(avrae)
        assert char.spellbook.get_slots(3) == 0 or char.spellbook.get_slots(3) < char.spellbook.get_max_slots(3)

    async def test_deserialize(self):
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
        assert result.allow_overflow == True
        assert result.error_behaviour is None

        data = {
            'type': 'counter',
            'counter': 'Bardic Inspiration',
            'amount': '5'
        }
        result = automation.UseCounter.from_data(data)
        assert result
        assert result.allow_overflow == False
        assert result.error_behaviour == 'warn'

        data = {
            'type': 'counter',
            'counter': {'slot': 3},
            'amount': '1'
        }
        result = automation.UseCounter.from_data(data)
        assert result
        assert isinstance(result.counter, automation.utils.SpellSlotReference)
        assert result.counter.slot == 3

        # data = {
        #     'type': 'counter',
        #     'counter': {'feature': 'class', 'featureId': 1},
        #     'amount': '5'
        # }
        # assert automation.UseCounter.from_data(data)

    async def test_serialize(self):
        result = automation.UseCounter('Bardic Inspiration', '1').to_dict()
        assert json.dumps(result)  # result should be JSON-encodable

        result = automation.UseCounter(automation.utils.SpellSlotReference(1), '1').to_dict()
        assert json.dumps(result)

        # result = automation.UseCounter(automation.utils.FeatureReference('class', 1), '1').to_dict()
        # assert json.dumps(result)

    @pytest.mark.parametrize("counter", [
        # counters by name
        "counter", "other counter name",
        # spell slot
        automation.utils.SpellSlotReference(1), automation.utils.SpellSlotReference(9)
        # feature (todo)
    ])
    @pytest.mark.parametrize("amount", [
        # valid inputs
        "1", "proficiencyBonus", "{proficiencyBonus}", "dexterityMod + proficiencyBonus",
        "{dexterityMod + proficiencyBonus}",
        # inputs that should be NaN
        "foobar", "{}", "dexterymod", "RogueLevel", "1d4"
    ])
    async def test_build_str(self, counter, amount):
        usecounter = automation.UseCounter(counter, amount)
        result = usecounter.build_str(DEFAULT_CASTER, DEFAULT_EVALUATOR)
        log.info(f"UseCounter str: ({counter=!r}, {amount=!r}) -> {result}")
        assert result
