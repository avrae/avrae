import asyncio
import logging
import random
import textwrap

import discord
from d20 import roll
from discord.ext import commands

from cogs5e.models import embeds
from cogs5e.models.embeds import EmbedWithAuthor, EmbedWithColor
from cogs5e.models.errors import InvalidArgument
from gamedata.compendium import compendium
from gamedata.lookuputils import available, get_race_choices
from utils.constants import STAT_ABBREVIATIONS
from utils.functions import get_selection, search_and_select

log = logging.getLogger(__name__)


async def roll_stats(ctx):
    guild_settings = await ctx.get_server_settings()
    print(guild_settings)

    dice = "4d6kh3"
    sets = 1
    straight = False
    min_total = None
    max_total = None
    over = {}
    under = {}

    if guild_settings:
        dice = guild_settings.randchar_dice
        sets = guild_settings.randchar_sets
        straight = guild_settings.randchar_straight
        min_total = guild_settings.randchar_min
        max_total = guild_settings.randchar_max
        over = guild_settings.randchar_over or {}
        under = guild_settings.randchar_under or {}

    embed = EmbedWithColor()
    embed.title = "Generating Random Stats:"

    # Generate our rule text
    rules = []
    if sets > 1:
        rules.append(f"""Rolling {sets} sets""")
    if min_total:
        rules.append(f"""Minimum of {min_total}""")
    if max_total:
        rules.append(f"""Maximum of {max_total}""")
    for m, t in over.items():
        rules.append(f"""At least {t} over {m}""")
    for m, t in under.items():
        rules.append(f"""At least {t} under {m}""")

    stat_rolls = []
    # Only attempt 1000 times to achieve the desired stat sets
    for _ in range(1000):
        # We need an individual copy per set
        current_set = []
        current_over = over.copy()
        current_under = under.copy()
        current_sum = 0
        for i in range(6):
            current_roll = roll(dice)
            current_sum += current_roll.total
            current_set.append(current_roll)

            if current_over and any(current_over.values()):
                for m, t in current_over.items():
                    if t and current_roll.total > int(m):
                        current_over[m] -= 1

            if current_under and any(current_under.values()):
                for m, t in current_under.items():
                    if t and current_roll.total < int(m):
                        current_under[m] -= 1

        meets_over = not current_over or not any(current_over.values())
        meets_under = not current_under or not any(current_under.values())
        meets_min = (current_sum >= min_total) if min_total else True
        meets_max = (current_sum <= max_total) if max_total else True
        if meets_over and meets_under and meets_max and meets_min:
            stat_rolls.append({"rolls": current_set, "total": current_sum})
            if len(stat_rolls) == sets:
                break
    else:
        embed.description = (
            "Unable to roll stat rolls that meet the current rule set.\n\n"
            "Please examine your current randchar settings to ensure that they are achievable."
        )
        return embed

    if rules:
        embed.description = f"Ruling: {', '.join(rules)}"

    for i, rolls in enumerate(stat_rolls, 1):
        embed.add_field(
            name=f"""Stats {f"#{i}" if len(stat_rolls)>1 else ""}""",
            value="\n".join(
                [
                    (f"**{STAT_ABBREVIATIONS[x].upper()}:** " if straight else f"**Stat {x+1}:** ")
                    + str(rolls["rolls"][x])
                    for x in range(6)
                ]
            )
            + f"\n-----\nTotal = `{rolls['total']}`",
            inline=True,
        )

    return embed


class CharGenerator(commands.Cog):
    """Random character generator."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="randchar")
    @commands.max_concurrency(1, per=commands.BucketType.user)
    async def randchar(self, ctx, level=None):
        """Rolls up a random 5e character."""
        if level is None:

            stats = await roll_stats(ctx)
            await ctx.send(embed=stats)
            return

        try:
            level = int(level)
        except:
            await ctx.send("Invalid level.")
            return

        if level > 20 or level < 1:
            await ctx.send("Invalid level (must be 1-20).")
            return

        await self.send_character_details(ctx, level)

    @commands.command(aliases=["name"])
    async def randname(self, ctx, race=None, option=None):
        """Generates a random name, optionally from a given race."""
        if race is None:
            return await ctx.send(f"Your random name: {self.old_name_gen()}")

        embed = EmbedWithAuthor(ctx)
        race_names = await search_and_select(ctx, compendium.names, race, lambda e: e["race"])
        if option is None:
            table = await get_selection(ctx, [(t["name"], t) for t in race_names["tables"]])
        else:
            table = await search_and_select(ctx, race_names["tables"], option, lambda e: e["name"])
        embed.title = f"{table['name']} {race_names['race']} Name"
        embed.description = random.choice(table["choices"])
        await ctx.send(embed=embed)

    @commands.command(name="charref", hidden=True)
    @commands.max_concurrency(1, per=commands.BucketType.user)
    async def charref(self, ctx, level):
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

        await self.send_character_details(ctx, level, race, _class, subclass, background)

    async def select_details(self, ctx):
        author = ctx.author
        channel = ctx.channel

        def chk(m):
            return m.author == author and m.channel == channel

        await ctx.send(author.mention + " What race?", allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        try:
            race_response = await self.bot.wait_for("message", timeout=90, check=chk)
        except asyncio.TimeoutError:
            raise InvalidArgument("Timed out waiting for race.")
        race_choices = await get_race_choices(ctx)
        race = await search_and_select(ctx, race_choices, race_response.content, lambda e: e.name)

        await ctx.send(author.mention + " What class?", allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        try:
            class_response = await self.bot.wait_for("message", timeout=90, check=chk)
        except asyncio.TimeoutError:
            raise InvalidArgument("Timed out waiting for class.")
        class_choices = await available(ctx, compendium.classes, "class")
        _class = await search_and_select(ctx, class_choices, class_response.content, lambda e: e.name)

        subclass_choices = await available(ctx, _class.subclasses, "class")
        if subclass_choices:
            await ctx.send(
                author.mention + " What subclass?", allowed_mentions=discord.AllowedMentions(users=[ctx.author])
            )
            try:
                subclass_response = await self.bot.wait_for("message", timeout=90, check=chk)
            except asyncio.TimeoutError:
                raise InvalidArgument("Timed out waiting for subclass.")
            subclass = await search_and_select(ctx, subclass_choices, subclass_response.content, lambda e: e.name)
        else:
            subclass = None

        await ctx.send(
            author.mention + " What background?", allowed_mentions=discord.AllowedMentions(users=[ctx.author])
        )
        try:
            bg_response = await self.bot.wait_for("message", timeout=90, check=chk)
        except asyncio.TimeoutError:
            raise InvalidArgument("Timed out waiting for background.")
        background_choices = await available(ctx, compendium.backgrounds, "background")
        background = await search_and_select(ctx, background_choices, bg_response.content, lambda e: e.name)
        return race, _class, subclass, background

    async def send_character_details(self, ctx, final_level, race=None, _class=None, subclass=None, background=None):
        loadingMessage = await ctx.channel.send("Generating character, please wait...")
        color = random.randint(0, 0xFFFFFF)

        # Name Gen
        #    DMG name gen
        name = self.old_name_gen()
        # Stat Gen
        #    4d6d1
        #        reroll if too low/high
        await ctx.author.send(embed=roll_stats(ctx))
        # Race Gen
        #    Racial Features
        race = race or random.choice(await get_race_choices(ctx))

        embed = EmbedWithAuthor(ctx)
        embed.title = race.name
        embed.add_field(name="Speed", value=race.speed)
        embed.add_field(name="Size", value=race.size)
        for t in race.traits:
            embeds.add_fields_from_long_text(embed, t.name, t.text)
        embed.set_footer(text=f"Race | {race.source_str()}")

        embed.colour = color
        await ctx.author.send(embed=embed)

        # Class Gen
        #    Class Features

        # class
        _class = _class or random.choice(await available(ctx, compendium.classes, "class"))
        subclass = subclass or (
            random.choice(subclass_choices)
            if (subclass_choices := await available(ctx, _class.subclasses, "class"))
            else None
        )
        embed = EmbedWithAuthor(ctx)

        embed.title = _class.name
        embed.add_field(name="Hit Points", value=_class.hit_points)

        levels = []
        for level in range(1, final_level + 1):
            level = _class.levels[level - 1]
            levels.append(", ".join([feature.name for feature in level]))

        embed.add_field(name="Starting Proficiencies", value=_class.proficiencies, inline=False)
        embed.add_field(name="Starting Equipment", value=_class.equipment, inline=False)

        level_features_str = ""
        for i, l in enumerate(levels):
            level_features_str += f"`{i + 1}` {l}\n"
        embed.description = level_features_str
        await ctx.author.send(embed=embed)

        # level table
        embed = EmbedWithAuthor(ctx)
        embed.title = f"{_class.name}, Level {final_level}"

        for resource, value in zip(_class.table.headers, _class.table.levels[final_level - 1]):
            if value != "0":
                embed.add_field(name=resource, value=value)

        embed.colour = color
        await ctx.author.send(embed=embed)

        # features
        embed_queue = [EmbedWithAuthor(ctx)]
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

        def add_levels(source):
            for level in range(1, final_level + 1):
                level_features = source.levels[level - 1]
                for f in level_features:
                    for field in embeds.get_long_field_args(f.text, f.name):
                        inc_fields(field["value"])
                        embed_queue[-1].add_field(**field)

        add_levels(_class)
        if subclass:
            add_levels(subclass)

        for embed in embed_queue:
            embed.colour = color
            await ctx.author.send(embed=embed)

        # Background Gen
        #    Inventory/Trait Gen
        background = background or random.choice(await available(ctx, compendium.backgrounds, "background"))
        embed = EmbedWithAuthor(ctx)
        embed.title = background.name
        embed.set_footer(text=f"Background | {background.source_str()}")

        ignored_fields = [
            "suggested characteristics",
            "personality trait",
            "ideal",
            "bond",
            "flaw",
            "specialty",
            "harrowing event",
        ]
        for trait in background.traits:
            if trait.name.lower() in ignored_fields:
                continue
            text = textwrap.shorten(trait.text, width=1020, placeholder="...")
            embed.add_field(name=trait.name, value=text, inline=False)
        embed.colour = color
        await ctx.author.send(embed=embed)

        out = (
            f"{ctx.author.mention}\n"
            f"{name}, {race.name} {subclass.name if subclass else ''} {_class.name} {final_level}. "
            f"{background.name} Background.\n"
            f"I have PM'd you full character details."
        )

        await loadingMessage.edit(content=out, allowed_mentions=discord.AllowedMentions(users=[ctx.author]))

    @staticmethod
    def old_name_gen():
        name = ""
        beginnings = [
            "",
            "",
            "",
            "",
            "A",
            "Be",
            "De",
            "El",
            "Fa",
            "Jo",
            "Ki",
            "La",
            "Ma",
            "Na",
            "O",
            "Pa",
            "Re",
            "Si",
            "Ta",
            "Va",
        ]
        middles = [
            "bar",
            "ched",
            "dell",
            "far",
            "gran",
            "hal",
            "jen",
            "kel",
            "lim",
            "mor",
            "net",
            "penn",
            "quill",
            "rond",
            "sark",
            "shen",
            "tur",
            "vash",
            "yor",
            "zen",
        ]
        ends = [
            "",
            "a",
            "ac",
            "ai",
            "al",
            "am",
            "an",
            "ar",
            "ea",
            "el",
            "er",
            "ess",
            "ett",
            "ic",
            "id",
            "il",
            "is",
            "in",
            "or",
            "us",
        ]
        name += random.choice(beginnings) + random.choice(middles) + random.choice(ends)
        name = name.capitalize()
        return name


def setup(bot):
    bot.add_cog(CharGenerator(bot))
