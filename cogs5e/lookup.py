"""
Created on Nov 29, 2016

@author: andrew
"""

import itertools
import logging

import cachetools
import disnake
from disnake.ext import commands

import gamedata
import ui
import utils.settings
from cogs5e.models.embeds import EmbedWithAuthor, add_fields_from_long_text, set_maybe_long_desc
from cogs5e.models.errors import RequiresLicense
from cogsmisc.stats import Stats
from gamedata import lookuputils
from gamedata.compendium import compendium
from gamedata.klass import ClassFeature
from gamedata.lookuputils import create_selectkey, lookup_converter, can_access, slash_match_key
from gamedata.race import RaceFeature
from gamedata.shared import CachedSourced, Sourced
from utils import checks, img
from utils.argparser import argparse
from utils.functions import chunk_text, get_positivity, search_and_select, smart_trim, trim_str, try_delete, search
from utils.settings import ServerSettings

LARGE_THRESHOLD = 200
ENTITY_TTL = 5 * 60
ENTITY_CACHE = cachetools.TTLCache(64, ENTITY_TTL)

log = logging.getLogger(__name__)


class Lookup(commands.Cog):
    """Commands to help look up items, status effects, rules, etc."""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="lookup")
    async def slash_lookup(self, inter: disnake.ApplicationCommandInteraction):
        if inter.author.id in self.bot.muted:
            await inter.send("You do not have permission to use this command.", ephemeral=True)
            raise commands.CommandNotFound

    # ==== rules/references ====
    async def _show_reference_options(self, ctx, version=None):
        if version is None:
            serverSettings = await ctx.get_server_settings()
            version = serverSettings.version
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = "Rules"
        categories = ", ".join(a["type"] for a in compendium.rule_references if a["version"] == version)
        embed.description = (
            f"Use `{ctx.prefix}{ctx.invoked_with} <category> <version(defaults to 2024)>` to look at all actions of "
            f"a certain type.\nCategories: {categories}"
        )

        for actiontype in compendium.rule_references:
            embed.add_field(
                name=actiontype["fullName"], value=", ".join(a["name"] for a in actiontype["items"]), inline=False
            )

        await destination.send(embed=embed)

    async def _show_action_options(self, ctx, actiontype):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = actiontype["fullName"]

        actions = []
        for action in actiontype["items"]:
            actions.append(f"**{action['name']}** - *{action['short']}*")

        embed.description = "\n".join(actions)
        await destination.send(embed=embed)

    @commands.command(aliases=["status"])
    async def condition(self, ctx, *, name: str = None):
        """Looks up a condition."""
        if not name:
            name = "condition"
        else:
            name = f"Condition: {name}"
        await self.rule(ctx, name=name)

    @commands.command(aliases=["reference"])
    async def rule(self, ctx, *, name: str = None):
        """Looks up a rule."""
        valid_versions = ["2024", "2014"]  # TODO: move to a global variable

        if name:
            version = name.split()[-1] if name.split()[-1] in valid_versions else "2024"
            name = name.replace(version, "").strip() if name.split()[-1] in valid_versions else name
        else:
            version = "2024"

        if name is None:
            return await self._show_reference_options(ctx)

        options = []
        for actiontype in (a for a in compendium.rule_references if a.get("version") == version or "version" not in a):
            if name == actiontype["type"]:
                return await self._show_action_options(ctx, actiontype)
            else:
                options.extend(actiontype["items"])

        result, metadata = await search_and_select(ctx, options, name, lambda e: e["fullName"], return_metadata=True)
        await lookuputils.add_training_data(self.bot.mdb, "reference", name, result["fullName"], metadata=metadata)

        return await self._rule(ctx, result, version)

    @slash_lookup.sub_command(name="rule", description="Looks up a rule or condition.")
    async def slash_rule(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name=commands.Param(
            description="The rule or condition you want to look up", converter=lookup_converter("rule")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Rule not found.", ephemeral=True)
                return
            name = name[0]
        return await self._rule(inter, name)

    @slash_rule.autocomplete("name")
    async def slash_rule_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        choices = []
        for actiontype in (a for a in compendium.rule_references if a.get("version") == "2024" or "version" not in a):
            choices.extend(actiontype["items"])

        result, strict = search(choices, user_input, lambda e: e["fullName"], 25)
        if strict:
            return [result["fullName"]]
        return [r["fullName"] for r in result][:25]

    @slash_lookup.sub_command(name="rules2014", description="Looks up a 2014 rule.")
    async def slash_2014_rule(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name=commands.Param(
            description="The rule or condition you want to look up", converter=lookup_converter("rule2014")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Rule not found.", ephemeral=True)
                return
            name = name[0]
        return await self._rule(inter, name, "2014")

    @slash_2014_rule.autocomplete("name")
    async def slash_2014_rule_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        choices = []
        for actiontype in (a for a in compendium.rule_references if a.get("version") == "2014" or "version" not in a):
            choices.extend(actiontype["items"])

        result, strict = search(choices, user_input, lambda e: e["fullName"], 25)
        if strict:
            return [result["fullName"]]
        return [r["fullName"] for r in result][:25]

    async def _rule(self, ctx, rule, version=None):
        if version is None:
            serverSettings = await ctx.get_server_settings()
            version = serverSettings.version
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = rule["fullName"]
        embed.description = f"*{rule['short']}*"
        add_fields_from_long_text(embed, "Description", rule["desc"])
        embed.set_footer(text=f"Rule | {rule['source']} | {version}")

        await destination.send(embed=embed)

    # ==== feats ====
    @commands.command()
    async def feat(self, ctx, *, name: str):
        """Looks up a feat."""
        result: gamedata.Feat = await lookuputils.search_entities(ctx, {"feat": compendium.feats}, name)
        return await self._feat(ctx, result)

    @slash_lookup.sub_command(name="feat", description="Looks up a feat.")
    async def slash_feat(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.feat = commands.Param(
            description="The feat you want to look up", converter=lookup_converter("feat")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Feat not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["feat"])
        return await self._feat(inter, name)

    @slash_feat.autocomplete("name")
    async def slash_feat_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {"feat": await self.bot.ddb.get_accessible_entities(inter, inter.author.id, "feat")}
        select_key = create_selectkey(available_ids)

        result, strict = search(compendium.feats, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _feat(self, ctx, result: gamedata.feat):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        if result.prerequisite:
            embed.add_field(name="Prerequisite", value=result.prerequisite, inline=False)
        add_fields_from_long_text(embed, "Description", result.desc)
        lookuputils.handle_source_footer(embed, result, "Feat")
        await destination.send(embed=embed)

    # ==== races / racefeats ====
    @commands.command(aliases=["speciesfeat"])
    async def racefeat(self, ctx, *, name: str):
        """Looks up a species feature."""
        result: RaceFeature = await lookuputils.search_entities(
            ctx, {"race": compendium.rfeats, "subrace": compendium.subrfeats}, name, "racefeat"
        )
        return await self._racefeat(ctx, result)

    @slash_lookup.sub_command(name="racefeat", description="Looks up a species feature.")
    async def slash_racefeat(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: RaceFeature = commands.Param(
            description="The species feature you want to look up", converter=lookup_converter("racefeat")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Species feature not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["race", "subrace"])
        return await self._racefeat(inter, name)

    @slash_racefeat.autocomplete("name")
    async def slash_racefeat_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {
            k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in ("race", "subrace")
        }
        select_key = create_selectkey(available_ids)

        result, strict = search(compendium.rfeats + compendium.subrfeats, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    @slash_lookup.sub_command(name="speciesfeat", description="Looks up a species feature.")
    async def slash_speciesfeat(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: RaceFeature = commands.Param(
            description="The species feature you want to look up", converter=lookup_converter("racefeat")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Species feature not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["subrace"])
        return await self._racefeat(inter, name)

    @slash_speciesfeat.autocomplete("name")
    async def slash_speciesfeat_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {
            k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in ("race", "subrace")
        }
        select_key = create_selectkey(available_ids)

        result, strict = search(compendium.rfeats + compendium.subrfeats, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _racefeat(self, ctx, result: RaceFeature):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        set_maybe_long_desc(embed, result.text)
        lookuputils.handle_source_footer(embed, result, "Species Feature")
        await destination.send(embed=embed)

    @commands.command(aliases=["species"])
    async def race(self, ctx, *, name: str):
        """Looks up a species."""
        result: gamedata.Race = await lookuputils.search_entities(
            ctx, {"race": compendium.races, "subrace": compendium.subraces}, name, "race"
        )
        return await self._race(ctx, result)

    @slash_lookup.sub_command(name="race", description="Looks up a race.")
    async def slash_race(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.race = commands.Param(
            description="The species you want to look up", converter=lookup_converter("race")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Species not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["race", "subrace"])
        return await self._race(inter, name)

    @slash_race.autocomplete("name")
    async def slash_race_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {
            k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in ("race", "subrace")
        }
        select_key = create_selectkey(available_ids)

        result, strict = search(compendium.races + compendium.subraces, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    @slash_lookup.sub_command(name="species", description="Looks up a species.")
    async def slash_species(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.race = commands.Param(
            description="The species you want to look up", converter=lookup_converter("race")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Species not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["race", "subrace"])
        return await self._race(inter, name)

    @slash_species.autocomplete("name")
    async def slash_species_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {
            k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in ("race", "subrace")
        }
        select_key = create_selectkey(available_ids)

        result, strict = search(compendium.races + compendium.subraces, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _race(self, ctx, result: gamedata.race):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        embed.add_field(name="Speed", value=result.speed)
        embed.add_field(name="Size", value=result.size)
        for t in result.traits:
            add_fields_from_long_text(embed, t.name, t.text)
        lookuputils.handle_source_footer(embed, result, "Species")
        await destination.send(embed=embed)

    # ==== classes / classfeats ====
    @commands.command()
    async def classfeat(self, ctx, *, name: str):
        """Looks up a class feature."""
        result: ClassFeature = await lookuputils.search_entities(
            ctx, {"class": compendium.cfeats, "class-feature": compendium.optional_cfeats}, name, query_type="classfeat"
        )
        return await self._classfeat(ctx, result)

    @slash_lookup.sub_command(name="classfeat", description="Looks up a class feature.")
    async def slash_classfeat(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: ClassFeature = commands.Param(
            description="The class feature you want to look up", converter=lookup_converter("classfeat")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Class feature not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["class", "class-feature"])
        return await self._classfeat(inter, name)

    @slash_classfeat.autocomplete("name")
    async def slash_classfeat_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {
            k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in ("class", "class-feature")
        }
        select_key = create_selectkey(available_ids)

        result, strict = search(compendium.cfeats + compendium.optional_cfeats, user_input, slash_match_key, 25)

        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _classfeat(self, ctx, result: ClassFeature):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        set_maybe_long_desc(embed, result.text)
        lookuputils.handle_source_footer(embed, result, "Class Feature")
        await destination.send(embed=embed)

    @commands.command(name="class")
    async def classcmd(self, ctx, name: str, level: int = None):
        """Looks up a class, or all features of a certain level."""
        if level is not None and not 0 < level < 21:
            return await ctx.send("Invalid level.")

        result: gamedata.Class = await lookuputils.search_entities(ctx, {"class": compendium.classes}, name)
        return await self._class(ctx, result, level)

    @slash_lookup.sub_command(name="class", description="Looks up a class, or all features of a certain level.")
    async def slash_class(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Class = commands.Param(
            description="The class you want to look up", converter=lookup_converter("class")
        ),
        level: int = commands.Param(
            description="The level you want to look at. Leave blank for an overview",
            choices=list(range(1, 21)),
            default=None,
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Class not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["class"])
        return await self._class(inter, name, level)

    @slash_class.autocomplete("name")
    async def slash_class_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {"class": await self.bot.ddb.get_accessible_entities(inter, inter.author.id, "class")}
        select_key = create_selectkey(available_ids)
        result, strict = search(compendium.classes, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _class(self, ctx, result: gamedata.Class, level):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        if level is None:
            embed.title = result.name
            embed.add_field(name="Hit Points", value=result.hit_points)

            levels = []
            for level in range(1, 21):
                level_features = result.levels[level - 1]
                feature_names = [feature.name for feature in level_features]
                if level in result.subclass_feature_levels:
                    feature_names.append(f"{result.subclass_title} Feature")
                levels.append(", ".join(feature_names))

            level_features_str = ""
            for i, l in enumerate(levels):
                level_features_str += f"`{i + 1}` {l}\n"
            embed.description = level_features_str

            available_ocfs = await lookuputils.available(ctx, result.optional_features, entity_type="class-feature")
            if available_ocfs:
                ocf_names = ", ".join(ocf.name for ocf in available_ocfs)
                embed.add_field(name="Optional Class Features", value=ocf_names, inline=False)

            embed.add_field(name="Starting Proficiencies", value=result.proficiencies, inline=False)
            embed.add_field(name="Starting Equipment", value=result.equipment, inline=False)

            lookuputils.handle_source_footer(
                embed, result, f"Use /lookup classfeat to look up a feature.", add_source_str=False
            )
        else:
            embed.title = f"{result.name}, Level {level}"

            level_features = result.levels[level - 1]

            for resource, value in zip(result.table.headers, result.table.levels[level - 1]):
                if value != "0":
                    embed.add_field(name=resource, value=value)

            for f in level_features:
                embed.add_field(
                    name=f.name,
                    value=smart_trim(f.text, 1024, f"> Use `/lookup classfeat name:{f.name}` to view full text"),
                    inline=False,
                )

            lookuputils.handle_source_footer(
                embed, result, f"Use /lookup classfeat to look up a feature if it is cut off.", add_source_str=False
            )

        await destination.send(embed=embed)

    @commands.command()
    async def subclass(self, ctx, *, name: str):
        """Looks up a subclass."""
        result: gamedata.Subclass = await lookuputils.search_entities(
            ctx, {"class": compendium.subclasses}, name, query_type="subclass"
        )
        return await self._subclass(ctx, result)

    @slash_lookup.sub_command(name="subclass", description="Looks up a subclass.")
    async def slash_subclass(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Subclass = commands.Param(
            description="The subclass you want to look up", converter=lookup_converter("subclass")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Subclass not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["class"])
        return await self._subclass(inter, name)

    @slash_subclass.autocomplete("name")
    async def slash_subclass_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {"class": await self.bot.ddb.get_accessible_entities(inter, inter.author.id, "class")}
        select_key = create_selectkey(available_ids)
        result, strict = search(compendium.subclasses, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _subclass(self, ctx, result: gamedata.Subclass):
        destination = await self._get_destination(ctx)

        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        embed.title = result.name
        embed.description = smart_trim(result.description, 2048)

        for level in result.levels:
            for feature in level:
                text = smart_trim(
                    feature.text, 1024, f"> Use `/lookup classfeat name:{feature.name}` to view full text"
                )
                embed.add_field(name=feature.name, value=text, inline=False)

        lookuputils.handle_source_footer(
            embed, result, f"Use /lookup classfeat to look up a feature if it is cut off", add_source_str=True
        )

        await destination.send(embed=embed)

    # ==== backgrounds ====
    @commands.command()
    async def background(self, ctx, *, name: str):
        """Looks up a background."""
        result: gamedata.Background = await lookuputils.search_entities(
            ctx, {"background": compendium.backgrounds}, name
        )
        return await self._background(ctx, result)

    @slash_lookup.sub_command(name="background", description="Looks up a background.")
    async def slash_background(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Background = commands.Param(
            description="The background you want to look up", converter=lookup_converter("background")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Background not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["background"])
        return await self._background(inter, name)

    @slash_background.autocomplete("name")
    async def slash_background_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        available_ids = {"background": await self.bot.ddb.get_accessible_entities(inter, inter.author.id, "background")}
        select_key = create_selectkey(available_ids)
        result, strict = search(compendium.backgrounds, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _background(self, ctx, result: gamedata.Background):
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        embed.title = result.name
        lookuputils.handle_source_footer(embed, result, "Background")

        for trait in result.traits:
            text = trim_str(trait.text, 1024)
            embed.add_field(name=trait.name, value=text, inline=False)

        await destination.send(embed=embed)

    # ==== monsters ====
    @commands.command()
    async def monster(self, ctx, *, name: str):
        """
        Looks up a monster.
        If you are not a Dungeon Master, this command may display partially hidden information. See !servsettings
        to view which roles on a server count as Dungeon Master roles.
        __Valid Arguments__
        -h - Shows the obfuscated stat block, even if you can see the full stat block.
        """
        if ctx.guild is not None:
            guild_settings = await ctx.get_server_settings()
            pm = guild_settings.lookup_pm_result
        else:
            pm = False

        # #1741 -h arg for monster lookup
        mon_args = argparse(name)
        hide_name = mon_args.get("h", False, bool)
        name = name.replace(" -h", "").rstrip()
        pm_lookup = pm or hide_name
        choices = await lookuputils.get_monster_choices(ctx)
        monster = await lookuputils.search_entities(ctx, {"monster": choices}, name, pm=pm_lookup)

        if hide_name:
            await try_delete(ctx.message)

        return await self._monster(ctx, monster, hide_name)

    @slash_lookup.sub_command(name="monster", description="Looks up a monster.")
    async def slash_monster(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Monster = commands.Param(
            description="The monster you want to look up", converter=lookup_converter("monster")
        ),
        hide_name: bool = commands.Param(
            description="Shows the obfuscated stat block, even if you can see the full stat block.", default=False
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Monster not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["monster"])
        return await self._monster(inter, name, hide_name)

    async def _monster(self, ctx, monster: gamedata.Monster, hide_name):
        destination = await self._get_destination(ctx)
        if ctx.guild is not None:
            if hasattr(ctx, "get_server_settings"):
                guild_settings = await ctx.get_server_settings()
            else:
                guild_settings = await ServerSettings.for_guild(mdb=ctx.bot.mdb, guild_id=ctx.guild.id)
            pm = guild_settings.lookup_pm_result
            pm_dm = guild_settings.lookup_pm_dm
            req_dm_monster = guild_settings.lookup_dm_required
            visible = (not req_dm_monster) or guild_settings.is_dm(ctx.author)
        else:
            pm = False
            pm_dm = False
            req_dm_monster = False
            visible = True

        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour

        if hide_name:
            visible = False
        else:
            embed_queue[-1].title = monster.name
        embed_queue[-1].url = monster.url

        def safe_append(title, desc):
            if len(desc) < 1024:
                embed_queue[-1].add_field(name=title, value=desc, inline=False)
            elif len(desc) < 2048:
                # noinspection PyTypeChecker
                # I'm adding an Embed to a list of Embeds, shut up.
                embed_queue.append(disnake.Embed(colour=color, description=desc, title=title))
            else:
                # noinspection PyTypeChecker
                embed_queue.append(disnake.Embed(colour=color, title=title))
                trait_all = chunk_text(desc, max_chunk_size=2048)
                embed_queue[-1].description = trait_all[0]
                for t in trait_all[1:]:
                    # noinspection PyTypeChecker
                    embed_queue.append(disnake.Embed(colour=color, description=t))

        if visible:
            embed_queue[-1].description = monster.get_meta()
            if monster.traits:
                trait = "\n\n".join(f"***{a.name}.*** {a.desc}" for a in monster.traits)
                if trait:
                    safe_append("Special Abilities", trait)
            if monster.actions:
                action = "\n\n".join(f"***{a.name}.*** {a.desc}" for a in monster.actions)
                if action:
                    safe_append("Actions", action)
            if monster.bonus_actions:
                bonus_action = "\n\n".join(f"***{a.name}.*** {a.desc}" for a in monster.bonus_actions)
                if bonus_action:
                    safe_append("Bonus Actions", bonus_action)
            if monster.reactions:
                reaction = "\n\n".join(f"***{a.name}.*** {a.desc}" for a in monster.reactions)
                if reaction:
                    safe_append("Reactions", reaction)
            if monster.legactions:
                proper_name = f"The {monster.name}" if not monster.proper else monster.name
                legendary = [
                    f"{proper_name} can take {monster.la_per_round} legendary actions, choosing from "
                    "the options below. Only one legendary action can be used at a time and only at the "
                    f"end of another creature's turn. {proper_name} regains spent legendary actions at "
                    "the start of its turn."
                ]
                for a in monster.legactions:
                    if a.name:
                        legendary.append(f"***{a.name}.*** {a.desc}")
                    else:
                        legendary.append(a.desc)
                if legendary:
                    safe_append("Legendary Actions", "\n\n".join(legendary))
            if monster.mythic_actions:
                mythic_action = "\n\n".join(f"***{a.name}.*** {a.desc}" for a in monster.mythic_actions)
                if mythic_action:
                    safe_append("Mythic Actions", mythic_action)

        else:
            hp = monster.hp
            ac = monster.ac
            size = monster.size
            _type = monster.creature_type
            if hp < 10:
                hp = "Very Low"
            elif 10 <= hp < 50:
                hp = "Low"
            elif 50 <= hp < 100:
                hp = "Medium"
            elif 100 <= hp < 200:
                hp = "High"
            elif 200 <= hp < 400:
                hp = "Very High"
            elif 400 <= hp:
                hp = "Ludicrous"

            if ac < 6:
                ac = "Very Low"
            elif 6 <= ac < 9:
                ac = "Low"
            elif 9 <= ac < 15:
                ac = "Medium"
            elif 15 <= ac < 17:
                ac = "High"
            elif 17 <= ac < 22:
                ac = "Very High"
            elif 22 <= ac:
                ac = "Untouchable"

            languages = len(monster.languages)

            embed_queue[-1].description = (
                f"*{size} {_type}*\n"
                f"**AC** {ac}\n**HP** {hp}\n**Speed** {monster.speed}\n"
                f"{monster.get_hidden_stat_array()}\n"
                f"**Languages** {languages}\n"
            )

            if monster.traits:
                embed_queue[-1].add_field(name="Special Abilities", value=str(len(monster.traits)))

            if monster.actions:
                embed_queue[-1].add_field(name="Actions", value=str(len(monster.actions)))

            if monster.bonus_actions:
                embed_queue[-1].add_field(name="Bonus Actions", value=str(len(monster.bonus_actions)))

            if monster.reactions:
                embed_queue[-1].add_field(name="Reactions", value=str(len(monster.reactions)))

            if monster.legactions:
                embed_queue[-1].add_field(name="Legendary Actions", value=str(len(monster.legactions)))

        lookuputils.handle_source_footer(embed_queue[-1], monster, "Creature")

        embed_queue[0].set_thumbnail(url=monster.get_image_url())
        await Stats.increase_stat(ctx, "monsters_looked_up_life")

        for i, embed in enumerate(embed_queue):
            if pm or (visible and pm_dm and req_dm_monster):
                await ctx.author.send(embed=embed)
            elif i == 0:
                # Ensure the first embed is sent as a reply
                await destination.send(embed=embed)
            else:
                # and the rest are to the channel
                await destination.channel.send(embed=embed)

    @commands.command()
    async def monimage(self, ctx, *, name: str):
        """Shows a monster's image.
        __Valid Arguments__
        -h - Hides the monster statblock name."""
        # #1741 -h arg for monster lookup
        image_args = argparse(name)
        hide_name = image_args.get("h", False, bool)
        name = name.replace(" -h", "").rstrip()
        if hide_name:
            await try_delete(ctx.message)

        choices = await lookuputils.get_monster_choices(ctx)
        monster = await lookuputils.search_entities(ctx, {"monster": choices}, name, pm=hide_name)
        await Stats.increase_stat(ctx, "monsters_looked_up_life")

        await self._monimage(ctx, monster, hide_name)

    @slash_lookup.sub_command(name="monimage", description="Shows a monster's image.")
    async def slash_monimage(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Monster = commands.Param(
            description="The monster you want to look up. (Excludes monsters without images)",
            converter=lookup_converter("monster"),
        ),
        hide_name: bool = commands.Param(description="Hides the monster statblock name.", default=False),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Monster not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["monster"])
        return await self._monimage(inter, name, hide_name)

    async def _monimage(self, ctx, monster: gamedata.Monster, hide_name):
        destination = await self._get_destination(ctx)
        url = monster.get_image_url()
        embed = EmbedWithAuthor(ctx)
        if not hide_name:
            embed.title = monster.name
        embed.description = f"{monster.size} monster."

        if not url:
            return await ctx.channel.send("This monster has no image.")

        embed.set_image(url=url)
        await destination.send(embed=embed)

    @commands.command()
    async def token(self, ctx, name=None, *, args=""):
        """
        Shows a monster or your character's token.
        __Valid Arguments__
        -border <plain|none (player token only)> - Overrides the token border.
        -h - Hides the monster statblock name.
        """
        if name is None or name.startswith("-"):
            token_cmd = self.bot.get_command("playertoken")
            if token_cmd is None:
                return await ctx.send("Error: SheetManager cog not loaded.")
            if name:
                args = name + " " + args
            return await ctx.invoke(token_cmd, args=args)

        # select monster
        token_args = argparse(args)
        plain_border = token_args.last("border") == "plain"
        hide_name = token_args.get("h", False, bool)
        if hide_name:
            await try_delete(ctx.message)

        choices = await lookuputils.get_monster_choices(ctx)
        monster = await lookuputils.search_entities(ctx, {"monster": choices}, name, pm=hide_name)
        await Stats.increase_stat(ctx, "monsters_looked_up_life")

        await self._token(ctx, monster, plain_border, hide_name)

    @slash_lookup.sub_command(name="token", description="Shows a monster token.")
    async def slash_token(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Monster = commands.Param(
            description="The monster you want to look up. (Excludes monsters without images)",
            converter=lookup_converter("monster"),
        ),
        plain_border: bool = commands.Param(
            description="Show the plain border instead of the subscriber border, if available.", default=False
        ),
        hide_name: bool = commands.Param(
            description="Shows the obfuscated stat block, even if you can see the full stat block.", default=False
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Monster not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["monster"])
        return await self._token(inter, name, plain_border, hide_name)

    @slash_monster.autocomplete("name")
    @slash_monimage.autocomplete("name")
    @slash_token.autocomplete("name")
    async def slash_monster_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        choices = await self._get_entities(inter, "monster", lookuputils.get_monster_choices)

        # If this autocomplete is for token or monimage, filter out monsters without tokens or images
        lookup_command = list(inter.options)[0]
        if lookup_command == "token":
            choices = list(filter(lambda x: x.has_token, choices))
        elif lookup_command == "monimage":
            choices = list(filter(lambda x: x.has_image, choices))

        available_ids = {"monster": await self.bot.ddb.get_accessible_entities(inter, inter.author.id, "monster")}
        select_key = create_selectkey(available_ids)
        result, strict = search(choices, user_input, slash_match_key)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _token(self, ctx, monster: gamedata.Monster, plain_border, hide_name):
        destination = await self._get_destination(ctx)

        # select border
        ddb_user = await self.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        is_subscriber = ddb_user and ddb_user.is_subscriber

        if monster.homebrew:
            # homebrew: generate token
            if not monster.get_image_url():
                return await destination.send("This monster has no image.")
            try:
                token_args = None
                # Not the cleanest but leaves it open to additional args in the future
                if plain_border:
                    token_args = "-border plain"
                image = await img.generate_token(monster.get_image_url(), is_subscriber, token_args)
            except Exception as e:
                return await destination.send(f"Error generating token: {e}")
        else:
            # official monsters
            token_url = monster.get_token_url(is_subscriber)
            if plain_border:
                token_url = monster.get_token_url(False)

            if not token_url:
                return await destination.send("This monster has no image.")

            image = await img.fetch_monster_image(token_url)

        embed = EmbedWithAuthor(ctx)
        if not hide_name:
            embed.title = monster.name
        embed.description = f"{monster.size} monster."

        file = disnake.File(image, filename="image.png")
        embed.set_image(url="attachment://image.png")
        await destination.send(embed=embed, file=file)

    # ==== spells ====
    @commands.command()
    async def spell(self, ctx, *, name: str):
        """Looks up a spell."""
        choices = await lookuputils.get_spell_choices(ctx)
        spell = await lookuputils.search_entities(ctx, {"spell": choices}, name)

        return await self._spell(ctx, spell)

    @slash_lookup.sub_command(name="spell", description="Looks up a spell.")
    async def slash_spell(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.Spell = commands.Param(
            description="The spell you want to look up", converter=lookup_converter("spell")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Spell not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["spell"])
        return await self._spell(inter, name)

    @slash_spell.autocomplete("name")
    async def slash_spell_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        choices = await self._get_entities(inter, "spell", lookuputils.get_spell_choices)

        available_ids = {"spell": await self.bot.ddb.get_accessible_entities(inter, inter.author.id, "spell")}
        select_key = create_selectkey(available_ids)
        result, strict = search(choices, user_input, slash_match_key, 25)

        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _spell(self, ctx, spell: gamedata.spell):
        destination = await self._get_destination(ctx)

        if ctx.guild is not None:
            if hasattr(ctx, "get_server_settings"):
                guild_settings = await ctx.get_server_settings()
            else:
                guild_settings = await ServerSettings.for_guild(mdb=ctx.bot.mdb, guild_id=ctx.guild.id)
            pm = guild_settings.lookup_pm_result
        else:
            pm = False

        embed = EmbedWithAuthor(ctx)
        embed.url = spell.url
        color = embed.colour

        embed.title = spell.name
        school_level = (
            f"{spell.get_level()} {spell.get_school().lower()}"
            if spell.level > 0
            else f"{spell.get_school().lower()} cantrip"
        )
        embed.description = f"*{school_level}. ({', '.join(itertools.chain(spell.classes, spell.subclasses))})*"
        if spell.ritual:
            time = f"{spell.time} (ritual)"
        else:
            time = spell.time

        meta = (
            f"**Casting Time**: {time}\n"
            f"**Range**: {spell.range}\n"
            f"**Components**: {spell.components}\n"
            f"**Duration**: {spell.duration}"
        )
        embed.add_field(name="Meta", value=meta)

        higher_levels = spell.higherlevels
        pieces = chunk_text(spell.description)

        embed.add_field(name="Description", value=pieces[0], inline=False)

        embed_queue = [embed]
        if len(pieces) > 1:
            for i, piece in enumerate(pieces[1::2]):
                temp_embed = disnake.Embed()
                temp_embed.colour = color
                if (next_idx := (i + 1) * 2) < len(pieces):  # this is chunked into 1024 pieces, and descs can handle 2
                    temp_embed.description = piece + pieces[next_idx]
                else:
                    temp_embed.description = piece
                embed_queue.append(temp_embed)

        if higher_levels:
            add_fields_from_long_text(embed_queue[-1], "At Higher Levels", higher_levels)

        lookuputils.handle_source_footer(embed_queue[-1], spell, "Spell")
        if spell.image:
            embed_queue[0].set_thumbnail(url=spell.image)

        await Stats.increase_stat(ctx, "spells_looked_up_life")

        for i, embed in enumerate(embed_queue):
            if pm:
                await ctx.author.send(embed=embed)
            elif i == 0:
                # Ensure the first embed is sent as a reply
                await destination.send(embed=embed)
            else:
                # and the rest are to the channel
                await destination.channel.send(embed=embed)

    # ==== items ====
    @commands.command(name="item")
    async def item_lookup(self, ctx, *, name: str):
        """Looks up an item."""
        choices = await lookuputils.get_item_entitlement_choice_map(ctx)
        item = await lookuputils.search_entities(ctx, choices, name, query_type="item")

        return await self._item(ctx, item)

    @slash_lookup.sub_command(name="item", description="Looks up an item.")
    async def slash_item(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: gamedata.item = commands.Param(
            description="The item you want to look up", converter=lookup_converter("item")
        ),
    ):
        if isinstance(name, list):
            if not name:
                await inter.send("Item not found.", ephemeral=True)
                return
            name = name[0]
        await self._check_access(inter, name, ["adventuring-gear", "armor", "magic-item", "weapon"])
        return await self._item(inter, name)

    @slash_item.autocomplete("name")
    async def slash_item_auto(self, inter: disnake.ApplicationCommandInteraction, user_input: str):
        choices = await self._get_entities(inter, "item", lookuputils.get_item_entitlement_choice_map)

        choice_dict = {}
        for choice in choices:
            if choice.entity_type not in choice_dict:
                choice_dict[choice.entity_type] = []
            choice_dict[choice.entity_type].append(choice)

        available_ids = {k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in choice_dict}

        select_key = create_selectkey(available_ids)
        result, strict = search(choices, user_input, slash_match_key, 25)
        if strict:
            return [select_key(result, True)]
        return [select_key(r, True) for r in result][:25]

    async def _item(self, ctx, item: gamedata.item):
        """Looks up an item."""
        destination = await self._get_destination(ctx)
        embed = EmbedWithAuthor(ctx)

        embed.title = item.name
        embed.url = item.url
        embed.description = item.meta

        if item.attunement:
            if item.attunement is True:  # can be truthy, but not true
                embed.add_field(name="Attunement", value="Requires Attunement")
            else:
                embed.add_field(name="Attunement", value=f"Requires Attunement {item.attunement}", inline=False)

        text = trim_str(item.desc, 5500)
        add_fields_from_long_text(embed, "Description", text)

        if item.image:
            embed.set_thumbnail(url=item.image)

        lookuputils.handle_source_footer(embed, item, "Item")

        await Stats.increase_stat(ctx, "items_looked_up_life")
        await destination.send(embed=embed)

    # ==== server settings ====
    @commands.command(hidden=True)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def lookup_settings(self, ctx, *, args=""):
        """This command has been replaced by `!servsettings`. If you're used to it, it still works like before!"""
        guild_settings = await ctx.get_server_settings()
        if not args:
            settings_ui = ui.ServerSettingsUI.new(ctx.bot, owner=ctx.author, settings=guild_settings, guild=ctx.guild)
            await settings_ui.send_to(ctx)
            return

        # old deprecated CLI behaviour
        args = argparse(args)
        out = []
        if "req_dm_monster" in args:
            setting = get_positivity(args.last("req_dm_monster", True))
            guild_settings.lookup_dm_required = setting
            out.append(f"req_dm_monster set to {setting}!")
        if "pm_dm" in args:
            setting = get_positivity(args.last("pm_dm", True))
            guild_settings.lookup_pm_dm = setting
            out.append(f"pm_dm set to {setting}!")
        if "pm_result" in args:
            setting = get_positivity(args.last("pm_result", True))
            guild_settings.lookup_pm_result = setting
            out.append(f"pm_result set to {setting}!")

        if out:
            await guild_settings.commit(ctx.bot.mdb)
            await ctx.send("Lookup settings set:\n" + "\n".join(out))
        else:
            await ctx.send(f"No settings found. Try using `{ctx.prefix}lookup_settings` to open an interactive menu.")

    # ==== helpers ====
    @staticmethod
    async def _get_destination(ctx):
        guild_settings = None
        if hasattr(ctx, "get_server_settings"):
            guild_settings = await ctx.get_server_settings()
            slash_command = False
        else:
            if ctx.guild is not None:
                guild_settings = await ServerSettings.for_guild(mdb=ctx.bot.mdb, guild_id=ctx.guild.id)
            slash_command = True
        if guild_settings is None:
            return ctx
        if slash_command and guild_settings.lookup_pm_result:
            dm_link = await ctx.author.create_dm()
            await ctx.send(f"Result sent to your [Direct Messages]({dm_link.jump_url})", ephemeral=True)
        return ctx.author if guild_settings.lookup_pm_result else ctx

    async def _check_access(self, inter, entity: Sourced, entity_choices: list[str]):
        available_ids = {
            k: await self.bot.ddb.get_accessible_entities(inter, inter.author.id, k) for k in entity_choices
        }
        if not can_access(entity, available_ids[entity.entitlement_entity_type]):
            raise RequiresLicense(entity, available_ids[entity.entitlement_entity_type] is not None)

    async def _get_entities(self, ctx, entity_type, entity_source):
        """
        Caches a minimal version of each entity of a given type available to a user for a particular context
        """
        if ctx.guild is None:
            key = f"{entity_type}.{ctx.author.id}"
        else:
            key = f"{entity_type}.{ctx.guild.id}.{ctx.author.id}"

        # L1: Memory
        l1_entity_cache = ENTITY_CACHE.get(key)
        if l1_entity_cache is not None:
            log.debug("found available entities in l1 (memory) cache")
            return l1_entity_cache

        # L2: Redis
        l2_entity_cache = await ctx.bot.rdb.jget(key)
        if l2_entity_cache is not None:
            log.debug("found available entities in l2 (redis) cache")
            return [CachedSourced.from_dict(e) for e in l2_entity_cache]

        # fetch it all
        available_entities = await entity_source(ctx)

        # Items have 4 entity types and as such return a dict
        if isinstance(available_entities, dict):
            available_entities = list(itertools.chain.from_iterable(available_entities.values()))

        converted_entities = [
            CachedSourced(
                name=e.name,
                entity_type=e.entity_type,
                has_image=False if entity_type != "monster" else bool(e.image_url),
                has_token=False if entity_type != "monster" else bool(e.token_free_fp or e.token_sub_fp),
                source=e.source,
                homebrew=e.homebrew,
                entity_id=e.entity_id,
                is_free=e.is_free,
                is_legacy=e.is_legacy,
                rulesVersion=e.rulesVersion,
            )
            for e in available_entities
        ]

        # cache monsters
        ENTITY_CACHE[key] = converted_entities
        await self.bot.rdb.jsetex(key, [m.to_dict() for m in converted_entities], ENTITY_TTL)
        return converted_entities

    async def clear_cache(self, ctx, entity_type):
        if ctx.guild is None:
            key = f"{entity_type}.{ctx.author.id}"
        else:
            key = f"{entity_type}.{ctx.guild.id}.{ctx.author.id}"
        if key in ENTITY_CACHE:
            del ENTITY_CACHE[key]
        await self.bot.rdb.delete(key)

    # ==== listeners ====
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # This method automatically allows full monster lookup for new large servers.
        # These settings can be changed by any server admin.
        existing_guild_settings = await utils.settings.ServerSettings.for_guild(self.bot.mdb, guild.id)
        if existing_guild_settings is not None:
            return

        if guild.member_count >= LARGE_THRESHOLD:
            guild_settings = utils.settings.ServerSettings(guild_id=guild.id, lookup_dm_required=False)
            await guild_settings.commit(self.bot.mdb)


def setup(bot):
    bot.add_cog(Lookup(bot))
