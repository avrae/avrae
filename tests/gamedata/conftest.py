import copy
import json
import os

import pytest

from tests.discord_mock_data import DEFAULT_USER_ID, MESSAGE_ID, TEST_CHANNEL_ID
from tests.utils import ContextBotProxy

SIMULATION_BASE_PATH = os.getenv("TEST_SIMULATION_BASE_PATH")


# ==== data ====
def load_file(path):
    if SIMULATION_BASE_PATH is not None:
        basepath = SIMULATION_BASE_PATH
    else:
        basepath = os.path.join(os.path.dirname(__file__), "../static/compendium")

    relpath = os.path.join(basepath, path)
    with open(relpath) as f:
        entities = json.load(f)
    return entities


# ---- spells ----
@pytest.fixture(scope="session")
def spells():
    """Fixture providing all spells in spells.json as a list of dicts."""
    yield load_file("spells.json")


@pytest.fixture(params=load_file("spells.json"), ids=lambda s: s["name"])
def spell(request):
    """Parameterized fixture providing each spell in spells individually."""
    yield copy.deepcopy(request.param)


# ---- monsters ----
@pytest.fixture(scope="session")
def monsters():
    """Fixture providing all monsters in monsters.json as a list of dicts."""
    yield load_file("monsters.json")


@pytest.fixture(params=load_file("monsters.json"), ids=lambda s: s["name"])
def monster(request):
    """Parameterized fixture providing each monster in monsters individually."""
    yield copy.deepcopy(request.param)


def generate_monster_actions(monsters):
    for monster in monsters:
        for attack in monster["attacks"]:
            yield attack, monster


@pytest.fixture(
    params=list(generate_monster_actions(load_file("monsters.json"))),
    ids=lambda a: f"{a[1]['name']}: {a[0]['name']}",
)
def monster_attack(request):
    """Parameterized fixture providing each attack from each monster individually in a (attack, monster_dict) pair."""
    yield copy.deepcopy(request.param[0]), copy.deepcopy(request.param[1])


# ---- actions ----
@pytest.fixture(scope="session")
def actions():
    """Fixture providing all actions in actions.json as a list of dicts."""
    yield load_file("actions.json")


@pytest.fixture(params=load_file("actions.json"), ids=lambda s: s["name"])
def action(request):
    """Parameterized fixture providing each action in actions individually."""
    yield copy.deepcopy(request.param)


# ==== simulation ====
@pytest.fixture(scope="module")
def bob():
    """Bob is a very simple spellcaster. He represents the minimal amount of data passed to a spellcast."""
    from cogs5e.models.sheet.statblock import StatBlock
    from cogs5e.models.sheet.spellcasting import Spellbook

    return StatBlock("Bob", spellbook=Spellbook(dc=10, sab=2, spell_mod=0))


@pytest.fixture(scope="module")
def ara():
    from cogs5e.models.character import Character

    filename = os.path.join(os.path.dirname(__file__), f"../static/char-ara.json")
    with open(filename) as f:
        char = Character.from_dict(json.load(f))
    return char


# ==== automation ====
@pytest.fixture(autouse=True, scope="session")
def monkey_patch_effect_run():
    """
    Monkey patches Effect.run() to fail tests if an effect raises a warning instead of just outputting the warning.
    This has to be the first monkey-patch run in order to monkeypatch the super call.
    """
    from cogs5e.models.automation.effects import Effect

    def run_children(_, child, autoctx):
        child_results = []
        for effect in child:
            try:
                result = effect.run(autoctx)
                if result is not None:
                    child_results.append(result)
            except Exception as e:
                pytest.fail(f"Automation execution raised warning: {e}")
        return child_results

    real_run_children = Effect.run_children
    Effect.run_children = run_children
    yield
    Effect.run_children = real_run_children


@pytest.fixture(autouse=True, scope="module")
def monkey_patch_entitlements():
    """Monkey patches the entitlement handler so that the test framework has access to all entities."""
    from cogs5e.models.automation.effects import CastSpell

    # CastSpell.preflight: spell check
    async def preflight(*_, **__):
        return

    real_preflight = CastSpell.preflight
    CastSpell.preflight = preflight
    yield
    CastSpell.preflight = real_preflight


# --- effects ---
@pytest.fixture(autouse=True, scope="module")
def monkey_patch_cc_discovery():
    """Monkey patches the ability reference counter discovery method to always return a valid, ephemeral cc."""
    import cogs5e.models.automation.effects.usecounter as usecounter
    from cogs5e.models.sheet.player import CustomCounter

    # usecounter.abilityreference_counter_discovery
    def abilityreference_counter_discovery(ref, char, *_, **__):
        if ref.entity is None:
            raise ValueError("Invalid entity in AbilityReference")
        return CustomCounter(char, "Test CC", 50)

    real_discovery = usecounter.abilityreference_counter_discovery
    usecounter.abilityreference_counter_discovery = abilityreference_counter_discovery
    yield
    usecounter.abilityreference_counter_discovery = real_discovery


@pytest.fixture(autouse=True, scope="module")
def monkey_patch_use_spell_slot():
    """Monkey patches the spell slot user to always return a successful use (as if -i was passed)."""
    from cogs5e.models.automation.effects import UseCounter

    # UseCounter.use_spell_slot
    real_use_spell_slot = UseCounter.use_spell_slot

    def use_spell_slot(self, autoctx, amount, ignore_resources=False):
        return real_use_spell_slot(self, autoctx, amount, ignore_resources=True)

    UseCounter.use_spell_slot = use_spell_slot
    yield
    UseCounter.use_spell_slot = real_use_spell_slot


# ===== mock combat =====
@pytest.fixture()
def mock_combat(avrae):
    """
    Sets up a combat in the channel's context, to be used in tests. Cleans up after itself.
    """
    from cogs5e.initiative.combat import Combat, CombatOptions

    # noinspection PyTypeChecker
    new_combat = Combat.new(
        channel_id=str(TEST_CHANNEL_ID),
        message_id=int(MESSAGE_ID),
        dm_id=int(DEFAULT_USER_ID),
        options=CombatOptions(),
        ctx=ContextBotProxy(avrae),
    )
    yield new_combat
