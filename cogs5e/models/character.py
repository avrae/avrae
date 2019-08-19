import asyncio
import logging
import random

from cogs5e.funcs.dice import roll
from cogs5e.funcs.scripting import MathEvaluator, ScriptingEvaluator
from cogs5e.models.dicecloud.integration import DicecloudIntegration
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import CounterOutOfBounds, InvalidArgument, InvalidSpellLevel, NoCharacter, NoReset
from cogs5e.models.sheet import Attack, BaseStats, CharOptions, CustomCounter, DeathSaves, Levels, ManualOverrides, \
    Resistances, Saves, Skills, Spellbook, SpellbookSpell, Spellcaster
from utils.constants import STAT_NAMES
from utils.functions import search_and_select

log = logging.getLogger(__name__)

INTEGRATION_MAP = {"dicecloud": DicecloudIntegration}


class Character(Spellcaster):
    def __init__(self, owner: str, upstream: str, active: bool, sheet_type: str, import_version: int,
                 name: str, description: str, image: str, stats: dict, levels: dict, attacks: list, skills: dict,
                 resistances: dict, saves: dict, ac: int, max_hp: int, hp: int, temp_hp: int, cvars: dict,
                 options: dict, overrides: dict, consumables: list, death_saves: dict, spellbook: dict, live,
                 race: str, background: str, **kwargs):
        if kwargs:
            log.warning(f"Unused kwargs: {kwargs}")
        # sheet metadata
        self._owner = owner
        self._upstream = upstream
        self._active = active
        self._sheet_type = sheet_type
        self._import_version = import_version

        # main character info
        self.name = name
        self._description = description
        self._image = image
        self.stats = BaseStats.from_dict(stats)
        self.levels = Levels.from_dict(levels)
        self._attacks = [Attack.from_dict(atk) for atk in attacks]
        self.skills = Skills.from_dict(skills)
        self.resistances = Resistances.from_dict(resistances)
        self.saves = Saves.from_dict(saves)

        # hp/ac
        self.ac = ac
        self.max_hp = max_hp
        self._hp = hp
        self._temp_hp = temp_hp

        # customization
        self.cvars = cvars
        self.options = CharOptions.from_dict(options)
        self.overrides = ManualOverrides.from_dict(overrides)

        # ccs
        self.consumables = [CustomCounter.from_dict(self, cons) for cons in consumables]
        self.death_saves = DeathSaves.from_dict(death_saves)

        # spellbook
        spellbook = Spellbook.from_dict(spellbook)
        super(Character, self).__init__(spellbook)

        # live sheet integrations
        self._live = live
        integration = INTEGRATION_MAP.get(live)
        if integration:
            self._live_integration = integration(self)
        else:
            self._live_integration = None

        # misc research things
        self.race = race
        self.background = background

    # ---------- Serialization ----------
    @classmethod
    def from_dict(cls, d):
        if '_id' in d:
            del d['_id']
        return cls(**d)

    def to_dict(self):
        return {
            "owner": self._owner, "upstream": self._upstream, "active": self._active, "sheet_type": self._sheet_type,
            "import_version": self._import_version, "name": self.name, "description": self._description,
            "image": self._image, "stats": self.stats.to_dict(), "levels": self.levels.to_dict(),
            "attacks": [a.to_dict() for a in self._attacks], "skills": self.skills.to_dict(),
            "resistances": self.resistances.to_dict(), "saves": self.saves.to_dict(), "ac": self.ac,
            "max_hp": self.max_hp, "hp": self._hp, "temp_hp": self._temp_hp, "cvars": self.cvars,
            "options": self.options.to_dict(), "overrides": self.overrides.to_dict(),
            "consumables": [co.to_dict() for co in self.consumables], "death_saves": self.death_saves.to_dict(),
            "spellbook": self._spellbook.to_dict(), "live": self._live, "race": self.race, "background": self.background
        }

    @classmethod
    async def from_ctx(cls, ctx):
        active_character = await ctx.bot.mdb.characters.find_one({"owner": str(ctx.author.id), "active": True})
        if active_character is None:
            raise NoCharacter()
        return cls.from_dict(active_character)

    @classmethod
    async def from_bot_and_ids(cls, bot, owner_id, character_id):
        character = await bot.mdb.characters.find_one({"owner": owner_id, "upstream": character_id})
        if character is None:
            raise NoCharacter()
        return cls.from_dict(character)

    # ---------- Basic CRUD ----------
    def get_name(self):
        return self.name

    def get_color(self):
        return self.options.get('color') or random.randint(0, 0xffffff)

    def get_resists(self):
        """
        Gets the resistances of a character.
        :return: The resistances, immunities, and vulnerabilites of a character.
        :rtype: dict
        """
        return {'resist': self.resistances.resist, 'immune': self.resistances.immune, 'vuln': self.resistances.vuln}

    def get_level(self):
        """:returns int - the character's total level."""
        return self.levels.total_level

    def get_mod(self, stat):
        """
        Gets the character's stat modifier for a core stat.
        :param stat: The core stat to get. Can be of the form "cha", or "charisma".
        :return: The character's relevant stat modifier.
        """
        return self.stats.get_mod(stat)

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
        return self.overrides.image or self._image

    # ---------- CSETTINGS ----------
    def get_setting(self, setting, default=None):
        """Gets the value of a csetting.
        :returns the csetting's value, or default."""
        return self.options.get(setting, default)

    def set_setting(self, setting, value):
        """Sets the value of a csetting."""
        self.options.set(setting, value)

    def delete_setting(self, setting):
        """Deletes a setting if it exists."""
        self.options.set(setting, None)

    # ---------- SCRIPTING ----------
    async def parse_cvars(self, cstr, ctx):
        """Parses cvars.
        :param ctx: The Context the cvar is parsed in.
        :param cstr: The string to parse.
        :returns string - the parsed string."""
        evaluator = await (await ScriptingEvaluator.new(ctx)).with_character(self)

        out = await asyncio.get_event_loop().run_in_executor(None, evaluator.parse, cstr)
        await evaluator.run_commits()

        return out

    def evaluate_math(self, varstr):
        """Evaluates a cvar expression in a MathEvaluator.
        :param varstr - the expression to evaluate.
        :returns int - the value of the expression."""
        varstr = str(varstr).strip('<>{}')
        evaluator = MathEvaluator.with_character(self)

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
        if no_cvars:
            out = {}
        else:
            out = self.cvars.copy()
        if self.spellbook.sab is not None:
            spell_mod = self.spellbook.sab - self.stats.prof_bonus
        else:
            spell_mod = None
        out.update({
            "name": self.name, "armor": self.ac, "description": self.description, "hp": self.max_hp,
            "image": self.image, "level": self.levels.total_level, "proficiencyBonus": self.stats.prof_bonus,
            "spell": spell_mod, "color": hex(self.get_color())[2:]
        })
        for cls, lvl in self.levels:
            out[f"{cls}Level"] = lvl
        for stat in STAT_NAMES:
            out[stat] = self.stats[stat]
            out[f"{stat}Mod"] = self.stats.get_mod(stat)
            out[f"{stat}Save"] = self.saves.get(stat).value
        return out

    # ---------- DATABASE ----------
    async def commit(self, ctx):
        """Writes a character object to the database, under the contextual author."""
        data = self.to_dict()
        await ctx.bot.mdb.characters.update_one(
            {"owner": self._owner, "upstream": self._upstream},
            {"$set": data},
            upsert=True
        )

    async def set_active(self, ctx):
        """Sets the character as active."""
        await ctx.bot.mdb.characters.update_many(
            {"owner": str(ctx.author.id), "active": True},
            {"$set": {"active": False}}
        )
        await ctx.bot.mdb.characters.update_one(
            {"owner": str(ctx.author.id), "upstream": self._upstream},
            {"$set": {"active": True}}
        )

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

    def get_hp_str(self):
        out = f"{self.hp}/{self.max_hp}"
        if self.temp_hp:
            out += f' (+{self.temp_hp} temp)'
        return out

    def modify_hp(self, value, ignore_temp=False, overflow=True):
        """Modifies the character's hit points. If ignore_temp is True, will deal damage to raw HP, ignoring temp."""
        if value < 0 and not ignore_temp:
            thp = self.temp_hp
            self.temp_hp += value
            value += min(thp, -value)  # how much did the THP absorb?
        if overflow:
            self.hp = self._hp + value
        else:
            self.hp = min(self._hp + value, self.max_hp)

    def reset_hp(self):
        """Resets the character's HP to max and THP to 0."""
        self.temp_hp = 0
        self.hp = self.max_hp

    @property
    def temp_hp(self):
        return self._temp_hp

    @temp_hp.setter
    def temp_hp(self, value):
        self._temp_hp = max(0, value)  # 0 ≤ temp_hp

    # ---------- SPELLBOOK ----------
    def get_remaining_slots_str(self, level: int = None):
        """:param level: The level of spell slot to return.
        :returns A string representing the character's remaining spell slots."""
        out = ''
        if level:
            assert 0 < level < 10
            _max = self.spellbook.get_max_slots(level)
            remaining = self.spellbook.get_slots(level)
            numEmpty = _max - remaining
            filled = '\u25c9' * remaining
            empty = '\u3007' * numEmpty
            out += f"`{level}` {filled}{empty}\n"
        else:
            for level in range(1, 10):
                _max = self.spellbook.get_max_slots(level)
                remaining = self.spellbook.get_slots(level)
                if _max:
                    numEmpty = _max - remaining
                    filled = '\u25c9' * remaining
                    empty = '\u3007' * numEmpty
                    out += f"`{level}` {filled}{empty}\n"
        if not out:
            out = "No spell slots."
        return out.strip()

    def set_remaining_slots(self, level: int, value: int):
        """Sets the character's remaining spell slots of level level.
        :param level - The spell level.
        :param value - The number of remaining spell slots."""
        if not 0 < level < 10:
            raise InvalidSpellLevel()
        if not 0 <= value <= self.spellbook.get_max_slots(level):
            raise CounterOutOfBounds()

        self.spellbook.set_slots(level, value)

        if self._live_integration:
            self._live_integration.sync_slots()

    def use_slot(self, level: int):
        """Uses one spell slot of level level.
        :raises CounterOutOfBounds if there are no remaining slots of the requested level."""
        if level == 0:
            return
        if not 0 < level < 10:
            raise InvalidSpellLevel()

        val = self.spellbook.get_slots(level) - 1
        if val < 0:
            raise CounterOutOfBounds("You do not have any spell slots of this level remaining.")

        self.set_remaining_slots(level, val)

    def reset_spellslots(self):
        """Resets all spellslots to their max value.
        :returns self"""
        self.spellbook.reset_slots()
        if self._live_integration:
            self._live_integration.sync_slots()

    def can_cast(self, spell, level) -> bool:
        return self.spellbook.get_slots(level) > 0 and spell.name in self.spellbook

    def cast(self, spell, level):
        self.use_slot(level)

    def remaining_casts_of(self, spell, level):
        return self.get_remaining_slots_str(level)

    def add_known_spell(self, spell):
        """Adds a spell to the character's known spell list.
        :param spell (Spell) - the Spell.
        :returns self"""
        if spell.name in self.spellbook:
            raise InvalidArgument("You already know this spell.")
        sbs = SpellbookSpell.from_spell(spell)
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

    def sync_consumable(self, ctr):
        if self._live_integration:
            self._live_integration.sync_consumable(ctr)

    def _reset_custom(self, scope):
        """Resets custom counters with given scope."""
        reset = []
        for ctr in self.consumables:
            if ctr.reset_on == scope:
                try:
                    ctr.reset()
                except NoReset:
                    continue
                reset.append(ctr.name)
        return reset

    # ---------- RESTING ----------
    def on_hp(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self._reset_custom('hp'))
        if self.hp > 0:
            self.death_saves.reset()
            reset.append("Death Saves")
        return reset

    def short_rest(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp())
        reset.extend(self._reset_custom('short'))
        if self.get_setting('srslots', False):
            self.reset_spellslots()
            reset.append("Spell Slots")
        return reset

    def long_rest(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp())
        reset.extend(self.short_rest())
        reset.extend(self._reset_custom('long'))
        self.reset_hp()
        reset.append("HP")
        if not self.get_setting('srslots', False):
            self.reset_spellslots()
            reset.append("Spell Slots")
        return reset

    def reset_all_consumables(self):
        """Resets all applicable consumables.
        Returns a list of the names of all reset counters."""
        reset = []
        reset.extend(self.on_hp())
        reset.extend(self.short_rest())
        reset.extend(self.long_rest())
        reset.extend(self._reset_custom(None))
        return reset

    # ---------- MISC ----------
    def update(self, old_character):
        """
        Updates certain attributes to match an old character's.
        Currently updates settings, overrides, cvars, consumables, overriden spellbook spells,
        hp, temp hp, death saves, used spell slots
        :type old_character Character
        """
        self.options = old_character.options
        self.overrides = old_character.overrides
        self.cvars = old_character.cvars

        existing_cons_names = set(con.name.lower() for con in self.consumables)
        self.consumables.extend(con for con in old_character.consumables if con.name.lower() not in existing_cons_names)

        self.spellbook.spells.extend(self.overrides.spells)
        self._hp = old_character._hp
        self._temp_hp = old_character._temp_hp
        self.spellbook.slots = old_character.spellbook.slots

    def get_sheet_embed(self):
        embed = EmbedWithCharacter(self)
        desc_details = []

        # race/class (e.g. Tiefling Bard/Warlock)
        classes = '/'.join(f"{cls} {lvl}" for cls, lvl in self.levels)
        desc_details.append(f"{self.race} {classes}")

        # prof bonus
        desc_details.append(f"**Proficiency Bonus**: {self.stats.prof_bonus:+}")

        # combat details
        desc_details.append(f"**AC**: {self.ac}")
        desc_details.append(f"**HP**: {self.get_hp_str()}")
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
        atks = self.attacks
        atk_str = ""
        for attack in atks:
            a = f"{str(attack)}\n"
            if len(atk_str) + len(a) > 1000:
                atk_str += "[...]"
                break
            atk_str += a
        atk_str = atk_str.strip()
        if atk_str:
            embed.add_field(name="Attacks", value=atk_str)

        # sheet url?
        if self._import_version < 15:
            embed.set_footer(text=f"You are using an old sheet version ({self.sheet_type} v{self._import_version}). "
                                  f"Please run !update.")

        return embed
