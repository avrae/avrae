import pytest

from aliasing.api.character import AliasCharacter
from tests.utils import active_character, end_init, start_init
from cogs5e.models.errors import ConsumableException, CounterOutOfBounds


pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("character")
class TestAliasCharacterCounter:
    async def test_alias_character_counters(self, avrae, dhttp):
        character = await active_character(avrae)
        alias_char = AliasCharacter(character)

        cc = alias_char.create_cc_nx(name="Test")

        # Make sure our basic properties work
        assert cc.value == 0
        assert cc.name == "Test"
        assert cc.display_type is None
        assert cc.desc is None

        # Modification
        assert cc.mod(3) == 3
        alias_char.mod_cc("Test", -3)
        assert alias_char.get_cc("Test") == 0

        # Deletion
        alias_char.delete_cc("Test")

        with pytest.raises(ConsumableException) as e:
            alias_char.delete_cc("Test")

    async def test_alias_character_counter_bounds(self, avrae, dhttp):
        character = await active_character(avrae)
        alias_char = AliasCharacter(character)

        alias_char.create_cc_nx(name="Test", maxVal="10", minVal="0")

        # Lower Bound
        with pytest.raises(CounterOutOfBounds):
            alias_char.mod_cc("Test", -1, strict=True)

        alias_char.mod_cc("Test", -1)
        assert alias_char.get_cc("Test") == 0

        # Upper Bound
        with pytest.raises(CounterOutOfBounds):
            alias_char.mod_cc("Test", +11, strict=True)

        alias_char.mod_cc("Test", +11)
        assert alias_char.get_cc("Test") == 10

        alias_char.delete_cc("Test")
