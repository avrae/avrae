import logging
from collections import namedtuple

import cachetools
import d20
from discord.ext.commands import NoPrivateMessage

from cogs5e.models.errors import ExternalImportError
from utils.dice import VerboseMDStringifier
from .errors import NoEncounter

from ..models.embeds import EmbedWithColor

log = logging.getLogger(__name__)


class Encounter:
    # cache encounters for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Encounter.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Encounter state
    # caches based on (owner, upstream)
    _cache = cachetools.TTLCache(maxsize=50, ttl=5)

    def __init__(
        self,
        owner: str,
        upstream: str,
        active: bool,
        name: str = None,
        numappear: list = None,
        encountervalues: list = None,
        dice_expression: str = None,
        active_guilds: list = None,
    ):
        if active_guilds is None:
            active_guilds = []

        # sheet metadata
        self._owner = owner
        self._upstream = upstream
        self._active = active
        self._active_guilds = active_guilds

        # main info
        self.name = name
        self.numappear = numappear
        self.encountervalues = encountervalues
        self.dice_expression = dice_expression

    # ---------- Deserialization ----------

    @classmethod
    def from_dict(cls, raw):
        if "_id" in raw:
            del raw["_id"]
        return cls(**raw)

    @classmethod
    async def from_ctx(cls, ctx, ignore_guild: bool = False):
        owner_id = str(ctx.author.id)
        active_encounter = None
        if ctx.guild is not None and not ignore_guild:
            guild_id = str(ctx.guild.id)
            active_encounter = await ctx.bot.mdb.encounters.find_one({"owner": owner_id, "active_guilds": guild_id})
        if active_encounter is None:
            active_encounter = await ctx.bot.mdb.encounters.find_one({"owner": owner_id, "active": True})
        if active_encounter is None:
            raise NoEncounter()

        try:
            # return from cache if available
            return cls._cache[owner_id, active_encounter["upstream"]]
        except KeyError:
            # otherwise deserialize and write to cache
            inst = cls.from_dict(active_encounter)
            cls._cache[owner_id, active_encounter["upstream"]] = inst
            return inst

    @classmethod
    async def from_bot_and_ids(cls, bot, owner_id: str, upstream: str):
        owner_id = str(owner_id)

        try:
            # read from cache if available
            return cls._cache[owner_id, upstream]
        except KeyError:
            pass

        encounter = await bot.mdb.encounters.find_one({"owner": owner_id, "upstream": upstream})
        if encounter is None:
            raise NoEncounter()
        # write to cache
        inst = cls.from_dict(encounter)
        cls._cache[owner_id, upstream] = inst
        return inst

    @classmethod
    def from_bot_and_ids_sync(cls, bot, owner_id: str, upstream: str):
        owner_id = str(owner_id)

        try:
            # read from cache if available
            return cls._cache[owner_id, upstream]
        except KeyError:
            pass

        encounter = bot.mdb.encounters.delegate.find_one({"owner": owner_id, "upstream": upstream})
        if encounter is None:
            raise NoEncounter()
        # write to cache
        inst = cls.from_dict(encounter)
        cls._cache[owner_id, upstream] = inst
        return inst

    # ---------- Serialization ----------
    def to_dict(self):
        d = {
            "owner": self._owner,
            "upstream": self._upstream,
            "active": self._active,
            "name": self.name,
            "numappear": self.numappear,
            "encountervalues": self.encountervalues,
            "dice_expression": self.dice_expression,
            "active_guilds": self._active_guilds,
        }
        return d

    @staticmethod
    async def delete(ctx, owner_id, upstream):
        await ctx.bot.mdb.encounters.delete_one({"owner": owner_id, "upstream": upstream})
        try:
            del Encounter._cache[owner_id, upstream]
        except KeyError:
            pass

    async def commit(self, ctx):
        """Writes an encounter object to the database, under the contextual author."""
        data = self.to_dict()
        data.pop("active")  # #1472 - may regress when doing atomic commits, be careful
        data.pop("active_guilds")
        try:
            await ctx.bot.mdb.encounters.update_one(
                {"owner": self._owner, "upstream": self._upstream},
                {
                    "$set": data,
                    "$setOnInsert": {"active": self._active, "active_guilds": self._active_guilds},  # also #1472
                },
                upsert=True,
            )
        except OverflowError:
            raise ExternalImportError("A number on the encounter sheet is too large to store.")

    async def set_active(self, ctx):
        """Sets the encounter sheet as globally active and unsets any server-active sheet in the current context."""
        owner_id = str(ctx.author.id)
        did_unset_server_active = False
        if ctx.guild is not None:
            guild_id = str(ctx.guild.id)
            # for all sheets owned by this owner who are active on this guild, make them inactive on this guild
            result = await ctx.bot.mdb.encounters.update_many(
                {"owner": owner_id, "active_guilds": guild_id}, {"$pull": {"active_guilds": guild_id}}
            )
            did_unset_server_active = result.modified_count > 0
            try:
                self._active_guilds.remove(guild_id)
            except ValueError:
                pass
        # for all encounter sheets owned by this owner who are globally active, make them inactive
        await ctx.bot.mdb.encounters.update_many({"owner": owner_id, "active": True}, {"$set": {"active": False}})
        # make this encounter sheet active
        await ctx.bot.mdb.encounters.update_one(
            {"owner": owner_id, "upstream": self._upstream}, {"$set": {"active": True}}
        )
        self._active = True
        return SetActiveResult(did_unset_server_active=did_unset_server_active)

    async def set_server_active(self, ctx):
        """
        Removes all server-active encounters and sets the encounter as active on the current server.
        Raises NoPrivateMessage() if not in a server.
        """
        if ctx.guild is None:
            raise NoPrivateMessage()
        guild_id = str(ctx.guild.id)
        owner_id = str(ctx.author.id)
        # unset anyone else that might be active on this server
        unset_result = await ctx.bot.mdb.encounters.update_many(
            {"owner": owner_id, "active_guilds": guild_id}, {"$pull": {"active_guilds": guild_id}}
        )
        # set us as active on this server
        await ctx.bot.mdb.encounters.update_one(
            {"owner": owner_id, "upstream": self._upstream}, {"$addToSet": {"active_guilds": guild_id}}
        )
        if guild_id not in self._active_guilds:
            self._active_guilds.append(guild_id)
        return SetActiveResult(did_unset_server_active=unset_result.modified_count > 0)

    async def unset_server_active(self, ctx):
        """
        If this encounter is active on the contextual guild, unset it as the guild active encounter.
        Raises NoPrivateMessage() if not in a server.
        """
        if ctx.guild is None:
            raise NoPrivateMessage()
        guild_id = str(ctx.guild.id)
        # if and only if this encounter is active in this server, unset me as active on this server
        unset_result = await ctx.bot.mdb.encounters.update_one(
            {"owner": str(ctx.author.id), "upstream": self._upstream}, {"$pull": {"active_guilds": guild_id}}
        )
        try:
            self._active_guilds.remove(guild_id)
        except ValueError:
            pass
        return SetActiveResult(did_unset_server_active=unset_result.modified_count > 0)

    @property
    def owner(self) -> str:
        return self._owner

    @owner.setter
    def owner(self, value: str):
        self._owner = value

    @property
    def upstream(self) -> str:
        return self._upstream

    @property
    def upstream_id(self) -> str:
        return self._upstream.split("-", 1)[-1]

    def get_sheet_embed(self):
        embed = EmbedWithColor()
        # noinspection PyListCreation
        # this could be a list literal, but it's more readable this way
        desc_details = []

        # combat details
        desc_details.append(f"**Name**: {self.name}")
        desc_details.append(f"Dice to roll: {self.dice_expression}")
        length = len(self.numappear)
        for n in range(0, length):
            desc_details.append(f"{n+1}) {self.numappear[n]} {self.encountervalues[n]}")
        embed.description = "\n".join(desc_details)

        return embed

    def is_active_global(self):
        """Returns if an encounter sheet is active globally."""
        return self._active

    def is_active_server(self, ctx):
        """Returns if an encounter sheet is active on the contextual server."""
        if ctx.guild is not None:
            return str(ctx.guild.id) in self._active_guilds
        return False

    def get_sheet_url(self):
        """
        Returns the sheet URL this encounter lives at.
        """
        return f"https://docs.google.com/spreadsheets/d/{self.upstream_id}"

    def get_renc(self, number):
        """
        Returns the random encounter and number of monsters rolled if any
        :param number: result of the dice roll
        :return: tuple of encounter and number appearing
        """
        if self.encountervalues is None:
            raise NoEncounter
        if self.numappear[number-1] is not None:
            dice = self.numappear[number-1]
            adv = d20.AdvType.NONE
            res = d20.roll(dice, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier()).total
            enc = (self.encountervalues[number-1], res, number)
        else:
            enc = (self.encountervalues[number-1], None, number)
        return enc

    def roll_encounters(self, number, chance):
        """
        Rolls random encounters
        :param: number: how many times it has to be rolled
        :param: chance: how likely it is for an encounter to be rolled
        :return: List of (encounter, number appearing) tuples
        """
        dice = self.dice_expression
        adv = d20.AdvType.NONE
        encounters = []
        for n in range(number):
            chn = d20.roll("1d100", advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier()).total
            if chn < chance:
                res = d20.roll(dice, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier())
                total = res.total
                encounters.append(self.get_renc(total))
        return encounters


SetActiveResult = namedtuple("SetActiveResult", "did_unset_server_active")
