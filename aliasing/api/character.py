import cogs5e.models.sheet.player as player_api
from aliasing import helpers
from aliasing.api.statblock import AliasStatBlock
from cogs5e.models.errors import ConsumableException


class AliasCharacter(AliasStatBlock):
    def __init__(self, character, interpreter=None):
        """
        :type character: cogs5e.models.character.Character
        :type interpreter: draconic.DraconicInterpreter
        """
        super().__init__(character)
        self._character = character
        self._interpreter = interpreter

    # helpers
    def _get_consumable(self, name):
        consumable = next((con for con in self._character.consumables if con.name == name), None)
        if consumable is None:
            raise ConsumableException(f"There is no counter named {name}.")
        return consumable

    # methods
    # --- ccs ---
    def get_cc(self, name):
        return self._get_consumable(name).value

    def get_cc_max(self, name):
        return self._get_consumable(name).get_max()

    def get_cc_min(self, name):
        return self._get_consumable(name).get_min()

    def set_cc(self, name, value: int, strict=False):
        self._get_consumable(name).set(int(value), strict)

    def mod_cc(self, name, val: int, strict=False):
        return self.set_cc(name, self.get_cc(name) + val, strict)

    def delete_cc(self, name):
        to_delete = self._get_consumable(name)
        self._character.consumables.remove(to_delete)

    def create_cc_nx(self, name: str, minVal: str = None, maxVal: str = None, reset: str = None,
                     dispType: str = None):
        if not self.cc_exists(name):
            new_consumable = player_api.CustomCounter.new(self._character, name, minVal, maxVal, reset, dispType)
            self._character.consumables.append(new_consumable)

    def create_cc(self, name: str, *args, **kwargs):
        if self.cc_exists(name):
            self.delete_cc(name)
        self.create_cc_nx(name, *args, **kwargs)

    def cc_exists(self, name):
        return name in [con.name for con in self._character.consumables]

    def cc_str(self, name):
        return str(self._get_consumable(name))

    # --- cvars ---
    def set_cvar(self, name, val: str):
        helpers.set_cvar(self._character, name, val)
        # noinspection PyProtectedMember
        self._interpreter._names[name] = str(val)

    def set_cvar_nx(self, name, val: str):
        if name not in self._character.cvars:
            self.set_cvar(name, val)

    def delete_cvar(self, name):
        if name in self._character.cvars:
            del self._character.cvars[name]

    # --- private helpers ----
    async def func_commit(self, ctx):
        await self._character.commit(ctx)
