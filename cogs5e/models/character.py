import asyncio
import logging
import random
import re

import discord

from cogs5e.funcs.dice import roll
from cogs5e.funcs.scripting import ScriptingEvaluator
from cogs5e.models.dicecloud.integration import DicecloudIntegration
from cogs5e.models.errors import CounterOutOfBounds, InvalidArgument, InvalidSpellLevel, NoCharacter, NoReset
from cogs5e.models.sheet import Attack, BaseStats, Levels, Resistances, Saves, Skills, Spellbook, SpellbookSpell, \
    Spellcaster
from utils.functions import search_and_select

log = logging.getLogger(__name__)

SKILL_MAP = {'acrobatics': 'dexterity', 'animalHandling': 'wisdom', 'arcana': 'intelligence', 'athletics': 'strength',
             'deception': 'charisma', 'history': 'intelligence', 'initiative': 'dexterity', 'insight': 'wisdom',
             'intimidation': 'charisma', 'investigation': 'intelligence', 'medicine': 'wisdom',
             'nature': 'intelligence', 'perception': 'wisdom', 'performance': 'charisma',
             'persuasion': 'charisma', 'religion': 'intelligence', 'sleightOfHand': 'dexterity', 'stealth': 'dexterity',
             'survival': 'wisdom', 'strengthSave': 'strength', 'dexteritySave': 'dexterity',
             'constitutionSave': 'constitution', 'intelligenceSave': 'intelligence', 'wisdomSave': 'wisdom',
             'charismaSave': 'charisma',
             'strength': 'strength', 'dexterity': 'dexterity', 'constitution': 'constitution',
             'intelligence': 'intelligence', 'wisdom': 'wisdom', 'charisma': 'charisma'}
INTEGRATION_MAP = {"dicecloud": DicecloudIntegration}


class CharOptions:
    def __init__(self, options):
        self.options = options

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"options": self.options}

    # ---------- main funcs ----------
    def get(self, option, default=None):
        return self.options.get(option, default)

    def set(self, option, value):
        self.options[option] = value


class ManualOverrides:
    def __init__(self, desc=None, image=None, attacks=None, spells=None):
        if attacks is None:
            attacks = []
        if spells is None:
            spells = []
        self.desc = desc
        self.image = image
        self.attacks = attacks
        self.spells = spells

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"desc": self.desc, "image": self.image, "attacks": self.attacks, "spells": self.spells}


class DeathSaves:
    def __init__(self, successes, fails):
        self.successes = successes
        self.fails = fails

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"successes": self.successes, "fails": self.fails}

    # ---------- main funcs ----------
    def succeed(self, num=1):
        self.successes = min(3, self.successes + num)

    def fail(self, num=1):
        self.fails = min(3, self.fails + num)

    def is_stable(self):
        return self.successes == 3

    def is_dead(self):
        return self.fails == 3

    def reset(self):
        self.successes = 0
        self.fails = 0

    def __str__(self):
        successes = '\u25c9' * self.successes + '\u3007' * (3 - self.successes)
        fails = '\u3007' * (3 - self.fails) + '\u25c9' * self.fails
        return f"F {fails} | {successes} S"


class CustomCounter:
    def __init__(self, character, name, value, minv=None, maxv=None, reset=None, display_type=None, live_id=None):
        self._character = character
        self.name = name
        self.value = value
        self.min = minv
        self.max = maxv
        self.reset_on = reset
        self.display_type = display_type
        self.live_id = live_id

        # cached values
        self._max = None
        self._min = None

    @classmethod
    def from_dict(cls, char, d):
        return cls(char, **d)

    def to_dict(self):
        return {"name": self.name, "value": self.value, "minv": self.min, "maxv": self.max, "reset": self.reset_on,
                "display_type": self.display_type, "live_id": self.live_id}

    @classmethod
    def new(cls, character, name, minv=None, maxv=None, reset=None, display_type=None, live_id=None):
        if reset not in ('short', 'long', 'none', None):
            raise InvalidArgument("Invalid reset.")
        if any(c in name for c in ".$"):
            raise InvalidArgument("Invalid character in CC name.")
        if minv is not None and maxv is not None:
            max_value = character.evaluate_cvar(maxv)
            if max_value < character.evaluate_cvar(minv):
                raise InvalidArgument("Max value is less than min value.")
            if max_value == 0:
                raise InvalidArgument("Max value cannot be 0.")
        if reset and maxv is None:
            raise InvalidArgument("Reset passed but no maximum passed.")
        if display_type == 'bubble' and (maxv is None or minv is None):
            raise InvalidArgument("Bubble display requires a max and min value.")

        value = character.evaluate_cvar(maxv) or 0
        return cls(character, name, value, minv, maxv, reset, display_type, live_id)

    # ---------- main funcs ----------
    def get_min(self):
        if self._min is None:
            self._min = self._character.evaluate_cvar(self.min) or -(2 ** 32)
        return self._min

    def get_max(self):
        if self._max is None:
            self._max = self._character.evaluate_cvar(self.max) or 2 ** 32
        return self._max

    def set(self, new_value: int, strict=False):
        minv = self.get_min()
        maxv = self.get_max()

        if strict and not minv <= new_value <= maxv:
            raise CounterOutOfBounds()

        new_value = min(max(minv, new_value), maxv)
        self.value = new_value

        if self.live_id:
            self._character.sync_consumable(self)

    def reset(self):
        if self.reset_on == 'none' or self.max is None:
            raise NoReset()
        self.set(self.get_max())


class Character(Spellcaster):
    def __init__(self, owner: str, upstream: str, active: bool, sheet_type: str, import_version: int,
                 name: str, description: str, image: str, stats: dict, levels: dict, attacks: list, skills: dict,
                 resistances: dict, saves: dict, ac: int, max_hp: int, hp: int, temp_hp: int, cvars: dict,
                 options: dict, overrides: dict, consumables: list, death_saves: dict, spellbook: dict, live: str,
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
        self.description = description
        self.image = image
        self.stats = BaseStats.from_dict(stats)
        self.levels = Levels.from_dict(levels)
        self.attacks = [Attack.from_dict(atk) for atk in attacks]
        self.skills = Skills.from_dict(skills)
        self.resistances = Resistances.from_dict(resistances)
        self.saves = Saves.from_dict(saves)

        # hp/ac
        self.ac = ac
        self.max_hp = max_hp
        self.hp = hp
        self.temp_hp = temp_hp

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
    def from_dict(cls, d):  # TODO
        return cls(**d)

    def to_dict(self):  # TODO
        pass

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

    def get_image(self):
        return self.image

    def get_color(self):
        return self.options.get('color', random.randint(0, 0xffffff))

    def get_ac(self):
        return self.ac

    def get_resists(self):
        """
        Gets the resistances of a character.
        :return: The resistances, immunities, and vulnerabilites of a character.
        :rtype: dict
        """
        return {'resist': self.resistances.resist, 'immune': self.resistances.immune, 'vuln': self.resistances.vuln}

    def get_max_hp(self):
        return self.max_hp

    def get_level(self):
        """:returns int - the character's total level."""
        return self.levels.total_level

    def get_prof_bonus(self):
        """:returns int - the character's proficiency bonus."""
        return self.stats.prof_bonus

    def get_mod(self, stat):
        """
        Gets the character's stat modifier for a core stat.
        :param stat: The core stat to get. Can be of the form "cha", or "charisma".
        :return: The character's relevant stat modifier.
        """
        return self.stats.get_mod(stat)

    def get_saves(self):
        """:returns dict - the character's saves and modifiers."""
        return self.saves

    def get_skills(self):
        """:returns dict - the character's skills and modifiers."""
        return self.skills

    def get_attacks(self):
        """
        :returns the character's list of attacks.
        :rtype list[Attack]
        """
        return self.attacks + self.overrides.attacks

    # ---------- CSETTINGS ----------
    def get_setting(self, setting, default=None):
        """Gets the value of a csetting.
        :returns the csetting's value, or default."""
        return self.options.get(setting, default)

    def set_setting(self, setting, value):
        """Sets the value of a csetting."""
        self.options.set(setting, value)

    # ---------- SCRIPTING ---------- TODO
    async def parse_cvars(self, cstr, ctx):
        """Parses cvars.
        :param ctx: The Context the cvar is parsed in.
        :param cstr: The string to parse.
        :returns string - the parsed string."""
        evaluator = await (await ScriptingEvaluator.new(ctx)).with_character(self)

        out = await asyncio.get_event_loop().run_in_executor(None, evaluator.parse, cstr)
        await evaluator.run_commits()

        return out

    def evaluate_cvar(self, varstr):
        """Evaluates a cvar expression.
        :param varstr - the expression to evaluate.
        :returns int - the value of the expression, or 0 if evaluation failed."""
        ops = r"([-+*/().<>=])"
        varstr = str(varstr).strip('<>{}')

        cvars = self.character.get('cvars', {})
        stat_vars = self.character.get('stat_cvars', {})
        stat_vars['spell'] = self.get_spell_ab() - self.get_prof_bonus()
        out = ""
        tempout = ''
        for substr in re.split(ops, varstr):
            temp = substr.strip()
            tempout += str(cvars.get(temp, temp)) + " "
        for substr in re.split(ops, tempout):
            temp = substr.strip()
            out += str(stat_vars.get(temp, temp)) + " "
        return roll(out).total

    def get_cvar(self, name):
        return self.cvars.get(name)

    def set_cvar(self, name, val: str):
        """Sets a cvar to a string value."""
        if any(c in name for c in '/()[]\\.^$*+?|{}'):
            raise InvalidArgument("Cvar contains invalid character.")
        self.cvars[name] = str(val)

    def get_cvars(self):
        return self.cvars

    def get_stat_vars(self):
        return self.character.get('stat_cvars', {})

    # ---------- DATABASE ---------- TODO
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
    def get_current_hp(self):
        """Returns the integer value of the remaining HP."""
        return self.hp

    def get_hp_str(self):
        hp = self.get_current_hp()
        out = f"{hp}/{self.get_max_hp()}"
        if self.get_temp_hp():
            out += f' ({self.get_temp_hp()} temp)'
        return out

    def set_hp(self, newValue):
        """Sets the character's hit points. Doesn't touch THP."""
        self.hp = newValue
        self.on_hp()

        if self._live_integration:
            self._live_integration.sync_hp()

    def modify_hp(self, value, ignore_temp=False):
        """Modifies the character's hit points. If ignore_temp is True, will deal damage to raw HP, ignoring temp."""
        if value < 0 and not ignore_temp:
            thp = self.temp_hp
            self.set_temp_hp(self.temp_hp + value)
            value += min(thp, -value)  # how much did the THP absorb?
        self.hp += value

        if self._live_integration:
            self._live_integration.sync_hp()

    def reset_hp(self):
        """Resets the character's HP to max and THP to 0."""
        self.set_temp_hp(0)
        self.set_hp(self.get_max_hp())

    def get_temp_hp(self):
        return self.temp_hp

    def set_temp_hp(self, temp_hp):
        self.temp_hp = max(0, temp_hp)  # 0 ≤ temp_hp

    # ---------- DEATH SAVES ----------
    def add_successful_ds(self):
        """Adds a successful death save to the character.
        Returns True if the character is stable."""
        self.death_saves.succeed()
        return self.death_saves.is_stable()

    def add_failed_ds(self):
        """Adds a failed death save to the character.
        Returns True if the character is dead."""
        self.death_saves.fail()
        return self.death_saves.is_dead()

    def reset_death_saves(self):
        """Resets successful and failed death saves to 0."""
        self.death_saves.reset()

    # ---------- SPELLBOOK ----------
    def get_spell_list(self):
        """:returns list - a list of the names of all spells the character can cast. """
        return [s.name for s in self.spellbook.spells]

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
        return out

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
        if not 0 < level < 10:
            raise InvalidSpellLevel()
        if level == 0:
            return

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
        sbs = SpellbookSpell.from_spell(spell)
        self.spellbook.spells.append(sbs)
        self.overrides.spells.append(sbs)

    def remove_known_spell(self, sb_spell):
        """
        Removes a spell from the character's spellbook override.
        :param sb_spell: The spell to remove.
        :type sb_spell SpellbookSpell
        """
        self.overrides.spells.remove(sb_spell)
        self.spellbook.spells.remove(sb_spell)

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
        if self.get_current_hp() > 0:
            self.reset_death_saves()
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

    # ---------- MISC ---------- TODO
    def get_sheet_embed(self):
        stats = self.get_stats()
        hp = self.get_max_hp()
        skills = self.get_skills()
        attacks = self.get_attacks()
        saves = self.get_saves()
        skill_effects = self.get_skill_effects()

        resists = self.get_resists()
        resist = resists['resist']
        immune = resists['immune']
        vuln = resists['vuln']
        resistStr = ''
        if len(resist) > 0:
            resistStr += "\nResistances: " + ', '.join(resist).title()
        if len(immune) > 0:
            resistStr += "\nImmunities: " + ', '.join(immune).title()
        if len(vuln) > 0:
            resistStr += "\nVulnerabilities: " + ', '.join(vuln).title()

        embed = discord.Embed()
        embed.colour = self.get_color()
        embed.title = self.get_name()
        embed.set_thumbnail(url=self.get_image())

        embed.add_field(name="HP/Level", value=f"**HP:** {hp}\nLevel {self.get_level()}{resistStr}")
        embed.add_field(name="AC", value=str(self.get_ac()))

        embed.add_field(name="Stats", value="**STR:** {strength} ({strengthMod:+})\n" \
                                            "**DEX:** {dexterity} ({dexterityMod:+})\n" \
                                            "**CON:** {constitution} ({constitutionMod:+})\n" \
                                            "**INT:** {intelligence} ({intelligenceMod:+})\n" \
                                            "**WIS:** {wisdom} ({wisdomMod:+})\n" \
                                            "**CHA:** {charisma} ({charismaMod:+})".format(**stats))

        savesStr = ''
        for save in ('strengthSave', 'dexteritySave', 'constitutionSave', 'intelligenceSave', 'wisdomSave',
                     'charismaSave'):
            if skill_effects.get(save):
                skill_effect = f"({skill_effects.get(save)})"
            else:
                skill_effect = ''
            savesStr += '**{}**: {:+} {}\n'.format(save[:3].upper(), saves.get(save), skill_effect)

        embed.add_field(name="Saves", value=savesStr)

        def cc_to_normal(string):
            return re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', string)

        skillsStr = ''
        for skill, mod in sorted(skills.items()):
            if 'Save' not in skill:
                if skill_effects.get(skill):
                    skill_effect = f"({skill_effects.get(skill)})"
                else:
                    skill_effect = ''
                skillsStr += '**{}**: {:+} {}\n'.format(cc_to_normal(skill), mod, skill_effect)

        embed.add_field(name="Skills", value=skillsStr.title())

        tempAttacks = []
        for a in attacks:
            damage = a['damage'] if a['damage'] is not None else 'no'
            if a['attackBonus'] is not None:
                bonus = a['attackBonus']
                tempAttacks.append(f"**{a['name']}:** +{bonus} To Hit, {damage} damage.")
            else:
                tempAttacks.append(f"**{a['name']}:** {damage} damage.")
        if not tempAttacks:
            tempAttacks = ['No attacks.']
        a = '\n'.join(tempAttacks)
        if len(a) > 1023:
            a = ', '.join(atk['name'] for atk in attacks)
        if len(a) > 1023:
            a = "Too many attacks, values hidden!"
        embed.add_field(name="Attacks", value=a)

        return embed
