import logging

import cachetools

import aliasing.evaluators
from cogs5e.models.dicecloud.integration import DicecloudIntegration
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import ExternalImportError, InvalidArgument, NoCharacter, NoReset
from cogs5e.models.sheet.action import Actions
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.player import CharOptions, CustomCounter, DeathSaves, ManualOverrides
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP as _DESER, StatBlock
from cogs5e.sheets.abc import SHEET_VERSION
from utils.functions import search_and_select

log = logging.getLogger(__name__)


# constants at bottom (yay execution order)

class Character(StatBlock):
    # cache characters for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Character.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Character state
    # caches based on (owner, upstream)
    _cache = cachetools.TTLCache(maxsize=50, ttl=5)

    def __init__(self, owner: str, upstream: str, active: bool, sheet_type: str, import_version: int,
                 name: str, description: str, image: str, stats: BaseStats, levels: Levels, attacks: AttackList,
                 skills: Skills, resistances: Resistances, saves: Saves, ac: int, max_hp: int, hp: int, temp_hp: int,
                 cvars: dict, options: dict, overrides: dict, consumables: list, death_saves: dict,
                 spellbook: Spellbook,
                 live, race: str, background: str, creature_type: str = None,
                 ddb_campaign_id: str = None, actions: Actions = None, active_guilds: list = None,
                 **kwargs):
        if kwargs:
            log.warning(f"Unused kwargs: {kwargs}")
        if actions is None:
            actions = Actions()
        if active_guilds is None:
            active_guilds = []
        # sheet metadata
        self._owner = owner
        self._upstream = upstream
        self._active = active
        self._active_guilds = active_guilds
        self._sheet_type = sheet_type
        self._import_version = import_version

        # StatBlock super call
        super().__init__(
            name=name, stats=stats, levels=levels, attacks=attacks, skills=skills, saves=saves, resistances=resistances,
            spellbook=spellbook,
            ac=ac, max_hp=max_hp, hp=hp, temp_hp=temp_hp, creature_type=creature_type
        )

        # main character info
        self._description = description
        self._image = image

        # customization
        self.cvars = cvars
        self.options = CharOptions.from_dict(options)
        self.overrides = ManualOverrides.from_dict(overrides)

        # ccs
        self.consumables = [CustomCounter.from_dict(self, cons) for cons in consumables]
        self.death_saves = DeathSaves.from_dict(death_saves)

        # live sheet resource integrations
        self._live = live
        integration = INTEGRATION_MAP.get(live)
        if integration:
            self._live_integration = integration(self)
        else:
            self._live_integration = None

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
        if '_id' in d:
            del d['_id']
        for key, klass in DESERIALIZE_MAP.items():
            if key in d:
                d[key] = klass.from_dict(d[key])
        inst = cls(**d)
        inst._spellbook._live_integration = inst._live_integration
        return inst

    @classmethod
    async def from_ctx(cls, ctx, ignoreGuild: bool = False):
        owner_id = str(ctx.author.id)
        active_character = None
        if ctx.guild and not ignoreGuild:
            guild_id = str(ctx.guild.id)
            active_character = await ctx.bot.mdb.characters.find_one({"owner": owner_id, "active_guilds": guild_id})
        if active_character is None:
            active_character = await ctx.bot.mdb.characters.find_one({"owner": owner_id, "active": True})
        if active_character is None:
            raise NoCharacter()

        try:
            # return from cache if available
            return cls._cache[owner_id, active_character['upstream']]
        except KeyError:
            # otherwise deserialize and write to cache
            inst = cls.from_dict(active_character)
            cls._cache[owner_id, active_character['upstream']] = inst
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
            "owner": self._owner, "upstream": self._upstream, "active": self._active,
            "sheet_type": self._sheet_type, "import_version": self._import_version, "description": self._description,
            "image": self._image, "cvars": self.cvars, "options": self.options.to_dict(),
            "overrides": self.overrides.to_dict(), "consumables": [co.to_dict() for co in self.consumables],
            "death_saves": self.death_saves.to_dict(), "live": self._live, "race": self.race,
            "background": self.background, "ddb_campaign_id": self.ddb_campaign_id, "actions": self.actions.to_dict(),
            "active_guilds": self._active_guilds
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
    def get_color(self):
        return self.options.get('color') or super().get_color()

    @property
    def owner(self):
        return self._owner

    @owner.setter
    def owner(self, value: str):
        self._owner = value
        self._active = False  # don't have any conflicts

    @property
    def upstream(self):
        return self._upstream

    @property
    def upstream_id(self):
        return self._upstream.split('-', 1)[-1]

    @property
    def sheet_type(self):
        return self._sheet_type

    @property
    def attacks(self):
        return self._attacks + self.overrides.attacks

    @property
    def description(self):
        return self.overrides.desc or self._description

    @property
    def image(self):
        return self.overrides.image or self._image or ''

    # ---------- CSETTINGS ----------
    def get_setting(self, setting, default=None):
        """Gets the value of a csetting.
        :returns the csetting's value, or default."""
        setting = self.options.get(setting)
        if setting is None:
            return default
        return setting

    def set_setting(self, setting, value):
        """Sets the value of a csetting."""
        self.options.set(setting, value)

    def delete_setting(self, setting):
        """Deletes a setting if it exists."""
        self.options.set(setting, None)

    # ---------- SCRIPTING ----------
    def evaluate_math(self, varstr):
        """Evaluates a cvar expression in a MathEvaluator.
        :param varstr - the expression to evaluate.
        :returns int - the value of the expression."""
        varstr = str(varstr).strip('<>{}')
        evaluator = aliasing.evaluators.MathEvaluator.with_character(self)

        try:
            return int(evaluator.eval(varstr))
        except Exception as e:
            raise InvalidArgument(f"Cannot evaluate {varstr}: {e}")

    def set_cvar(self, name: str, val: str):
        """Sets a cvar to a string value."""
        if not name.isidentifier():
            raise InvalidArgument("Cvar name must be a valid identifier "
                                  "(contains only a-z, A-Z, 0-9, and _, and not start with a number).")
        self.cvars[name] = str(val)

    def get_scope_locals(self, no_cvars=False):
        out = super().get_scope_locals()
        if not no_cvars:
            out.update(self.cvars.copy())
        out.update({
            "description": self.description, "image": self.image, "color": hex(self.get_color())[2:]
        })
        return out

    # ---------- DATABASE ----------
    async def commit(self, ctx):
        """Writes a character object to the database, under the contextual author."""
        data = self.to_dict()
        data.pop('active')  # #1472 - may regress when doing atomic commits, be careful
        data.pop('active_guilds')
        try:
            await ctx.bot.mdb.characters.update_one(
                {"owner": self._owner, "upstream": self._upstream},
                {
                    "$set": data,
                    "$setOnInsert": {'active': self._active,'active_guilds': self._active_guilds}  # also #1472
                },
                upsert=True
            )
        except OverflowError:
            raise ExternalImportError("A number on the character sheet is too large to store.")

    async def set_active(self, ctx):
        """Sets the character as active and removes the active character from the current server if possible."""
        self._active = True
        if ctx.guild:
            guild_id = str(ctx.guild.id)
            await ctx.bot.mdb.characters.update_many(
                {"owner": str(ctx.author.id), "active_guilds": guild_id},
                {"$pull": {"active_guilds": guild_id}}
            )
        await ctx.bot.mdb.characters.update_many(
            {"owner": str(ctx.author.id), "active": True},
            {"$set": {"active": False}}
        )
        await ctx.bot.mdb.characters.update_one(
            {"owner": str(ctx.author.id), "upstream": self._upstream},
            {"$set": {"active": True}}
        )
    
    async def set_server_active(self, ctx):
        """Sets the active character on the current server. Raises NoPrivateMessage() if not in a server."""
        if ctx.guild is None:
            raise NoPrivateMessage()
        guild_id = str(ctx.guild.id)
        await ctx.bot.mdb.characters.update_many(
            {"owner": str(ctx.author.id), "active_guilds": guild_id},
            {"$pull": {"active_guilds": guild_id}}
        )
        await ctx.bot.mdb.characters.update_one(
            {"owner": str(ctx.author.id), "upstream": self._upstream},
            {"$push": {"active_guilds": guild_id}}
        )
        self._active_guilds.append(guild_id)
            
    async def unset_server_active(self, ctx):
        """Unsets the active character on the current server. Raises NoPrivateMessage() if not in a server."""
        if ctx.guild is None:
            raise NoPrivateMessage()
        guild_id = str(ctx.guild.id)
        await ctx.bot.mdb.characters.update_many(
            {"owner": str(ctx.author.id), "active_guilds": guild_id},
            {"$pull": {"active_guilds": guild_id}}
        )
        if guild_id in self._active_guilds:
            self._active_guilds.remove(guild_id)


    # ---------- HP ----------
    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, value):
        self._hp = max(0, value)
        self.on_hp()

        if self._live_integration:
            self._live_integration.sync_hp()

    # ---------- SPELLBOOK ----------
    def add_known_spell(self, spell, dc: int = None, sab: int = None, mod: int = None):
        """Adds a spell to the character's known spell list."""
        if spell.name in self.spellbook:
            raise InvalidArgument("You already know this spell.")
        sbs = SpellbookSpell.from_spell(spell, dc, sab, mod)
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
        reset.extend(self._reset_custom('hp'))
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
        reset.extend(self._reset_custom('short'))
        if self.get_setting('srslots', False):
            self.spellbook.reset_slots()
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
        reset.extend(self._reset_custom('long'))
        self.reset_hp()
        if not self.get_setting('srslots', False):
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
    def update(self, old_character):
        """
        Updates certain attributes to match an old character's.
        Currently updates settings, overrides, cvars, consumables, overriden spellbook spells,
        hp, temp hp, death saves, used spell slots
        and caches the new character.
        :type old_character Character
        """
        # top level things
        self.options = old_character.options
        self.overrides = old_character.overrides
        self.cvars = old_character.cvars

        # consumables: no duplicate name or live (upstream) ids
        new_cc_names = set(con.name.lower() for con in self.consumables)
        new_cc_upstreams = set(con.live_id for con in self.consumables if con.live_id is not None)
        self.consumables.extend(
            con for con in old_character.consumables
            if con.name.lower() not in new_cc_names
            and con.live_id not in new_cc_upstreams
        )

        # overridden spells
        self.spellbook.spells.extend(self.overrides.spells)

        # tracking
        self._hp = old_character._hp
        self._temp_hp = old_character._temp_hp
        # ensure new slots are within bounds (#1453)
        self.spellbook.slots = {l: min(v, self.spellbook.get_max_slots(l))
                                for l, v in old_character.spellbook.slots.items()}

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

        embed.description = '\n'.join(desc_details)

        # attacks
        atk_str = self.attacks.build_str(self)
        if len(atk_str) > 1000:
            atk_str = f"{atk_str[:1000]}\n[...]"
        if atk_str:
            embed.add_field(name="Attacks", value=atk_str)

        # sheet url?
        if self._import_version < SHEET_VERSION:
            embed.set_footer(text=f"You are using an old sheet version ({self.sheet_type} v{self._import_version}). "
                                  f"Please run !update.")

        return embed
    
    def active_embed(self):
        """Creates an embed to be displayed when the active character is checked"""
        embed = EmbedWithCharacter(self)
        embed.title = self.name
        urls = {"beyond": "https://ddb.ac/characters/",
                "dicecloud": "https://dicecloud.com/character/",
                "google": "https://docs.google.com/spreadsheets/d/"}
        sheeturl = urls[self.sheet_type] + self.upstream_id
        desc = f"Your current active character is {active_character.name}. " \
                "All of your checks, saves and actions will use this character's stats.\n" \
                "This character is active in " + \
                (", ".join(["GLOBAL" if self.is_active_global()] +
                           ["SERVER" if self.is_active_server(ctx)])) + "\n" \
                f"[Go to Character Sheet]({sheeturl})."
        embed.description = desc
        return embed
    
    def is_active_global(self):
        """Returns if a character is active globally."""
        return self._active
    
    def is_active_server(self, ctx):
        """Returns if a character is active on the current server."""
        if ctx.guild:
            guild_id=str(ctx.guild.id)
            return guild_id in self._active_guilds
        return False


class CharacterSpellbook(Spellbook):
    """A subclass of spellbook to support live integrations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._live_integration = None

    def set_slots(self, level: int, value: int):
        super().set_slots(level, value)
        if self._live_integration:
            self._live_integration.sync_slots()


INTEGRATION_MAP = {"dicecloud": DicecloudIntegration}
DESERIALIZE_MAP = {**_DESER, "spellbook": CharacterSpellbook, "actions": Actions}
