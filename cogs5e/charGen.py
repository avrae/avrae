import asyncio
import logging
import random

from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import compendium
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import InvalidArgument
from utils.functions import ABILITY_MAP, get_selection, parse_data_entry, search_and_select

log = logging.getLogger(__name__)

SKILL_MAP = {'acrobatics': 'acrobatics', 'animal handling': 'animalHandling', 'arcana': 'arcana',
             'athletics': 'athletics', 'deception': 'deception', 'history': 'history', 'initiative': 'initiative',
             'insight': 'insight', 'intimidation': 'intimidation', 'investigation': 'investigation',
             'medicine': 'medicine', 'nature': 'nature', 'perception': 'perception', 'performance': 'performance',
             'persuasion': 'persuasion', 'religion': 'religion', 'sleight of hand': 'sleightOfHand',
             'stealth': 'stealth', 'survival': 'survival'}

CLASS_RESOURCE_NAMES = {"Ki Points": "ki", "Rage Damage": "rageDamage", "Rages": "rages",
                        "Sorcery Points": "sorceryPoints", "Superiority Dice": "superiorityDice",
                        "1st": "level1SpellSlots", "2nd": "level2SpellSlots", "3rd": "level3SpellSlots",
                        "4th": "level4SpellSlots", "5th": "level5SpellSlots", "6th": "level6SpellSlots",
                        "7th": "level7SpellSlots", "8th": "level8SpellSlots", "9th": "level9SpellSlots"}


class CharGenerator(commands.Cog):
    """Random character generator."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='randchar')
    async def randChar(self, ctx, level="0"):
        """Makes a random 5e character."""
        try:
            level = int(level)
        except:
            await ctx.send("Invalid level.")
            return

        if level == 0:
            rolls = [roll("4d6kh3", inline=True) for _ in range(6)]
            stats = '\n'.join(r.skeleton for r in rolls)
            total = sum([r.total for r in rolls])
            await ctx.send(f"{ctx.message.author.mention}\nGenerated random stats:\n{stats}\nTotal = `{total}`")
            return

        if level > 20 or level < 1:
            await ctx.send("Invalid level (must be 1-20).")
            return

        await self.genChar(ctx, level)

    @commands.command(aliases=['name'])
    async def randname(self, ctx, race=None, option=None):
        """Generates a random name, optionally from a given race."""
        if race is None:
            return await ctx.send(f"Your random name: {self.old_name_gen()}")

        embed = EmbedWithAuthor(ctx)
        race_names = await search_and_select(ctx, compendium.names, race, lambda e: e['race'])
        if option is None:
            table = await get_selection(ctx, [(t['name'], t) for t in race_names['tables']])
        else:
            table = await search_and_select(ctx, race_names['tables'], option, lambda e: e['name'])
        embed.title = f"{table['name']} {race_names['race']} Name"
        embed.description = random.choice(table['choices'])
        await ctx.send(embed=embed)

    @commands.command(name='charref', aliases=['makechar'])
    async def char(self, ctx, level):
        """Gives you reference stats for a 5e character."""
        try:
            level = int(level)
        except:
            await ctx.send("Invalid level.")
            return
        if level > 20 or level < 1:
            await ctx.send("Invalid level (must be 1-20).")
            return

        race, _class, subclass, background = await self.select_details(ctx)

        await self.genChar(ctx, level, race, _class, subclass, background)

    async def select_details(self, ctx):
        author = ctx.author
        channel = ctx.channel

        def chk(m):
            return m.author == author and m.channel == channel

        await ctx.send(author.mention + " What race?")
        try:
            race_response = await self.bot.wait_for('message', timeout=90, check=chk)
        except asyncio.TimeoutError:
            raise InvalidArgument("Timed out waiting for race.")
        race = await search_and_select(ctx, compendium.fancyraces, race_response.content, lambda e: e.name)

        await ctx.send(author.mention + " What class?")
        try:
            class_response = await self.bot.wait_for('message', timeout=90, check=chk)
        except asyncio.TimeoutError:
            raise InvalidArgument("Timed out waiting for class.")
        _class = await search_and_select(ctx, compendium.classes, class_response.content, lambda e: e['name'])

        if 'subclasses' in _class:
            await ctx.send(author.mention + " What subclass?")
            try:
                subclass_response = await self.bot.wait_for('message', timeout=90, check=chk)
            except asyncio.TimeoutError:
                raise InvalidArgument("Timed out waiting for subclass.")
            subclass = await search_and_select(ctx, _class['subclasses'], subclass_response.content,
                                               lambda e: e['name'])
        else:
            subclass = None

        await ctx.send(author.mention + " What background?")
        try:
            bg_response = await self.bot.wait_for('message', timeout=90, check=chk)
        except asyncio.TimeoutError:
            raise InvalidArgument("Timed out waiting for background.")
        background = await search_and_select(ctx, compendium.backgrounds, bg_response.content, lambda e: e.name)
        return race, _class, subclass, background

    async def genChar(self, ctx, final_level, race=None, _class=None, subclass=None, background=None):
        loadingMessage = await ctx.channel.send("Generating character, please wait...")
        color = random.randint(0, 0xffffff)

        # Name Gen
        #    DMG name gen
        name = self.old_name_gen()
        # Stat Gen
        #    4d6d1
        #        reroll if too low/high
        stats = self.stat_gen()
        await ctx.author.send("**Stats for {0}:** `{1}`".format(name, stats))
        # Race Gen
        #    Racial Features
        race = race or random.choice(compendium.fancyraces)

        embed = EmbedWithAuthor(ctx)
        embed.title = race.name
        embed.description = f"Source: {race.source}"
        embed.add_field(name="Speed", value=race.get_speed_str())
        embed.add_field(name="Size", value=race.size)
        embed.add_field(name="Ability Bonuses", value=race.get_asi_str())
        for t in race.get_traits():
            f_text = t['text']
            f_text = [f_text[i:i + 1024] for i in range(0, len(f_text), 1024)]
            embed.add_field(name=t['name'], value=f_text[0])
            for piece in f_text[1:]:
                embed.add_field(name="** **", value=piece)

        embed.colour = color
        await ctx.author.send(embed=embed)

        # Class Gen
        #    Class Features
        _class = _class or random.choice(compendium.classes)
        subclass = subclass or (random.choice(_class['subclasses']) if _class['subclasses'] else None)
        embed = EmbedWithAuthor(ctx)
        embed.title = f"{_class['name']} ({subclass['name']})"
        embed.add_field(name="Hit Die", value=f"1d{_class['hd']['faces']}")
        embed.add_field(name="Saving Throws", value=', '.join(ABILITY_MAP.get(p) for p in _class['proficiency']))

        levels = []
        starting_profs = f"You are proficient with the following items, " \
            f"in addition to any proficiencies provided by your race or background.\n" \
            f"Armor: {', '.join(_class['startingProficiencies'].get('armor', ['None']))}\n" \
            f"Weapons: {', '.join(_class['startingProficiencies'].get('weapons', ['None']))}\n" \
            f"Tools: {', '.join(_class['startingProficiencies'].get('tools', ['None']))}\n" \
            f"Skills: Choose {_class['startingProficiencies']['skills']['choose']} from " \
            f"{', '.join(_class['startingProficiencies']['skills']['from'])}"

        equip_choices = '\n'.join(f"• {i}" for i in _class['startingEquipment']['default'])
        gold_alt = f"Alternatively, you may start with {_class['startingEquipment']['goldAlternative']} gp " \
            f"to buy your own equipment." if 'goldAlternative' in _class['startingEquipment'] else ''
        starting_items = f"You start with the following items, plus anything provided by your background.\n" \
            f"{equip_choices}\n" \
            f"{gold_alt}"

        for level in range(1, final_level + 1):
            level_str = []
            level_features = _class['classFeatures'][level - 1]
            for feature in level_features:
                level_str.append(feature.get('name'))
            levels.append(', '.join(level_str))

        embed.add_field(name="Starting Proficiencies", value=starting_profs)
        embed.add_field(name="Starting Equipment", value=starting_items)

        level_features_str = ""
        for i, l in enumerate(levels):
            level_features_str += f"`{i + 1}` {l}\n"
        embed.description = level_features_str

        embed.colour = color
        await ctx.author.send(embed=embed)

        embed = EmbedWithAuthor(ctx)
        level_resources = {}
        for table in _class.get('classTableGroups', []):
            relevant_row = table['rows'][final_level - 1]
            for i, col in enumerate(relevant_row):
                level_resources[table['colLabels'][i]] = parse_data_entry([col])

        for res_name, res_value in level_resources.items():
            embed.add_field(name=res_name, value=res_value)

        embed.colour = color
        await ctx.author.send(embed=embed)

        embed_queue = [EmbedWithAuthor(ctx)]
        num_subclass_features = 0
        num_fields = 0

        def inc_fields(ftext):
            nonlocal num_fields
            num_fields += 1
            if num_fields > 25:
                embed_queue.append(EmbedWithAuthor(ctx))
                num_fields = 0
            if len(str(embed_queue[-1].to_dict())) + len(ftext) > 5800:
                embed_queue.append(EmbedWithAuthor(ctx))
                num_fields = 0

        for level in range(1, final_level + 1):
            level_features = _class['classFeatures'][level - 1]
            for f in level_features:
                if f.get('gainSubclassFeature'):
                    num_subclass_features += 1
                text = parse_data_entry(f['entries'])
                text = [text[i:i + 1024] for i in range(0, len(text), 1024)]
                inc_fields(text[0])
                embed_queue[-1].add_field(name=f['name'], value=text[0])
                for piece in text[1:]:
                    inc_fields(piece)
                    embed_queue[-1].add_field(name="\u200b", value=piece)
        if subclass:
            for num in range(num_subclass_features):
                level_features = subclass['subclassFeatures'][num]
                for feature in level_features:
                    for entry in feature.get('entries', []):
                        if not isinstance(entry, dict): continue
                        if not entry.get('type') == 'entries': continue
                        fe = {'name': entry['name'],
                              'text': parse_data_entry(entry['entries'])}
                        text = [fe['text'][i:i + 1024] for i in range(0, len(fe['text']), 1024)]
                        inc_fields(text[0])
                        embed_queue[-1].add_field(name=fe['name'], value=text[0])
                        for piece in text[1:]:
                            inc_fields(piece)
                            embed_queue[-1].add_field(name="\u200b", value=piece)

        for embed in embed_queue:
            embed.colour = color
            await ctx.author.send(embed=embed)

        # Background Gen
        #    Inventory/Trait Gen
        background = background or random.choice(compendium.backgrounds)
        embed = EmbedWithAuthor(ctx)
        embed.title = background.name
        embed.description = f"*Source: {background.source}*"

        ignored_fields = ['suggested characteristics', 'specialty',
                          'harrowing event']
        for trait in background.traits:
            if trait['name'].lower() in ignored_fields: continue
            text = trait['text']
            text = [text[i:i + 1024] for i in range(0, len(text), 1024)]
            embed.add_field(name=trait['name'], value=text[0])
            for piece in text[1:]:
                embed.add_field(name="\u200b", value=piece)
        embed.colour = color
        await ctx.author.send(embed=embed)

        out = "{6}\n{0}, {1} {7} {2} {3}. {4} Background.\nStat Array: `{5}`\nI have PM'd you full character details.".format(
            name, race.name, _class['name'], final_level, background.name, stats, ctx.message.author.mention,
            subclass['name'] if subclass else "")

        await loadingMessage.edit(content=out)

    @staticmethod
    def old_name_gen():
        name = ""
        beginnings = ["", "", "", "", "A", "Be", "De", "El", "Fa", "Jo", "Ki", "La", "Ma", "Na", "O", "Pa", "Re", "Si",
                      "Ta", "Va"]
        middles = ["bar", "ched", "dell", "far", "gran", "hal", "jen", "kel", "lim", "mor", "net", "penn", "quill",
                   "rond", "sark", "shen", "tur", "vash", "yor", "zen"]
        ends = ["", "a", "ac", "ai", "al", "am", "an", "ar", "ea", "el", "er", "ess", "ett", "ic", "id", "il", "is",
                "in", "or", "us"]
        name += random.choice(beginnings) + random.choice(middles) + random.choice(ends)
        name = name.capitalize()
        return name

    @staticmethod
    def stat_gen():
        stats = [roll('4d6kh3').total for _ in range(6)]
        return stats


def setup(bot):
    bot.add_cog(CharGenerator(bot))
