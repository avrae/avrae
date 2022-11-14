import pytest

from aliasing.api.character import AliasCharacter
from tests.utils import active_character, end_init, start_init

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
