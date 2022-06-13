import discord

import cogs5e.models.character
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistance, Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP, StatBlock
from utils.constants import RESIST_TYPES
from utils.functions import combine_maybe_mods, get_guild_member, search_and_select
from .effect import Effect
from .errors import RequiresContext
from .types import BaseExplorer, ExplorerType
from .utils import create_explorer_id


class Explorer(BaseExplorer, StatBlock):
    DESERIALIZE_MAP = DESERIALIZE_MAP  # allow making class-specific deser maps
    type = ExplorerType.GENERIC

    def __init__(
        self,
        # init metadata
        ctx,
        exploration,
        id: str,
        name: str,
        controller_id: str,
        private: bool,
        notes: str = None,
        effects: list = None,
        group_id: str = None,
        # statblock info
        stats: BaseStats = None,
        levels: Levels = None,
        attacks: AttackList = None,
        skills: Skills = None,
        saves: Saves = None,
        resistances: Resistances = None,
        spellbook: Spellbook = None,
        ac: int = None,
        max_hp: int = None,
        hp: int = None,
        temp_hp: int = 0,
        creature_type: str = None,
        **_,
    ):
        super().__init__(
            name=name,
            stats=stats,
            levels=levels,
            attacks=attacks,
            skills=skills,
            saves=saves,
            resistances=resistances,
            spellbook=spellbook,
            ac=ac,
            max_hp=max_hp,
            hp=hp,
            temp_hp=temp_hp,
            creature_type=creature_type,
        )
        if effects is None:
            effects = []
        self.ctx = ctx
        self.exploration = exploration
        self.id = id

        self._controller = controller_id
        self._private = private
        self._notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    @classmethod
    def new(
        cls,
        name: str,
        controller_id: str,
        max_hp: int,
        ac: int,
        private: bool,
        resists: Resistances,
        ctx,
        exploration,
    ):
        skills = Skills.default()

        levels = Levels({"Monster": 0})
        id = create_explorer_id()
        return cls(
            ctx,
            exploration,
            id,
            name,
            controller_id,
            private,
            levels=levels,
            resistances=resists,
            skills=skills,
            max_hp=max_hp,
            ac=ac,
        )

    @classmethod
    def from_dict(cls, raw, ctx, exploration):
        for key, klass in cls.DESERIALIZE_MAP.items():
            if key in raw:
                raw[key] = klass.from_dict(raw[key])
        del raw["type"]
        effects = raw.pop("effects")
        inst = cls(ctx, exploration, **raw)
        inst._effects = [Effect.from_dict(e, exploration, inst) for e in effects]
        return inst

    def to_dict(self):
        d = super().to_dict()
        d.update(
            {
                "controller_id": self.controller,
                "private": self.is_private,
                "notes": self.notes,
                "effects": [e.to_dict() for e in self._effects],
                "group_id": self._group_id,
                "type": self.type.value,
                "id": self.id,
            }
        )
        return d

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = new_name

    @property
    def controller(self):
        return self._controller

    @controller.setter
    def controller(self, new_controller_id):
        self._controller = new_controller_id

    @property
    def max_hp(self):
        _maxhp = self._max_hp
        _maxhp = combine_maybe_mods(self.active_effects("maxhp"), base=_maxhp)
        return _maxhp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp
        if self._hp is None:
            self._hp = new_max_hp

    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, new_hp):
        self._hp = new_hp

    def hp_str(self, private=False):
        """Returns a string representation of the explorer's HP."""
        out = ""
        if not self.is_private or private:
            if self.max_hp is not None and self.hp is not None:
                out = f"<{self.hp}/{self.max_hp} HP>"
            elif self.hp is not None:
                out = f"<{self.hp} HP>"
            else:
                out = ""

            if self.temp_hp and self.temp_hp > 0:
                out += f" (+{self.temp_hp} temp)"
        elif self.max_hp is not None and self.max_hp > 0:
            ratio = self.hp / self.max_hp
            if ratio >= 1:
                out = "<Healthy>"
            elif 0.5 < ratio < 1:
                out = "<Injured>"
            elif 0.15 < ratio <= 0.5:
                out = "<Bloodied>"
            elif 0 < ratio <= 0.15:
                out = "<Critical>"
            elif ratio <= 0:
                out = "<Dead>"
        return out

    @property
    def ac(self):
        _ac = self._ac
        _ac = combine_maybe_mods(self.active_effects("ac"), base=_ac)
        return _ac

    @ac.setter
    def ac(self, new_ac):
        self._ac = new_ac

    @property
    def is_private(self):
        return self._private

    @is_private.setter
    def is_private(self, new_privacy):
        self._private = new_privacy

    @property
    def resistances(self):
        out = self._resistances.copy()
        out.update(Resistances.from_dict({k: self.active_effects(k) for k in RESIST_TYPES}), overwrite=False)
        return out

    def set_resist(self, damage_type: str, resist_type: str):
        if resist_type not in RESIST_TYPES:
            raise ValueError("Resistance type is invalid")

        resistance = Resistance.from_str(damage_type)

        for rt in RESIST_TYPES:
            for resist in reversed(self._resistances[rt]):
                # remove any existing identical resistances, or any filtered variant of a given non-complex resistance
                if resist == resistance or (not resistance.is_complex and resist.dtype == resistance.dtype):
                    self._resistances[rt].remove(resist)

        if resist_type != "neutral" or resistance.is_complex:
            self._resistances[resist_type].append(resistance)

    @property
    def attacks(self):
        if "attacks" not in self._cache:
            # attacks granted by effects are cached so that the same object is referenced in initTracker (#950)
            self._cache["attacks"] = self._attacks + AttackList.from_dict(self.active_effects("attack"))
        return self._cache["attacks"]

    @property
    def notes(self):
        return self._notes

    @notes.setter
    def notes(self, new_notes):
        self._notes = new_notes

    @property
    def group(self):
        return self._group_id

    @group.setter
    def group(self, value):
        self._group_id = value

    @property
    def _effect_id_map(self):
        return {e.id: e for e in self._effects}

    def set_group(self, group_name):
        self.exploration.remove_explorer(self, ignore_remove_hook=True)
        if isinstance(group_name, str) and group_name.lower() == "none":
            group_name = None
        if group_name is None:
            self.exploration.add_explorer(self)
            return None
        else:
            c_group = self.exploration.get_group(group_name)
            c_group.add_explorer(self)
            return c_group

    def get_group(self):
        return self.exploration.get_group(self._group_id) if self._group_id else None

    # effects
    def add_effect(self, effect):
        # handle name conflict
        if self.get_effect(effect.name, True):
            self.get_effect(effect.name).remove()

        # handle concentration conflict
        conc_conflict = []
        if effect.concentration:
            conc_conflict = self.remove_all_effects(lambda e: e.concentration)

        # invalidate cache
        self._invalidate_effect_cache()

        self._effects.append(effect)
        return {"conc_conflict": conc_conflict}

    def get_effects(self):
        return self._effects

    def effect_by_id(self, effect_id):
        return self._effect_id_map.get(effect_id)

    def get_effect(self, name, strict=True):
        if strict:
            return next((c for c in self.get_effects() if c.name == name), None)
        else:
            return next((c for c in self.get_effects() if name.lower() in c.name.lower()), None)

    async def select_effect(self, name):
        """
        Opens a prompt for a user to select the effect they were searching for.

        :rtype: Effect
        :param name: The name of the effect to search for.
        :return: The selected Effect, or None if the search failed.
        """
        return await search_and_select(self.ctx, self.get_effects(), name, lambda e: e.name)

    def remove_effect(self, effect):
        try:
            self._effects.remove(effect)
        except ValueError:
            # this should be safe
            # the only case where this occurs is if a parent removes an effect while it's trying to remove itself
            pass
        # invalidate cache
        self._invalidate_effect_cache()

    def remove_all_effects(self, _filter=None):
        if _filter is None:
            to_remove = self._effects.copy()
        else:
            to_remove = list(filter(_filter, self._effects))
        for e in to_remove:
            e.remove()
        return to_remove

    def active_effects(self, key=None):
        if "parsed_effects" not in self._cache:
            parsed_effects = {}
            for effect in self.get_effects():
                for k, v in effect.effect.items():
                    if k not in parsed_effects:
                        parsed_effects[k] = []
                    if not isinstance(v, list):
                        parsed_effects[k].append(v)
                    else:
                        parsed_effects[k].extend(v)
            self._cache["parsed_effects"] = parsed_effects
        if key:
            return self._cache["parsed_effects"].get(key, [])
        return self._cache["parsed_effects"]

    def _invalidate_effect_cache(self):
        if "parsed_effects" in self._cache:
            del self._cache["parsed_effects"]
        if "attacks" in self._cache:
            del self._cache["attacks"]

    def is_concentrating(self):
        return any(e.concentration for e in self.get_effects())

    # controller stuff
    def controller_mention(self):
        return f"<@{self.controller}>"

    async def message_controller(self, ctx, *args, **kwargs):
        """Sends a message to the explorer's controller."""
        if ctx.guild is None:
            raise RequiresContext("message_controller requires a guild context.")
        if int(self.controller) == ctx.bot.user.id:  # don't message self
            return
        member = await get_guild_member(ctx.guild, int(self.controller))
        if member is None:  # member is not in the guild, oh well
            return
        try:
            await member.send(*args, **kwargs)
        except discord.Forbidden:  # member is not accepting PMs from us, oh well
            pass

    # hooks
    def on_round(self, num_rounds=1):
        """
        A method called at the start of the round
        :param num_rounds: The number of rounds that just passed.
        :return: None
        """
        message_list = []
        s_name = self.name + "'s "
        for e in self.get_effects().copy():
            message_list.append(s_name + e.on_round(num_rounds))
        for m in message_list:
            if m == s_name:
                message_list.remove(m)
        final_str = "\n".join(message_list)
        return final_str

    def on_round_end(self, num_rounds=1):
        """A method called at the end of the round"""
        for e in self.get_effects().copy():
            e.on_round_end(num_rounds)

    def on_remove(self):
        """
        Called when the explorer is removed from exploration, either through !i remove or the exploration ending.
        """
        pass

    # stringification
    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of an explorer's status.
        :return: A string describing the explorer.
        """
        if not no_notes:
            return f"{self.name}{self._get_effects_and_notes()}"
        else:
            return f"{self.name}"

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of an explorer.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the explorer.
        """
        name = self.name
        hp_ac = self._get_hp_and_ac(private)
        resists = self._get_resist_string(private)
        notes = "\n# " + self.notes if self.notes else ""
        effects = self._get_long_effects()
        return f"{name} {hp_ac} {resists}{notes}\n{effects}".strip()

    def _get_long_effects(self):
        return "\n".join(f"* {str(e)}" for e in self.get_effects())

    def _get_effects_and_notes(self):
        out = []
        if (self._ac is not None or self.ac) and not self.is_private:
            out.append(f"AC {self.ac}")
        for e in self.get_effects():
            out.append(e.get_short_str())
        if self.notes:
            out.append(self.notes)
        if out:
            return f"({', '.join(out)})"
        return ""

    def _get_hp_and_ac(self, private: bool = False):
        out = [self.hp_str(private)]
        if (self._ac is not None or self.ac) and (not self.is_private or private):
            out.append(f"(AC {self.ac})")
        return " ".join(out)

    def _get_resist_string(self, private: bool = False):
        resist_str = ""
        if not self.is_private or private:
            if len(self.resistances.resist) > 0:
                resist_str += "\n> Resistances: " + ", ".join([str(r) for r in self.resistances.resist])
            if len(self.resistances.immune) > 0:
                resist_str += "\n> Immunities: " + ", ".join([str(r) for r in self.resistances.immune])
            if len(self.resistances.vuln) > 0:
                resist_str += "\n> Vulnerabilities: " + ", ".join([str(r) for r in self.resistances.vuln])
            if len(self.resistances.neutral) > 0:
                resist_str += "\n> Ignored: " + ", ".join([str(r) for r in self.resistances.neutral])
        return resist_str

    def __str__(self):
        return f"{self.name}: {self.hp_str()}".strip()

    def __hash__(self):
        return hash(f"{self.exploration.channel}.{self.name}")


class PlayerExplorer(Explorer):
    type = ExplorerType.PLAYER

    def __init__(
        self,
        # init metadata
        ctx,
        exploration,
        id: str,
        name: str,
        controller_id: str,
        private: bool = True,
        notes: str = None,
        effects: list = None,
        group_id: str = None,
        # statblock info
        attacks: AttackList = None,
        resistances: Resistances = None,
        ac: int = None,
        max_hp: int = None,
        # character specific
        character_id=None,
        character_owner=None,
        **_,
    ):
        # note that the player explorer doesn't initialize the statblock
        # because we want the explorer statblock attrs to reference the character attrs
        super().__init__(
            ctx,
            exploration,
            id,
            name,
            controller_id,
            private,
            notes,
            effects,
            group_id,
            attacks=attacks,
            resistances=resistances,
            ac=ac,
            max_hp=max_hp,
        )
        self.character_id = character_id
        self.character_owner = character_owner

        self._character = None  # cache

    @classmethod
    async def from_character(cls, character, ctx, exploration, controller_id, private=True):
        id = create_explorer_id()
        inst = cls(
            ctx,
            exploration,
            id,
            character.name,
            controller_id,
            private,
            # statblock copies
            resistances=character.resistances.copy(),
            # character specific
            character_id=character.upstream,
            character_owner=character.owner,
        )
        inst._character = character
        return inst

    # ==== serialization ====
    @classmethod
    async def from_dict(cls, raw, ctx, exploration):
        inst = super().from_dict(raw, ctx, exploration)
        inst.character_id = raw["character_id"]
        inst.character_owner = raw["character_owner"]
        inst._character = await cogs5e.models.character.Character.from_bot_and_ids(
            ctx.bot, inst.character_owner, inst.character_id
        )
        return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx, exploration):
        inst = super().from_dict(raw, ctx, exploration)
        inst.character_id = raw["character_id"]
        inst.character_owner = raw["character_owner"]
        inst._character = cogs5e.models.character.Character.from_bot_and_ids_sync(
            ctx.bot, inst.character_owner, inst.character_id
        )
        return inst

    def to_dict(self):
        ignored_attributes = ("stats", "levels", "skills", "saves", "spellbook", "hp", "temp_hp")
        raw = super().to_dict()
        for attr in ignored_attributes:
            del raw[attr]
        raw.update({"character_id": self.character_id, "character_owner": self.character_owner})
        return raw

    # ==== helpers ====
    async def update_character_ref(self, ctx, inst=None):
        """
        Updates the character reference in self._character to ensure that it references the cached Character instance
        if one is cached (since Exploration cache TTL > Character cache TTL), preventing instance divergence.

        If ``inst`` is passed, sets the character to reference the given instance, otherwise retrieves it via the normal
        Character init flow (from cache or db). ``inst`` should be a Character instance with the same character ID and
        owner as ``self._character``.
        """
        if inst is not None:
            self._character = inst
            return

        # retrieve from character constructor
        self._character = await cogs5e.models.character.Character.from_bot_and_ids(
            ctx.bot, self.character_owner, self.character_id
        )

    # ==== members ====
    @property
    def character(self):
        return self._character

    @property
    def stats(self):
        return self.character.stats

    @property
    def levels(self):
        return self.character.levels

    @property
    def skills(self):
        return self.character.skills

    @property
    def saves(self):
        return self.character.saves

    @property
    def ac(self):
        _ac = self._ac or self.character.ac
        _ac = combine_maybe_mods(self.active_effects("ac"), base=_ac)
        return _ac

    @ac.setter
    def ac(self, new_ac):
        """
        :param int|None new_ac: The new AC
        """
        self._ac = new_ac

    @property
    def spellbook(self):
        return self.character.spellbook

    @property
    def max_hp(self):
        _maxhp = self._max_hp or self.character.max_hp
        _maxhp = combine_maybe_mods(self.active_effects("maxhp"), base=_maxhp)
        return _maxhp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp

    @property
    def hp(self):
        return self.character.hp

    @hp.setter
    def hp(self, new_hp):
        self.character.hp = new_hp

    def set_hp(self, new_hp):
        return self.character.set_hp(new_hp)

    def reset_hp(self):
        return self.character.reset_hp()

    @property
    def temp_hp(self):
        return self.character.temp_hp

    @temp_hp.setter
    def temp_hp(self, new_hp):
        self.character.temp_hp = new_hp

    @property
    def attacks(self):
        return super().attacks + self.character.attacks

    def get_scope_locals(self):
        return {**self.character.get_scope_locals(), **super().get_scope_locals()}

    def get_color(self):
        return self.character.get_color()
