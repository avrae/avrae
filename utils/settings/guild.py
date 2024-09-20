import enum
from typing import List, Optional, Literal

import disnake
from pydantic import BaseModel

from . import SettingsBaseModel
from utils.enums import CritDamageType

DEFAULT_DM_ROLE_NAMES = {"dm", "gm", "dungeon master", "game master"}


class InlineRollingType(enum.IntEnum):
    DISABLED = 0
    REACTION = 1
    ENABLED = 2


class LegacyPreference(enum.IntEnum):
    LATEST = 1
    LEGACY = 2
    ASK = 3


class RandcharRule(BaseModel):
    type: Literal["gt", "lt"]
    amount: int
    value: int


class ServerSettings(SettingsBaseModel):
    guild_id: int
    dm_roles: Optional[List[int]] = None
    lookup_dm_required: bool = True
    lookup_pm_dm: bool = False
    lookup_pm_result: bool = False
    inline_enabled: InlineRollingType = InlineRollingType.DISABLED
    show_campaign_cta: bool = True
    upenn_nlp_opt_in: bool = False
    crit_type: CritDamageType = CritDamageType.NORMAL
    legacy_preference: LegacyPreference = LegacyPreference.LATEST
    version: str = "2024"  # Versions: 2024(Free Rules/PHB 2024) or 2014(BR/PHB 2014)

    randchar_dice: str = "4d6kh3"
    randchar_sets: int = 1
    randchar_straight: bool = False
    randchar_stat_names: Optional[List[str]] = None
    randchar_num: int = 6
    randchar_min: int = None
    randchar_max: int = None
    randchar_rules: List[RandcharRule] = []

    # ==== lifecycle ====
    @classmethod
    async def for_guild(cls, mdb, guild_id: int):
        """Returns the server settings for a given guild."""
        # new-style
        existing = await mdb.guild_settings.find_one({"guild_id": guild_id})
        if existing is not None:
            return cls.parse_obj(existing)

        # old-style lookupsettings
        old_style = await mdb.lookupsettings.find_one({"server": str(guild_id)})
        if old_style is not None:
            return cls.from_old_lookupsettings(guild_id, old_style)

        return cls(guild_id=guild_id)

    @classmethod
    def from_old_lookupsettings(cls, guild_id: int, d):
        """Returns a new ServerSettings instance with all default options, updated by legacy lookupsettings options."""
        return cls(
            guild_id=guild_id,
            lookup_dm_required=d.get("req_dm_monster", True),
            lookup_pm_dm=d.get("pm_dm", False),
            lookup_pm_result=d.get("pm_result", False),
        )

    async def commit(self, mdb):
        """Commits the settings to the database."""
        await mdb.guild_settings.update_one({"guild_id": self.guild_id}, {"$set": self.dict()}, upsert=True)

    # ==== helpers ====
    def is_dm(self, member: disnake.Member):
        """Returns whether the given member is considered a DM given the DM roles specified in the servsettings."""
        if not self.dm_roles:
            return any(r.name.lower() in DEFAULT_DM_ROLE_NAMES for r in member.roles)
        dm_role_set = set(self.dm_roles)
        return any(r.id in dm_role_set for r in member.roles)
