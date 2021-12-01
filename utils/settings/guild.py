import enum

from . import SettingsBaseModel


class InlineRollingType(enum.IntEnum):
    DISABLED = 0
    REACTION = 1
    ENABLED = 2


class ServerSettings(SettingsBaseModel):
    guild_id: int
    # lookup_dm_role: int = 1234
    lookup_dm_required: bool = True
    lookup_pm_dm: bool = False
    lookup_pm_result: bool = False
    inline_enabled: InlineRollingType = InlineRollingType.DISABLED

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
            lookup_dm_required=d.get('req_dm_monster', True),
            lookup_pm_dm=d.get('pm_dm', False),
            lookup_pm_result=d.get('pm_result', False)
        )

    async def commit(self, mdb):
        """Commits the settings to the database."""
        await mdb.guild_settings.update_one(
            {"guild_id": self.guild_id},
            {"$set": self.dict()},
            upsert=True
        )
