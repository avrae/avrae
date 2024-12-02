import logging
from collections import namedtuple

import cachetools
from disnake.ext.commands import NoPrivateMessage

import aliasing.evaluators
from cogs5e.models.ddbsync import DDBSheetSync
from cogs5e.models.dicecloud.integration import DicecloudIntegration
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import ExternalImportError, InvalidArgument, NoCharacter, NoReset
from cogs5e.models.sheet.action import Actions
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.mixins import HasIntegrationMixin
from cogs5e.models.sheet.player import CustomCounter, DeathSaves, ManualOverrides
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP as _DESER, StatBlock
from cogs5e.models.sheet.coinpurse import Coinpurse
from cogs5e.sheets.abc import SHEET_VERSION
from utils.functions import confirm, search_and_select
from utils.settings import CharacterSettings
from enum import Enum

log = logging.getLogger(__name__)


class CharacterLocationContext(Enum):
    GLOBAL = "Global"
    SERVER = "Server"
    CHANNEL = "Channel"
    NOCHARACTER = "No Character"


# constants at bottom (yay execution order)


class Character(StatBlock):
    # cache characters for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Character.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Character state
    # caches based on (owner, upstream)
    _cache = cachetools.TTLCache(maxsize=50, ttl=5)

    def __init__(
        self,
        owner: str,
        upstream: str,
        active: bool,
        sheet_type: str,
        import_version: int,
        name: str,
        description: str,
        image: str,
        stats: BaseStats,
        levels: Levels,
        attacks: AttackList,
        skills: Skills,
        resistances: Resistances,
        saves: Saves,
        ac: int,
        max_hp: int,
        hp: int,
        temp_hp: int,
        cvars: dict,
        overrides: dict,
        consumables: list,
        death_saves: dict,
        spellbook: Spellbook,
        live,
        race: str,
        background: str,
        creature_type: str = None,
        ddb_campaign_id: str = None,
        actions: Actions = None,
        active_guilds: list = None,
        active_channels: list = None,
        options_v2: CharacterSettings = None,
        coinpurse=None,
        **kwargs,
    ):
        if actions is None:
            actions = Actions()
        if active_guilds is None:
            active_guilds = []
        if active_channels is None:
            active_channels = []
        if coinpurse is None:
            coinpurse = Coinpurse()
        if options_v2 is None:
            if "options" in kwargs:  # options v1 -> v2 migration (options rewrite)
                options_v2 = CharacterSettings.from_old_csettings(kwargs.pop("options"))
            else:
                options_v2 = CharacterSettings()
        if kwargs:
            log.debug(f"Unused kwargs: {kwargs}")

        # sheet metadata
        self._owner = owner
        self._upstream = upstream
        self._active = active
        self._active_guilds = active_guilds
        self._active_channels = active_channels
        self._sheet_type = sheet_type
        self._import_version = import_version
        self.coinpurse = coinpurse

        # StatBlock super call
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

        # main character info
        self._description = description
        self._image = image

        # customization
        self.cvars = cvars
        self.options = options_v2
        self.overrides = ManualOverrides.from_dict(overrides)

        # ccs
        self.consumables = [CustomCounter.from_dict(self, cons) for cons in consumables]
        self.death_saves = DeathSaves.from_dict(self, death_saves)

        # live sheet resource integrations
        self._live = live
        integration = INTEGRATION_MAP.get(live)
        if integration:
            self._live_integration = integration(self)
        else:
            self._live_integration = None

        # child objects' live integration stuff
        self.spellbook._live_integration = self._live_integration
        self.coinpurse._live_integration = self._live_integration

        # misc research things
        self.race = race
        self.background = background

        # ddb live sync
        self.ddb_campaign_id = ddb_campaign_id
        # action automation
        self.actions = actions

    # ---------- Deserialization ----------
    @classmethod
    def from_dict(cls, d):
        if "_id" in d:
            del d["_id"]
        for key, klass in DESERIALIZE_MAP.items():
            if key in d:
                d[key] = klass.from_dict(d[key])
        return cls(**d)

    @classmethod
    async def from_ctx(cls, ctx, use_global: bool = False, use_guild: bool = False, use_channel: bool = False):
        owner_id = str(ctx.author.id)
        active_character = None
        if ctx.channel is not None and use_channel:
            channel_id = str(ctx.channel.id)
            active_character = await ctx.bot.mdb.characters.find_one({"owner": owner_id, "active_channels": channel_id})
        if ctx.guild is not None and use_guild and active_character is None:
            guild_id = str(ctx.guild.id)
            active_character = await ctx.bot.mdb.characters.find_one({"owner": owner_id, "active_guilds": guild_id})
        if use_global and active_character is None:
            active_character = await ctx.bot.mdb.characters.find_one({"owner": owner_id, "active": True})
        if active_character is None:
            raise NoCharacter()

        try:
            # return from cache if available
            return cls._cache[owner_id, active_character["upstream"]]
        except KeyError:
            # otherwise deserialize and write to cache
            inst = cls.from_dict(active_character)
            cls._cache[owner_id, active_character["upstream"]] = inst
            return inst

    @classmethod
    async def from_bot_and_ids(cls, bot, owner_id: str, character_id: str):
        owner_id = str(owner_id)

        try:
            # read from cache if available
            return cls._cache[owner_id, character_id]
        except KeyError:
            pass

        character = await bot.mdb.characters.find_one({"owner": owner_id, "upstream": character_id})
        if character is None:
            raise NoCharacter()
        # write to cache
        inst = cls.from_dict(character)
        cls._cache[owner_id, character_id] = inst
        return inst

    @classmethod
    def deserialize_character_from_dict(cls, owner_id, character_dictionary):
        char = Character.from_dict(character_dictionary)
        cls._cache[owner_id, character_dictionary["upstream"]] = char
        return char

    @classmethod
    async def from_bot_and_channel_id(cls, ctx, owner_id: str, channel_id: str):
        owner_id = str(owner_id)
        channel_id = str(channel_id)

        try:
            # read from cache if available
            return cls._cache[owner_id, channel_id]
        except KeyError:
            pass

        character = await ctx.bot.mdb.characters.find_one({"owner": owner_id, "active_channels": channel_id})
        if character is None:
            raise NoCharacter()
        # write to cache
        inst = cls.from_dict(character)
        cls._cache[owner_id, channel_id] = inst
        return inst

    @classmethod
    def from_bot_and_ids_sync(cls, bot, owner_id: str, character_id: str):
        owner_id = str(owner_id)

        try:
            # read from cache if available
            return cls._cache[owner_id, character_id]
        except KeyError:
            pass

        character = bot.mdb.characters.delegate.find_one({"owner": owner_id, "upstream": character_id})
        if character is None:
            raise NoCharacter()
        # write to cache
        inst = cls.from_dict(character)
        cls._cache[owner_id, character_id] = inst
        return inst

    # ---------- Serialization ----------
    def to_dict(self):
        d = super().to_dict()
        d.update({
            "owner": self._owner,
            "upstream": self._upstream,
            "active": self._active,
            "sheet_type": self._sheet_type,
            "import_version": self._import_version,
            "description": self._description,
            "image": self._image,
            "cvars": self.cvars,
            "overrides": self.overrides.to_dict(),
            "consumables": [co.to_dict() for co in self.consumables],
            "death_saves": self.death_saves.to_dict(),
            "live": self._live,
            "race": self.race,
            "background": self.background,
            "ddb_campaign_id": self.ddb_campaign_id,
            "actions": self.actions.to_dict(),
            "active_guilds": self._active_guilds,
            "active_channels": self._active_channels,
            "options_v2": self.options.dict(),
            "coinpurse": self.coinpurse.to_dict(),
        })
        return d

    @staticmethod
    async def delete(ctx, owner_id, upstream):
        await ctx.bot.mdb.characters.delete_one({"owner": owner_id, "upstream": upstream})
        try:
            del Character._cache[owner_id, upstream]
        except KeyError:
            pass

    # ---------- Basic CRUD ----------
    def get_color(self) -> int:
        return self.options.color if self.options.color is not None else super().get_color()

    @property
    def owner(self) -> str:
        return self._owner

    @owner.setter
    def owner(self, value: str):
        self._owner = value
        self._active = False  # don't have any conflicts

    @property
    def upstream(self) -> str:
        return self._upstream

    @property
    def upstream_id(self) -> str:
        return self._upstream.split("-", 1)[-1]

    @property
    def sheet_type(self) -> str:
        return self._sheet_type

    @property
    def attacks(self) -> AttackList:
        return self._attacks + self.overrides.attacks

    @property
    def description(self) -> str:
        return self.overrides.desc or self._description

    @property
    def image(self) -> str:
        return self.overrides.image or self._image or ""

    # ---------- SCRIPTING ----------
    def evaluate_math(self, varstr):
        """Evaluates a cvar expression in a MathEvaluator.
        :param varstr - the expression to evaluate.
        :returns int - the value of the expression."""
        varstr = str(varstr).strip("<>{}")
        evaluator = aliasing.evaluators.MathEvaluator.with_character(self)

        try:
            return int(evaluator.eval(varstr))
        except Exception as e:
            raise InvalidArgument(f"Cannot evaluate {varstr}: {e}")

    def evaluate_annostr(self, varstr):
        """
        Evaluates annotated string using AutomationEvaluator with character.
        :param varstr - the string to search and replace.
        :returns str - the string with annotations evaluated
        """
        evaluator = aliasing.evaluators.AutomationEvaluator.with_character(self)

        try:
            return evaluator.transformed_str(varstr)
        except Exception as e:
            raise InvalidArgument(f"Cannot evaluate `{varstr}`: {e}")

    def set_cvar(self, name: str, val: str):
        """Sets a cvar to a string value."""
        if not name.isidentifier():
            raise InvalidArgument(
                "Cvar name must be a valid identifier "
                "(contains only a-z, A-Z, 0-9, and _, and not start with a number)."
            )
        self.cvars[name] = str(val)

    def get_scope_locals(self, no_cvars=False):
        out = super().get_scope_locals()
        if not no_cvars:
            out.update(self.cvars.copy())
        out.update({"description": self.description, "image": self.image, "color": hex(self.get_color())[2:]})
        return out

    # ---------- DATABASE ----------
    async def commit(self, ctx, do_live_integrations=True):
        """Writes a character object to the database, under the contextual author."""
        data = self.to_dict()
        data.pop("active")  # #1472 - may regress when doing atomic commits, be careful
        data.pop("active_guilds")
        data.pop("active_channels")
        try:
            await ctx.bot.mdb.characters.update_one(
                {"owner": self._owner, "upstream": self._upstream},
                {
                    "$set": data,
                    "$setOnInsert": {
                        "active": self._active,
                        "active_guilds": self._active_guilds,
                        "active_channels": self._active_channels,
                    },  # also #1472
                },
                upsert=True,
            )
        except OverflowError:
            raise ExternalImportError("A number on the character sheet is too large to store.")
        if self._live_integration is not None and do_live_integrations and self.options.sync_outbound:
            self._live_integration.commit_soon(ctx)  # creates a task to commit eventually

    async def set_active(self, ctx):
        """Sets the character as globally active and unsets any server-active character or channel-active characters."""
        channel_character = None
        try:
            channel_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=False, use_channel=True
            )
        except NoCharacter:
            pass
        server_character = None
        try:
            server_character: Character = await Character.from_ctx(
                ctx, use_global=False, use_guild=True, use_channel=False
            )
        except NoCharacter:
            pass
        global_character = None
        try:
            global_character: Character = await Character.from_ctx(
                ctx, use_global=True, use_guild=False, use_channel=False
            )
        except NoCharacter:
            pass

        messages = []
        if ctx.channel is not None and channel_character is not None and channel_character.is_active_channel(ctx):
            # for all characters owned by this owner who are active on this guild, make them inactive on this guild
            unset_channel_result = await channel_character.unset_channel_active(ctx)
            messages.append(unset_channel_result.message)
        if ctx.guild is not None and server_character is not None and server_character.is_active_server(ctx):
            # for all characters owned by this owner who are active on this guild, make them inactive on this guild
            unset_server_result = await server_character.unset_server_active(ctx)
            messages.append(unset_server_result.message)

        joined_message = "\n".join(messages)
        global_set_result = await self.set_global_active(ctx, global_character)
        message = f"{global_set_result.message}\n{joined_message}"
        return SetActiveResult(did_unset_active_location=global_set_result.did_unset_active_location, message=message)

    async def set_global_active(self, ctx, previous_character):
        """Sets the current class as the global active character"""
        owner_id = str(ctx.author.id)
        did_unset_active_location = False
        # for all characters owned by this owner who are globally active, make them inactive
        await ctx.bot.mdb.characters.update_many({"owner": owner_id, "active": True}, {"$set": {"active": False}})
        # make this character active
        await ctx.bot.mdb.characters.update_one(
            {"owner": owner_id, "upstream": self._upstream}, {"$set": {"active": True}}
        )
        self._active = True
        message = f"Global character set to '{self.name}'"
        if previous_character:
            message = f"{message}\nUnset previous Global character '{previous_character.name}'"
        return SetActiveResult(
            did_unset_active_location=did_unset_active_location,
            message=message,
        )

    async def set_server_active(self, ctx, previous_character):
        """
        Removes all server-active characters and sets the character as active on the current server.
        Raises NoPrivateMessage() if not in a server.
        """
        if ctx.guild is None:
            raise NoPrivateMessage()
        guild_id = str(ctx.guild.id)
        owner_id = str(ctx.author.id)
        # unset anyone else that might be active with this server id
        unset_result = await ctx.bot.mdb.characters.update_many(
            {"owner": owner_id, "active_guilds": guild_id}, {"$pull": {"active_guilds": guild_id}}
        )
        # set us as active with this server id
        await ctx.bot.mdb.characters.update_one(
            {"owner": owner_id, "upstream": self._upstream}, {"$addToSet": {"active_guilds": guild_id}}
        )
        if guild_id not in self._active_guilds:
            self._active_guilds.append(guild_id)
        message = f"Server character set to '{self.name}'"
        if previous_character:
            message = f"{message}\nUnset previous Server character '{previous_character.name}'"
        return SetActiveResult(
            did_unset_active_location=unset_result.modified_count > 0,
            message=message,
        )

    async def unset_server_active(self, ctx):
        """
        If this character is active on the contextual guild, unset it as the guild active character.
        Raises NoPrivateMessage() if not in a server.
        """
        if ctx.guild is None:
            raise NoPrivateMessage()
        guild_id = str(ctx.guild.id)
        # if and only if this character is active in this server/channel, unset me as active on this server/channel
        unset_result = await ctx.bot.mdb.characters.update_one(
            {"owner": str(ctx.author.id), "upstream": self._upstream}, {"$pull": {"active_guilds": guild_id}}
        )
        try:
            self._active_guilds.remove(guild_id)
        except ValueError:
            pass
        did_unset_active_location = unset_result.modified_count > 0
        message = ""
        if did_unset_active_location:
            message = f"Unset previous Server character '{self.name}'"
        else:
            message = "No server character was set"
        return SetActiveResult(
            did_unset_active_location=did_unset_active_location,
            message=message,
        )

    async def set_channel_active(self, ctx, previous_character):
        """
        Removes all channel-active characters and sets the character as active on the current channel.
        Raises NoPrivateMessage() if not in a channel.
        """
        if ctx.channel is None:
            raise NoPrivateMessage()
        channel_id = str(ctx.channel.id)
        owner_id = str(ctx.author.id)
        # unset anyone else that might be active with this server/channel id
        unset_result = await ctx.bot.mdb.characters.update_many(
            {"owner": owner_id, "active_channels": channel_id}, {"$pull": {"active_channels": channel_id}}
        )
        # set us as active with this server/channel id
        await ctx.bot.mdb.characters.update_one(
            {"owner": owner_id, "upstream": self._upstream}, {"$addToSet": {"active_channels": channel_id}}
        )
        if channel_id not in self._active_channels:
            self._active_channels.append(channel_id)

        message = f"Channel character set to '{self.name}'"
        if previous_character:
            message = f"{message}\nUnset previous Channel character '{previous_character.name}'"
        return SetActiveResult(
            did_unset_active_location=unset_result.modified_count > 0,
            message=message,
        )

    async def unset_channel_active(self, ctx):
        """
        If this character is active on the contextual channel, unset it as the channel active character.
        Raises NoPrivateMessage() if not in a channel.
        """
        if ctx.channel is None:
            raise NoPrivateMessage()
        channel_id = str(ctx.channel.id)
        return await self.unset_active_channel_helper(ctx, channel_id)

    async def unset_active_channel_helper(self, ctx, channel_id):
        channel_id = str(channel_id)
        # if and only if this character is active in this channel, unset me as active on this server/channel
        unset_result = await ctx.bot.mdb.characters.update_one(
            {"owner": str(ctx.author.id), "upstream": self._upstream}, {"$pull": {"active_channels": channel_id}}
        )
        try:
            self._active_channels.remove(channel_id)
        except ValueError:
            pass

        did_unset_active_location = unset_result.modified_count > 0
        message = ""
        if did_unset_active_location:
            message = f"Unset previous Channel character '{self.name}'"
        else:
            message = "No channel character was set"
        return SetActiveResult(
            did_unset_active_location=unset_result.modified_count > 0,
            message=message,
        )

    # ---------- HP ----------
    @property
    def hp(self):
        return super().hp

    @hp.setter
    def hp(self, value):
        old_hp = self._hp
        self._hp = max(0, value)  # reimplements the setter, but super().(property) = x doesn't work (py-14965)
        self.on_hp()
        if self._live_integration and self._hp != old_hp:
            self._live_integration.sync_hp()

    @property
    def temp_hp(self):
        return super().temp_hp

    @temp_hp.setter
    def temp_hp(self, value):
        old_temp = self._temp_hp
        self._temp_hp = max(0, value)
        if self._live_integration and self._temp_hp != old_temp:
            self._live_integration.sync_hp()

    @property
    def max_hp(self):
        return super().max_hp

    @max_hp.setter
    def max_hp(self, value):
        """
        Sets the character's base/canonical permanent max hp, which can be further modified by effects.
        To temporarily change the character's max hp (i.e. in combat), use PlayerCombatant.max_hp.
        """
        self._max_hp = max(0, value)

    # ---------- SPELLBOOK ----------
    def add_known_spell(self, spell, dc: int = None, sab: int = None, mod: int = None):
        """Adds a spell to the character's known spell list."""
        if spell.name in self.spellbook:
            raise InvalidArgument("You already know this spell.")
        sbs = SpellbookSpell.from_spell(spell, dc, sab, mod, self.options.version)

        self.spellbook.spells.append(sbs)
        self.overrides.spells.append(sbs)

    def remove_known_spell(self, sb_spell):
        """
        Removes a spell from the character's spellbook override.
        :param sb_spell: The spell to remove.
        :type sb_spell SpellbookSpell
        """
        if sb_spell not in self.overrides.spells:
            raise InvalidArgument("This spell is not in the overrides.")
        self.overrides.spells.remove(sb_spell)
        spell_in_book = next(s for s in self.spellbook.spells if s.name == sb_spell.name)
        self.spellbook.spells.remove(spell_in_book)

    def remove_all_known_spells(self):
        """
        Removes all spells from the character's spellbook overrides.
        """
        for spell_to_remove in self.overrides.spells:
            spell_in_book = next(s for s in self.spellbook.spells if s.name == spell_to_remove.name)
            self.spellbook.spells.remove(spell_in_book)
        self.overrides.spells = []

    # ---------- CUSTOM COUNTERS ----------
    async def select_consumable(self, ctx, name):
        return await search_and_select(ctx, self.consumables, name, lambda ctr: ctr.name)

    def get_consumable(self, name):
        """Gets the next custom counter with the exact given name (case-sensitive). Returns None if not found."""
        return next((con for con in self.consumables if con.name == name), None)

    def sync_consumable(self, ctr):
        if self._live_integration:
            self._live_integration.sync_consumable(ctr)

    def _reset_custom(self, scope):
        """
        Resets custom counters with given scope.
        Returns a list of all the reset counters and their deltas in [(counter, delta)].
        """
        reset = []
        for ctr in self.consumables:
            if ctr.reset_on == scope:
                try:
                    result = ctr.reset()
                except NoReset:
                    continue
                reset.append((ctr, result))
        return reset

    # ---------- RESTING ----------
    def on_hp(self):
        """
        Returns a list of all the reset counters and their reset results in [(counter, result)].
        Resets but does not return Death Saves.
        """
        reset = []
        reset.extend(self._reset_custom("hp"))
        if self.hp > 0:
            self.death_saves.reset()
        return reset

    def short_rest(self, cascade=True):
        """
        Returns a list of all the reset counters and their reset results in [(counter, result)].
        Resets but does not return Spell Slots or Death Saves.
        """
        reset = []
        if cascade:
            reset.extend(self.on_hp())
        reset.extend(self._reset_custom("short"))
        if self.options.srslots:
            self.spellbook.reset_slots()  # reset as if it was a long rest (legacy)
        else:
            self.spellbook.reset_pact_slots()
        return reset

    def long_rest(self, cascade=True):
        """
        Resets all applicable consumables.
        Returns a list of all the reset counters and their reset results in [(counter, result)].
        Resets but does not return HP, Spell Slots, or Death Saves.
        """
        reset = []
        if cascade:
            reset.extend(self.on_hp())
            reset.extend(self.short_rest(cascade=False))
        reset.extend(self._reset_custom("long"))
        self.reset_hp()
        self.spellbook.reset_slots()
        return reset

    def reset_all_consumables(self, cascade=True):
        """
        Returns a list of all the reset counters and their reset results in [(counter, result)].
        Resets but does not return HP, Spell Slots, or Death Saves.
        """
        reset = []
        if cascade:
            reset.extend(self.on_hp())
            reset.extend(self.short_rest(cascade=False))
            reset.extend(self.long_rest(cascade=False))
        reset.extend(self._reset_custom(None))
        return reset

    # ---------- MISC ----------
    def sync_death_saves(self):
        if self._live_integration:
            self._live_integration.sync_death_saves()

    def update(self, old_character):
        """
        Updates certain attributes to match an old character's.
        Currently updates settings, overrides, cvars, active guilds, consumables, overriden spellbook spells,
        hp, temp hp, death saves, used spell slots
        and caches the new character.
        :type old_character Character
        """
        # top level things
        self.options = old_character.options
        self.overrides = old_character.overrides
        self.cvars = old_character.cvars
        self._active_guilds = old_character._active_guilds
        self._active_channels = old_character._active_channels

        # consumables: no duplicate name or live (upstream) ids
        new_cc_names = set(con.name.lower() for con in self.consumables)
        new_cc_upstreams = set(con.live_id for con in self.consumables if con.live_id is not None)
        self.consumables.extend(
            con
            for con in old_character.consumables
            if con.name.lower() not in new_cc_names and con.live_id not in new_cc_upstreams
        )

        # coinpurse
        # only allow update to overwrite coinpurse if it's the first v19 update and the coinpurse is empty
        if old_character._import_version >= 19 or old_character.coinpurse.total > 0:
            self.coinpurse = old_character.coinpurse

        # overridden spells
        sb = self.spellbook
        sb.spells.extend(self.overrides.spells)

        # tracking
        self._hp = old_character._hp
        self._temp_hp = old_character._temp_hp
        sb.slots = {  # ensure new slots are within bounds (#1453)
            level: min(v, sb.get_max_slots(level)) for level, v in old_character.spellbook.slots.items()
        }
        if sb.num_pact_slots is not None:
            sb.num_pact_slots = min(
                old_character.spellbook.num_pact_slots or 0,  # pact slots before update
                sb.max_pact_slots,  # cannot have more then max
                sb.get_slots(sb.pact_slot_level),  # cannot gain slots out of nowhere
            )

            # sanity check:             num_non_pact <= max_non_pact
            # get_slots(pact_level) - num_pact_slots <= get_max(pact_level) - max_pact_slots
            #                         num_pact_slots >= max_pact_slots - get_max(pact_level) + get_slots(pact_level)
            sb.num_pact_slots = max(
                sb.num_pact_slots,
                sb.max_pact_slots - sb.get_max_slots(sb.pact_slot_level) + sb.get_slots(sb.pact_slot_level),
            )

        if (self.owner, self.upstream) in Character._cache:
            Character._cache[self.owner, self.upstream] = self

    def get_sheet_embed(self):
        embed = EmbedWithCharacter(self)
        # noinspection PyListCreation
        # this could be a list literal, but it's more readable this way
        desc_details = []

        # race/class (e.g. Tiefling Bard/Warlock)
        desc_details.append(f"{self.race} {str(self.levels)}")

        # prof bonus
        desc_details.append(f"**Proficiency Bonus**: {self.stats.prof_bonus:+}")

        # combat details
        desc_details.append(f"**AC**: {self.ac}")
        desc_details.append(f"**HP**: {self.hp_str()}")
        desc_details.append(f"**Initiative**: {self.skills.initiative.value:+}")

        # stats
        desc_details.append(str(self.stats))
        save_profs = str(self.saves)
        if save_profs:
            desc_details.append(f"**Save Proficiencies**: {save_profs}")
        skill_profs = str(self.skills)
        if skill_profs:
            desc_details.append(f"**Skill Proficiencies**: {skill_profs}")
        desc_details.append(f"**Senses**: passive Perception {10 + self.skills.perception.value}")

        # resists
        resists = str(self.resistances)
        if resists:
            desc_details.append(resists)

        embed.description = "\n".join(desc_details)

        # attacks
        atk_str = "\n".join(
            atk.build_str(self) for atk in sorted(self.attacks.no_activation_types, key=lambda atk: atk.name)
        )
        if len(atk_str) > 1000:
            atk_str = f"{atk_str[:1000]}\n[...]"
        if atk_str:
            embed.add_field(name="Attacks", value=atk_str)

        # Coins
        embed.add_field(name="Currency", value=str(self.coinpurse))

        # sheet url?
        if self._import_version < SHEET_VERSION:
            embed.set_footer(
                text=(
                    f"You are using an old sheet version ({self.sheet_type} v{self._import_version}). "
                    "Please run !update."
                )
            )

        return embed

    def is_active_global(self):
        """Returns if a character is active globally."""
        return self._active

    def is_active_server(self, ctx):
        """Returns if a character is active on the contextual server."""
        if ctx.guild is not None:
            return str(ctx.guild.id) in self._active_guilds
        return False

    def is_active_channel(self, ctx):
        """Returns if a character is active on the contextual channel."""
        if ctx.channel is not None:
            return str(ctx.channel.id) in self._active_channels
        return False

    def get_sheet_url(self):
        """
        Returns the sheet URL this character lives at, or None if the sheet url could not be created (possible for
        really old characters).
        """
        base_urls = {
            "beyond": "https://ddb.ac/characters/",
            "dicecloud": "https://v1.dicecloud.com/character/",
            "google": "https://docs.google.com/spreadsheets/d/",
            "dicecloudv2": "https://dicecloud.com/character/",
        }
        if self.sheet_type in base_urls:
            return f"{base_urls[self.sheet_type]}{self.upstream_id}"
        return None


class CharacterSpellbook(HasIntegrationMixin, Spellbook):
    """A subclass of spellbook to support live integrations."""

    def set_slots(self, *args, **kwargs):
        super().set_slots(*args, **kwargs)
        if self._live_integration:
            self._live_integration.sync_slots()


SetActiveResult = namedtuple("SetActiveResult", ["did_unset_active_location", "message"])

INTEGRATION_MAP = {"dicecloud": DicecloudIntegration, "beyond": DDBSheetSync}
DESERIALIZE_MAP = {
    **_DESER,
    "spellbook": CharacterSpellbook,
    "actions": Actions,
    "options_v2": CharacterSettings,
    "coinpurse": Coinpurse,
}
