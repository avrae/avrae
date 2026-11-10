import inspect
import json
import random
from pathlib import Path
from unittest.mock import MagicMock

import d20
import pytest

from aliasing.api.character import AliasCharacter
from aliasing.api.combat import SimpleCombat, SimpleCombatant
from aliasing.api.functions import SimpleRollResult
from aliasing.evaluators import DEFAULT_BUILTINS, ScriptingEvaluator
from cogs5e.initiative import Combat, CombatOptions, PlayerCombatant
from cogs5e.initiative.effects import InitiativeEffect
from cogs5e.initiative.effects.passive import InitPassiveEffect
from cogs5e.models.character import Character
from cogs5e.models.errors import InvalidArgument, InvalidSaveType
from tests.utils import ContextBotProxy


@pytest.fixture(params=[("save", "dex"), ("check", "perception")], ids=["save", "check"])
def roll_case(request):
    return request.param


@pytest.fixture
def roll_character():
    path = Path(__file__).parents[2] / "static" / "char-ara.json"
    character = Character.from_dict(json.loads(path.read_text()))
    character.options.reroll = None
    character.options.talent = False
    character.skills.perception.adv = None
    character.skills.perception.prof = 0
    character.saves.get("dex").adv = None
    return character


@pytest.fixture
def evaluator(avrae, roll_character):
    return ScriptingEvaluator(ContextBotProxy(avrae), builtins=DEFAULT_BUILTINS).with_character(roll_character)


@pytest.fixture
def in_combat(evaluator, roll_character):
    ctx = evaluator.ctx
    combat = Combat.new(str(ctx.channel.id), 1, ctx.author.id, CombatOptions(), ctx)
    player = PlayerCombatant.from_character(roll_character, ctx, combat, ctx.author.id, 10, False)
    combat.add_combatant(player)
    player.add_effect(
        InitiativeEffect.new(
            combat,
            player,
            "Roll Test",
            passive_effects=InitPassiveEffect(
                save_bonus="1d1 [effect]", save_adv={"dex"}, check_bonus="1d1 [effect]", check_adv={"wisdom"}
            ),
        )
    )
    evaluator._cache["combat"] = SimpleCombat(combat, None, interpreter=evaluator)
    return player


@pytest.fixture(params=["character", "combatant"])
def roll_api(request, evaluator, in_combat):
    if request.param == "character":
        return evaluator.character()
    return SimpleCombatant(in_combat, evaluator, hidestats=False)


def _modifier(character, method, key):
    skill = character.saves.get(key) if method == "save" else character.skills.get(key)
    return skill.value


def test_signatures_match_combatant(roll_case):
    method, _ = roll_case
    signature = inspect.signature(getattr(AliasCharacter, method))
    assert signature == inspect.signature(getattr(SimpleCombatant, method))
    assert "args" in signature.parameters and "bonus" not in signature.parameters


@pytest.mark.parametrize(
    "bonus, expected, comment",
    [
        (None, 0, None),
        ("", 0, None),
        ("2", 2, None),
        ("1d1 [bonus]", 1, None),
        ("-1d1 [penalty]", -1, None),
        ("2*(1+1)", 4, None),
        ("1d1 [bonus] ^[comment]", 1, "^[comment]"),
        ("1d1 bonus + 20", 1, "bonus + 20"),
    ],
)
def test_roll_without_interpreter(roll_character, roll_case, bonus, expected, comment):
    method, key = roll_case
    result = getattr(AliasCharacter(roll_character), method)(
        key, args=f'-b "{bonus}"' if bonus else bonus, include_ieffects=True
    )

    assert isinstance(result, SimpleRollResult)
    assert isinstance(result.result, d20.RollResult)
    assert result.raw is result.result.expr
    assert result.result.comment == comment
    assert result.full == str(result) == str(result.result) == f"{result.dice} = `{result.total}`"
    assert result.total == d20.utils.leftmost(result.raw).total + _modifier(roll_character, method, key) + expected
    if bonus and "[bonus]" in bonus:
        assert "[bonus]" in result.dice


def test_effect_flag_without_combat(evaluator, roll_character, monkeypatch, roll_case):
    method, key = roll_case
    roll_character.options.reroll = 1
    roll_character.options.talent = True
    roll_character.skills.perception.prof = 1
    lookup = MagicMock(return_value=None)
    monkeypatch.setattr(SimpleCombat, "from_ctx", lookup)

    args = '-b "1d1 [bonus] ^[comment]"'
    result = evaluator.eval(
        f'character().{method}("{key}", include_ieffects=True, include_csettings=True, args={args!r})'
    )

    assert "[bonus]" in result.full
    assert "ro1" in result.full
    assert ("mi10" in result.full) == (method == "check")
    assert result.result.comment == "^[comment]"
    assert evaluator._cache["combat"] is None
    lookup.assert_called_once()


def test_disabled_effect_flag_does_not_load_combat(evaluator, monkeypatch, roll_case):
    method, key = roll_case
    lookup = MagicMock(side_effect=AssertionError("Combat should not be loaded"))
    monkeypatch.setattr(evaluator, "combat", lookup)

    getattr(evaluator.character(), method)(key, args="-b 1d1")

    lookup.assert_not_called()


def test_effects_are_opt_in(evaluator, roll_character, in_combat, roll_case):
    method, key = roll_case
    roll = getattr(evaluator.character(), method)

    excluded = roll(key, args='-b "1d1 [custom]"')
    included = roll(key, include_ieffects=True, args='-b "1d1 [custom]"')

    assert "[effect]" not in excluded.full and "kh1" not in excluded.full
    assert "[effect]" in included.full and "kh1" in included.full
    assert "[custom]" in included.full
    assert included.total == d20.utils.leftmost(included.raw).total + _modifier(roll_character, method, key) + 2


def test_explicit_advantage_overrides_effects(evaluator, in_combat, roll_case):
    method, key = roll_case
    result = getattr(evaluator.character(), method)(key, adv=False, include_ieffects=True)
    assert "kl1" in result.full


@pytest.mark.parametrize("mismatch", ["character_id", "character_owner"])
def test_other_characters_effects_are_ignored(evaluator, in_combat, roll_case, mismatch):
    method, key = roll_case
    setattr(in_combat, mismatch, "another-character")

    result = getattr(evaluator.character(), method)(key, include_ieffects=True)

    assert "[effect]" not in result.full and "kh1" not in result.full


def test_character_settings_are_opt_in(roll_character, roll_case):
    method, key = roll_case
    roll_character.options.reroll = 1
    roll_character.options.talent = True
    roll_character.skills.perception.prof = 1
    roll = getattr(AliasCharacter(roll_character), method)

    excluded = roll(key)
    included = roll(key, include_csettings=True)

    assert "ro1" not in excluded.full and "mi10" not in excluded.full
    assert "ro1" in included.full
    assert ("mi10" in included.full) == (method == "check")


@pytest.mark.parametrize("proficiency", [0, 0.5, 1, 2])
def test_reliable_talent_requires_proficiency(roll_character, proficiency):
    roll_character.options.talent = True
    roll_character.skills.perception.prof = proficiency
    result = AliasCharacter(roll_character).check("perception", include_csettings=True)
    assert ("mi10" in result.full) == (proficiency >= 1)


@pytest.mark.parametrize("adv", [None, True, False])
@pytest.mark.parametrize("include_csettings", [False, True])
@pytest.mark.parametrize("args", [None, '-b "1d1 [bonus] ^[comment]"', "dis -b 1d1 -mc 12 -ro 2"])
def test_matches_combatant_in_combat(evaluator, roll_character, in_combat, roll_case, adv, include_csettings, args):
    method, key = roll_case
    roll_character.options.reroll = 1
    roll_character.options.talent = True
    roll_character.skills.perception.prof = 1
    character_roll = getattr(evaluator.character(), method)
    combatant_roll = getattr(SimpleCombatant(in_combat, evaluator, hidestats=False), method)

    random.seed(123)
    actual = character_roll(key, adv, True, include_csettings, args)
    random.seed(123)
    expected = combatant_roll(key, adv, True, include_csettings, args)

    assert actual.total == expected.total
    assert actual.full == expected.full
    assert actual.result.comment == expected.result.comment


def test_uses_current_character_stats(evaluator, roll_character, in_combat, roll_case):
    method, key = roll_case
    stale_character = Character.from_dict(roll_character.to_dict())
    stale_character.saves.get("dex").value += 100
    stale_character.skills.perception.value += 100
    in_combat._character = stale_character

    result = getattr(evaluator.character(), method)(key, include_ieffects=True)

    assert in_combat.character is roll_character
    assert result.total == d20.utils.leftmost(result.raw).total + _modifier(roll_character, method, key) + 1


@pytest.mark.parametrize("method, key, error", [("save", "xyz", InvalidSaveType), ("check", "xyz", ValueError)])
def test_invalid_stat_raises(roll_character, method, key, error):
    with pytest.raises(error):
        getattr(AliasCharacter(roll_character), method)(key)


def test_invalid_bonus_raises(roll_character, roll_case):
    method, key = roll_case
    with pytest.raises(d20.RollSyntaxError):
        getattr(AliasCharacter(roll_character), method)(key, args="-b (1d4")


def test_combined_roll_arguments(roll_api, roll_character, in_combat, roll_case):
    method, key = roll_case
    in_combat.remove_all_effects()
    result = getattr(roll_api, method)(
        key,
        args='adv -ro 1 -mc 20 -b "1d1 [bless] ^[first]" -b "-1d1 [penalty] second" -b "2*(1+1)"',
    )

    assert "2d20ro1kh1mi20" in result.full
    assert d20.utils.leftmost(result.raw).total == 20
    assert result.total == 20 + _modifier(roll_character, method, key) + 4
    assert "[bless]" in result.full and "[penalty]" in result.full
    assert result.result.comment == "^[first] second"
    assert result.full == str(result) == str(result.result)


@pytest.mark.parametrize(
    "adv, args, expected",
    [
        (None, "adv", "kh1"),
        (None, "dis", "kl1"),
        (None, "adv1", "kh1"),
        (None, "dis1", "kl1"),
        (False, "adv", "kl1"),
        (True, "dis", "kh1"),
        (None, "adv dis", None),
    ],
)
def test_argument_advantage_precedence(roll_api, roll_case, adv, args, expected):
    method, key = roll_case
    result = getattr(roll_api, method)(key, adv=adv, include_ieffects=True, args=args)
    if expected is None:
        assert "kh1" not in result.full and "kl1" not in result.full
    else:
        assert expected in result.full


@pytest.mark.parametrize(
    "args, rolls, expected",
    [
        ("-mc 10", [1], 10),
        ("-mc 0", [1], 2),
        ("-mc 10 -mc 12", [1], 12),
        ("-ro 1", [0, 7], 8),
        ("-ro 1", [0, 0], 1),
        ("-ro 1", [3], 4),
        ("-ro 0", [0], 1),
        ("-ro 1 -ro 2", [1, 7], 8),
    ],
)
def test_minimum_and_reroll_arguments(
    roll_api, roll_character, in_combat, roll_case, monkeypatch, args, rolls, expected
):
    method, key = roll_case
    in_combat.remove_all_effects()
    randrange = MagicMock(side_effect=rolls)
    monkeypatch.setattr("d20.expression.random.randrange", randrange)

    result = getattr(roll_api, method)(key, args=args)

    assert result.total == expected + _modifier(roll_character, method, key)
    assert randrange.call_count == len(rolls)


def test_ephemeral_bonus_argument(roll_api, roll_character, in_combat, roll_case):
    method, key = roll_case
    in_combat.remove_all_effects()

    result = getattr(roll_api, method)(key, args='-b 2 -b1 "-1d1 [penalty]"')

    assert result.total == d20.utils.leftmost(result.raw).total + _modifier(roll_character, method, key) + 1
    assert "[penalty]" in result.full


@pytest.mark.parametrize("args", ["-rr 99999", "-dc 999", "eadv", "-unknown value"])
def test_unsupported_arguments_are_ignored(roll_api, roll_case, monkeypatch, args):
    method, key = roll_case
    roll = getattr(roll_api, method)
    random.seed(123)
    expected = roll(key, args="-b 1d1")
    roll_mock = MagicMock(wraps=d20.roll)
    monkeypatch.setattr("aliasing.api._rolls.roll", roll_mock)

    random.seed(123)
    result = roll(key, args=f"-b 1d1 {args}")

    assert isinstance(result, SimpleRollResult)
    assert result.full == expected.full
    assert result.result.comment == expected.result.comment
    roll_mock.assert_called_once()


@pytest.mark.parametrize("args, reroll, minimum", [("-ro 0 -mc 0", None, None), ("-ro 2 -mc 12", "ro2", "mi12")])
def test_arguments_override_character_settings(roll_api, roll_character, roll_case, args, reroll, minimum):
    method, key = roll_case
    roll_character.options.reroll = 1
    roll_character.options.talent = True
    roll_character.skills.perception.prof = 1

    result = getattr(roll_api, method)(key, include_csettings=True, args=args)

    assert "ro1" not in result.full and "mi10" not in result.full
    assert ("ro2" in result.full) == (reroll is not None)
    assert ("mi12" in result.full) == (minimum is not None)


def test_guidance_only_applies_to_checks(roll_api, roll_character, in_combat, roll_case):
    method, key = roll_case
    in_combat.remove_all_effects()
    result = getattr(roll_api, method)(key, args="guidance -b 1d1")

    assert ("[guidance]" in result.full) == (method == "check")
    bonus = result.total - d20.utils.leftmost(result.raw).total - _modifier(roll_character, method, key)
    if method == "check":
        assert 2 <= bonus <= 5
    else:
        assert bonus == 1


@pytest.mark.parametrize(
    "args, error",
    [
        ('-b "not dice"', d20.RollSyntaxError),
        ("-b (1d4", d20.RollSyntaxError),
        ("-b \"__import__('os')\"", d20.RollSyntaxError),
        ("-mc invalid", InvalidArgument),
        ("-ro invalid", InvalidArgument),
        ("-b 1001d1", d20.TooManyRolls),
    ],
)
def test_invalid_arguments_and_roll_limits(roll_api, roll_case, args, error):
    method, key = roll_case
    with pytest.raises(error):
        getattr(roll_api, method)(key, args=args)
