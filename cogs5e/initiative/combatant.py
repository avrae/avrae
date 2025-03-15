import itertools
from typing import Callable, List, Optional, TYPE_CHECKING, TypeVar

import disnake

import cogs5e.models.character
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistance, Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP, StatBlock
from gamedata.monster import MonsterCastableSpellbook
from utils.constants import RESIST_TYPES
from utils.functions import get_guild_member, search_and_select
from .effects import InitiativeEffect
from .errors import RequiresContext
from .types import BaseCombatant, CombatantType
from .utils import create_combatant_id

if TYPE_CHECKING:
    from .group import CombatantGroup

_IntermediateT = TypeVar("_IntermediateT")
T = TypeVar("T")


class Combatant(BaseCombatant, StatBlock):
    DESERIALIZE_MAP = DESERIALIZE_MAP  # allow making class-specific deser maps
    type = CombatantType.GENERIC

    def __init__(
        self,
        # init metadata
        ctx,
        combat,
        id: str,
        name: str,
        controller_id: int,
        private: bool,
        init: int,
        index: int = None,
        notes: str = None,
        effects: List[InitiativeEffect] = None,
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
        self.combat = combat
        self.id = id

        self.controller_id = int(controller_id)
        self.init = init
        self.is_private = private
        self._index = index  # combat write only; position in combat
        self.notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    @classmethod
    def from_dict(cls, raw, ctx, combat):
        for key, klass in cls.DESERIALIZE_MAP.items():
            if key in raw:
                raw[key] = klass.from_dict(raw[key])
        del raw["type"]
        effects = raw.pop("effects")
        inst = cls(ctx, combat, **raw)
        inst._effects = [InitiativeEffect.from_dict(e, combat, inst) for e in effects]
        return inst

    def to_dict(self):
        d = super().to_dict()
        d.update({
            "controller_id": self.controller_id,
            "init": self.init,
            "private": self.is_private,
            "index": self.index,
            "notes": self.notes,
            "effects": [e.to_dict() for e in self._effects],
            "group_id": self._group_id,
            "type": self.type.value,
            "id": self.id,
        })
        return d

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = new_name

    @property
    def init_skill(self) -> Skill:
        return self.skills.initiative

    @property
    def max_hp(self) -> int:
        base_hp = self._max_hp or 0
        base_effect_hp = self.active_effects(mapper=lambda effect: effect.effects.max_hp_value, reducer=max, default=0)
        bonus_effect_hp = self.active_effects(mapper=lambda effect: effect.effects.max_hp_bonus, reducer=sum, default=0)
        return (base_effect_hp or base_hp) + bonus_effect_hp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp
        if self._hp is None:
            self._hp = new_max_hp

    @property
    def hp(self) -> Optional[int]:
        return self._hp

    @hp.setter
    def hp(self, new_hp):
        self._hp = new_hp

    def hp_str(self, private=False) -> str:
        """Returns a string representation of the combatant's HP."""
        out = ""
        if not self.is_private or private:
            hp_strs = []
            if self.max_hp is not None and self.hp is not None:
                hp_strs.append(f"{self.hp}/{self.max_hp} HP")
            elif self.hp is not None:
                hp_strs.append(f"{self.hp} HP")

            if self.temp_hp and self.temp_hp > 0:
                hp_strs.append(f"{self.temp_hp} temp")

            out = f"<{', '.join(hp_strs) or 'None'}>"

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
        else:  # Max HP is less than 0?!
            out = "<Very Dead>"
        return out

    @property
    def ac(self) -> int:
        base_ac = self._ac or 0
        base_effect_ac = self.active_effects(mapper=lambda effect: effect.effects.ac_value, reducer=max, default=0)
        bonus_effect_ac = self.active_effects(mapper=lambda effect: effect.effects.ac_bonus, reducer=sum, default=0)
        return (base_effect_ac or base_ac) + bonus_effect_ac

    @ac.setter
    def ac(self, new_ac):
        self._ac = new_ac

    @property
    def base_ac(self) -> Optional[int]:
        """The base AC, unaffected by any passive effects."""
        return self._ac

    @property
    def resistances(self) -> Resistances:
        out = self._resistances.copy()
        out.update(
            Resistances(
                resist=self.active_effects(
                    mapper=lambda effect: effect.effects.resistances,
                    reducer=lambda resists: list(itertools.chain(*resists)),
                    default=[],
                ),
                immune=self.active_effects(
                    mapper=lambda effect: effect.effects.immunities,
                    reducer=lambda resists: list(itertools.chain(*resists)),
                    default=[],
                ),
                vuln=self.active_effects(
                    mapper=lambda effect: effect.effects.vulnerabilities,
                    reducer=lambda resists: list(itertools.chain(*resists)),
                    default=[],
                ),
                neutral=self.active_effects(
                    mapper=lambda effect: effect.effects.ignored_resistances,
                    reducer=lambda resists: list(itertools.chain(*resists)),
                    default=[],
                ),
            ),
            overwrite=False,
        )
        return out

    @property
    def base_resistances(self) -> Resistances:
        """The base resistances, unaffected by any passive effects."""
        return self._resistances

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
    def attacks(self) -> AttackList:
        if "attacks" not in self._cache:
            # attacks granted by effects are cached so that the same object is referenced in initTracker (#950)
            effect_attacks = self.active_effects(
                mapper=lambda effect: [i.attack for i in effect.attacks],
                reducer=lambda attacks: AttackList(list(itertools.chain(*attacks))),
            )
            if effect_attacks is not None:
                self._cache["attacks"] = self._attacks + effect_attacks
            else:
                self._cache["attacks"] = self._attacks
        return self._cache["attacks"]

    @property
    def index(self) -> int:
        """The combatant's index in the Combat combatant array. If the combatant is in a group, the group's index."""
        if self._group_id:
            return self.get_group().index
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    @property
    def group(self) -> Optional[str]:
        return self._group_id

    @group.setter
    def group(self, value):
        self._group_id = value

    @property
    def _effect_id_map(self) -> dict[str, InitiativeEffect]:
        if "effect_id_map" in self._cache:
            return self._cache["effect_id_map"]
        effect_id_map = {e.id: e for e in self._effects}
        self._cache["effect_id_map"] = effect_id_map
        return effect_id_map

    def set_group(self, group_name: Optional[str]) -> Optional["CombatantGroup"]:
        current = self.combat.current_combatant
        was_current = current is not None and (
            self is current or (current.type == CombatantType.GROUP and self in current and len(current) == 1)
        )
        self.combat.remove_combatant(self, ignore_remove_hook=True)
        if isinstance(group_name, str) and group_name.lower() == "none":
            group_name = None
        if group_name is None:
            self.combat.add_combatant(self)
            if was_current:
                self.combat.goto_turn(self, True)
            return None
        else:
            c_group = self.combat.get_group(group_name, create=self.init)
            c_group.add_combatant(self)
            if was_current:
                self.combat.goto_turn(self, True)
            return c_group

    def get_group(self) -> Optional["CombatantGroup"]:
        return self.combat.get_group(self._group_id) if self._group_id else None

    # effects
    def add_effect(self, effect: InitiativeEffect):
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

    def get_effects(self) -> list[InitiativeEffect]:
        return self._effects

    def effect_by_id(self, effect_id: str) -> Optional[InitiativeEffect]:
        return self._effect_id_map.get(effect_id)

    def get_effect(self, name: str, strict=True) -> Optional[InitiativeEffect]:
        if strict:
            return next((c for c in self.get_effects() if c.name == name), None)
        else:
            return next((c for c in self.get_effects() if name.lower() in c.name.lower()), None)

    async def select_effect(self, name: str) -> Optional[InitiativeEffect]:
        """
        Opens a prompt for a user to select the effect they were searching for.

        :param name: The name of the effect to search for.
        :return: The selected Effect, or None if the search failed.
        """
        return await search_and_select(self.ctx, self.get_effects(), name, lambda e: e.name)

    def remove_effect(self, effect: InitiativeEffect):
        try:
            self._effects.remove(effect)
        except ValueError:
            # this should be safe
            # the only case where this occurs is if a parent removes an effect while it's trying to remove itself
            pass
        # invalidate cache
        self._invalidate_effect_cache()

    def remove_all_effects(self, _filter: Callable[[InitiativeEffect], bool] = None) -> list[InitiativeEffect]:
        if _filter is None:
            to_remove = self._effects.copy()
        else:
            to_remove = list(filter(_filter, self._effects))
        for e in to_remove:
            e.remove()
        return to_remove

    def active_effects(
        self,
        mapper: Callable[[InitiativeEffect], _IntermediateT],
        reducer: Callable[[List[_IntermediateT]], T] = lambda mapped: mapped,
        default: T = None,
    ) -> T:
        """
        Map/Reduce operation over each effect on the combatant to reduce everything down to a single value.
        If the mapper returns a falsy value, the value will not be passed to the reducer.
        If there are no elements to reduce, returns *default*.
        """
        values = [value for effect in self.get_effects() if (value := mapper(effect))]
        if values:
            return reducer(values)
        return default

    def _invalidate_effect_cache(self):
        if "attacks" in self._cache:
            del self._cache["attacks"]
        if "effect_id_map" in self._cache:
            del self._cache["effect_id_map"]

    def is_concentrating(self) -> bool:
        return any(e.concentration for e in self.get_effects())

    # controller stuff
    def controller_mention(self) -> str:
        return f"<@{self.controller_id}>"

    async def message_controller(self, ctx, *args, **kwargs):
        """Sends a message to the combatant's controller."""
        if ctx.guild is None:
            raise RequiresContext("message_controller requires a guild context.")
        if self.controller_id == ctx.bot.user.id:  # don't message self
            return
        member = await get_guild_member(ctx.guild, self.controller_id)
        if member is None:  # member is not in the guild, oh well
            return
        try:
            await member.send(*args, **kwargs)
        except disnake.Forbidden:  # member is not accepting PMs from us, oh well
            pass

    # hooks
    def on_turn(self, num_turns: int = 1):
        """
        A method called at the start of each combatant's turns.
        :param num_turns: The number of turns that just passed.
        :return: None
        """
        for e in self.get_effects().copy():
            e.on_turn(num_turns)

    def on_remove(self):
        """
        Called when the combatant is removed from combat, either through !i remove or the combat ending.
        """
        self.remove_all_effects()

    # stringification
    def get_summary(self, private=False, no_notes=False) -> str:
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        hp_str = f"{self.hp_str(private)} " if self.hp_str(private) else ""
        if not no_notes:
            return f"{self.init:>2}: {self.name} {hp_str}{self._get_effects_and_notes()}"
        else:
            return f"{self.init:>2}: {self.name} {hp_str}"

    def get_status(
        self,
        private=False,
        resistances=True,
        notes=True,
        duration=True,
        parenthetical=True,
        concentration=True,
        description=True,
    ) -> str:
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :param duration:
        :return: A string describing the combatant.
        """
        name = self.name
        hp_ac = self._get_hp_and_ac(private)
        resists = self._get_resist_string(private) if resistances else ""
        note_str = "\n# " + self.notes if self.notes and notes else ""
        effects = self._get_long_effects(
            duration=duration, parenthetical=parenthetical, concentration=concentration, description=description
        )
        return f"{name} {hp_ac} {resists}{note_str}\n{effects}".strip()

    def _get_long_effects(self, **kwargs) -> str:
        return "\n".join(f"* {e.get_str(**kwargs)}" for e in self.get_effects())

    def _get_effects_and_notes(self) -> str:
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

    def _get_hp_and_ac(self, private: bool = False) -> str:
        out = [self.hp_str(private)]
        if (self._ac is not None or self.ac) and (not self.is_private or private):
            out.append(f"(AC {self.ac})")
        return " ".join(out)

    def _get_resist_string(self, private: bool = False) -> str:
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
        return hash(f"{self.combat.channel_id}.{self.name}")


class MonsterCombatant(Combatant):
    DESERIALIZE_MAP = {**DESERIALIZE_MAP, "spellbook": MonsterCastableSpellbook}
    type = CombatantType.MONSTER

    def __init__(
        self,
        # init metadata
        ctx,
        combat,
        id: str,
        name: str,
        controller_id: int,
        private: bool,
        init: int,
        index: int = None,
        notes: str = None,
        effects: List[InitiativeEffect] = None,
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
        # monster specific
        monster_name: str = None,
        monster_id: int = None,
        creature_type: str = None,
        **_,
    ):
        super().__init__(
            ctx,
            combat,
            id,
            name,
            controller_id,
            private,
            init,
            index,
            notes,
            effects,
            group_id,
            stats,
            levels,
            attacks,
            skills,
            saves,
            resistances,
            spellbook,
            ac,
            max_hp,
            hp,
            temp_hp,
            creature_type=creature_type,
        )
        self._monster_name = monster_name
        self._monster_id = monster_id

    @classmethod
    def from_monster(cls, monster, ctx, combat, name, controller_id, init, private, hp=None, ac=None):
        monster_name = monster.name
        creature_type = monster.creature_type
        hp = int(monster.hp) if not hp else int(hp)
        ac = int(monster.ac) if not ac else int(ac)
        id = create_combatant_id()

        # copy spellbook
        spellbook = None
        if monster.spellbook is not None:
            spellbook = MonsterCastableSpellbook.copy(monster.spellbook)

        # copy resistances (#1134)
        resistances = monster.resistances.copy()

        return cls(
            ctx,
            combat,
            id,
            name,
            controller_id,
            private,
            init,
            # statblock info
            stats=monster.stats,
            levels=monster.levels,
            attacks=monster.attacks,
            skills=monster.skills,
            saves=monster.saves,
            resistances=resistances,
            spellbook=spellbook,
            ac=ac,
            max_hp=hp,
            # monster specific
            monster_name=monster_name,
            monster_id=monster.entity_id,
            creature_type=creature_type,
        )

    # ser/deser
    @classmethod
    def from_dict(cls, raw, ctx, combat):
        inst = super().from_dict(raw, ctx, combat)
        inst._monster_name = raw["monster_name"]
        inst._monster_id = raw.get("monster_id")
        return inst

    def to_dict(self):
        raw = super().to_dict()
        raw.update({"monster_name": self._monster_name, "monster_id": self._monster_id})
        return raw

    # members
    @property
    def monster_name(self) -> str:
        return self._monster_name

    @property
    def monster_id(self) -> Optional[int]:
        return self._monster_id


class PlayerCombatant(Combatant):
    type = CombatantType.PLAYER

    def __init__(
        self,
        # init metadata
        ctx,
        combat,
        id: str,
        name: str,
        controller_id: int,
        private: bool,
        init: int,
        index: int = None,
        notes: str = None,
        effects: List[InitiativeEffect] = None,
        group_id: str = None,
        # statblock info
        attacks: AttackList = None,
        resistances: Resistances = None,
        ac: int = None,
        max_hp: int = None,
        # character specific
        character_id: str = None,
        character_owner: str = None,
        **_,
    ):
        # note that the player combatant doesn't initialize the statblock
        # because we want the combatant statblock attrs to reference the character attrs
        super().__init__(
            ctx,
            combat,
            id,
            name,
            controller_id,
            private,
            init,
            index,
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
    def from_character(cls, character, ctx, combat, controller_id, init, private):
        id = create_combatant_id()
        inst = cls(
            ctx,
            combat,
            id,
            character.name,
            controller_id,
            private,
            init,
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
    async def from_dict(cls, raw, ctx, combat):
        inst = super().from_dict(raw, ctx, combat)
        inst.character_id = raw["character_id"]
        inst.character_owner = raw["character_owner"]
        inst._character = await cogs5e.models.character.Character.from_bot_and_ids(
            ctx.bot, inst.character_owner, inst.character_id
        )
        return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx, combat):
        inst = super().from_dict(raw, ctx, combat)
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
        if one is cached (since Combat cache TTL > Character cache TTL), preventing instance divergence.

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
    def character(self) -> cogs5e.models.character.Character:
        return self._character

    @property
    def init_skill(self) -> Skill:
        return self.character.skills.initiative

    @property
    def stats(self) -> BaseStats:
        return self.character.stats

    @property
    def levels(self) -> Levels:
        return self.character.levels

    @property
    def skills(self) -> Skills:
        return self.character.skills

    @property
    def saves(self) -> Saves:
        return self.character.saves

    @property
    def ac(self) -> int:
        base_ac = self.base_ac
        base_effect_ac = self.active_effects(mapper=lambda effect: effect.effects.ac_value, reducer=max, default=0)
        bonus_effect_ac = self.active_effects(mapper=lambda effect: effect.effects.ac_bonus, reducer=sum, default=0)
        return (base_effect_ac or base_ac) + bonus_effect_ac

    @ac.setter
    def ac(self, new_ac):
        """
        :param int|None new_ac: The new AC
        """
        self._ac = new_ac

    @property
    def base_ac(self) -> int:
        return self._ac or self.character.ac

    @property
    def spellbook(self) -> Spellbook:
        return self.character.spellbook

    @property
    def max_hp(self) -> int:
        base_hp = self._max_hp or self.character.max_hp
        base_effect_hp = self.active_effects(mapper=lambda effect: effect.effects.max_hp_value, reducer=max, default=0)
        bonus_effect_hp = self.active_effects(mapper=lambda effect: effect.effects.max_hp_bonus, reducer=sum, default=0)
        return (base_effect_hp or base_hp) + bonus_effect_hp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp

    @property
    def hp(self) -> int:
        return self.character.hp

    @hp.setter
    def hp(self, new_hp):
        self.character.hp = new_hp

    def set_hp(self, new_hp):
        return self.character.set_hp(new_hp)

    def reset_hp(self):
        return self.character.reset_hp()

    @property
    def temp_hp(self) -> int:
        return self.character.temp_hp

    @temp_hp.setter
    def temp_hp(self, new_hp):
        self.character.temp_hp = new_hp

    @property
    def attacks(self) -> AttackList:
        return super().attacks + self.character.attacks

    def get_scope_locals(self):
        return {**self.character.get_scope_locals(), **super().get_scope_locals()}

    def get_color(self):
        return self.character.get_color()
