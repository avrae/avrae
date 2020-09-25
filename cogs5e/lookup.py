"""
Created on Nov 29, 2016

@author: andrew
"""
import itertools

import discord
from discord.ext import commands

import gamedata
from cogs5e.models import errors
from cogs5e.models.embeds import EmbedWithAuthor, add_fields_from_long_text, set_maybe_long_desc
from cogsmisc.stats import Stats
from gamedata.compendium import compendium
from gamedata.lookuputils import HOMEBREW_EMOJI, can_access, get_item_choices, get_monster_choices, get_spell_choices, \
    handle_source_footer
from gamedata.shared import SourcedTrait
from utils import checks, img
from utils.argparser import argparse
from utils.functions import get_positivity, search_and_select, trim_str

LARGE_THRESHOLD = 200


class Lookup(commands.Cog):
    """Commands to help look up items, status effects, rules, etc."""

    def __init__(self, bot):
        self.bot = bot

    # ==== rules/references ====
    @staticmethod
    async def _show_reference_options(ctx, destination):
        embed = EmbedWithAuthor(ctx)
        embed.title = "Rules"
        categories = ', '.join(a['type'] for a in compendium.rule_references)
        embed.description = f"Use `{ctx.prefix}{ctx.invoked_with} <category>` to look at all actions of " \
                            f"a certain type.\nCategories: {categories}"

        for actiontype in compendium.rule_references:
            embed.add_field(name=actiontype['fullName'], value=', '.join(a['name'] for a in actiontype['items']),
                            inline=False)

        await destination.send(embed=embed)

    @staticmethod
    async def _show_action_options(ctx, actiontype, destination):
        embed = EmbedWithAuthor(ctx)
        embed.title = actiontype['fullName']

        actions = []
        for action in actiontype['items']:
            actions.append(f"**{action['name']}** - *{action['short']}*")

        embed.description = '\n'.join(actions)
        await destination.send(embed=embed)

    @commands.command(aliases=['status'])
    async def condition(self, ctx, *, name: str):
        """Looks up a condition."""
        # this is an invoke instead of an alias to make more sense in docs
        await self.rule(ctx, name=f"Condition: {name}")

    @commands.command(aliases=['reference'])
    async def rule(self, ctx, *, name: str = None):
        """Looks up a rule."""
        destination = await self._get_destination(ctx)

        if name is None:
            return await self._show_reference_options(ctx, destination)

        options = []
        for actiontype in compendium.rule_references:
            if name == actiontype['type']:
                return await self._show_action_options(ctx, actiontype, destination)
            else:
                options.extend(actiontype['items'])

        result, metadata = await search_and_select(ctx, options, name, lambda e: e['fullName'], return_metadata=True)
        await self._add_training_data("reference", name, result['fullName'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['fullName']
        embed.description = f"*{result['short']}*"
        add_fields_from_long_text(embed, "Description", result['desc'])
        embed.set_footer(text=f"Rule | {result['source']}")

        await destination.send(embed=embed)

    # ==== feats ====
    @commands.command()
    async def feat(self, ctx, *, name: str):
        """Looks up a feat."""
        result: gamedata.Feat = await self._lookup_search3(ctx, {'feat': compendium.feats}, name)

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        if result.prerequisite:
            embed.add_field(name="Prerequisite", value=result.prerequisite, inline=False)
        add_fields_from_long_text(embed, "Description", result.desc)
        handle_source_footer(embed, result, "Feat")
        await (await self._get_destination(ctx)).send(embed=embed)

    # ==== races / racefeats ====
    @commands.command()
    async def racefeat(self, ctx, *, name: str):
        """Looks up a racial feature."""
        result: SourcedTrait = await self._lookup_search3(ctx,
                                                          {'race': compendium.rfeats, 'subrace': compendium.subrfeats},
                                                          name, 'racefeat')

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        set_maybe_long_desc(embed, result.text)
        handle_source_footer(embed, result, "Race Feature")

        await (await self._get_destination(ctx)).send(embed=embed)

    @commands.command()
    async def race(self, ctx, *, name: str):
        """Looks up a race."""
        result: gamedata.Race = await self._lookup_search3(ctx,
                                                           {'race': compendium.races, 'subrace': compendium.subraces},
                                                           name, 'race')

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        embed.add_field(name="Speed", value=result.speed)
        embed.add_field(name="Size", value=result.size)
        for t in result.traits:
            add_fields_from_long_text(embed, t.name, t.text)
        handle_source_footer(embed, result, "Race")
        await (await self._get_destination(ctx)).send(embed=embed)

    # ==== classes / classfeats ====
    @commands.command()
    async def classfeat(self, ctx, *, name: str):
        """Looks up a class feature."""
        result: SourcedTrait = await self._lookup_search3(ctx, {'class': compendium.cfeats}, name,
                                                          query_type='classfeat')

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        set_maybe_long_desc(embed, result.text)
        handle_source_footer(embed, result, "Class Feature")

        await (await self._get_destination(ctx)).send(embed=embed)

    @commands.command(name='class')
    async def _class(self, ctx, name: str, level: int = None):
        """Looks up a class, or all features of a certain level."""
        if level is not None and not 0 < level < 21:
            return await ctx.send("Invalid level.")

        result: gamedata.Class = await self._lookup_search3(ctx, {'class': compendium.classes}, name)

        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        if level is None:
            embed.title = result.name
            embed.add_field(name="Hit Points", value=result.hit_points)

            levels = []
            for level in range(1, 21):
                level = result.levels[level - 1]
                levels.append(', '.join([feature.name for feature in level]))

            embed.add_field(name="Starting Proficiencies", value=result.proficiencies, inline=False)
            embed.add_field(name="Starting Equipment", value=result.equipment, inline=False)

            level_features_str = ""
            for i, l in enumerate(levels):
                level_features_str += f"`{i + 1}` {l}\n"
            embed.description = level_features_str

            handle_source_footer(embed, result, f"Use {ctx.prefix}classfeat to look up a feature.",
                                 add_source_str=False)
        else:
            embed.title = f"{result.name}, Level {level}"

            level_features = result.levels[level - 1]

            for resource, value in zip(result.table.headers, result.table.levels[level - 1]):
                if value != '0':
                    embed.add_field(name=resource, value=value)

            for f in level_features:
                embed.add_field(name=f.name, value=trim_str(f.text, 1024), inline=False)

            handle_source_footer(embed, result, f"Use {ctx.prefix}classfeat to look up a feature if it is cut off.",
                                 add_source_str=False)

        await (await self._get_destination(ctx)).send(embed=embed)

    @commands.command()
    async def subclass(self, ctx, *, name: str):
        """Looks up a subclass."""
        result: gamedata.Subclass = await self._lookup_search3(ctx, {'class': compendium.subclasses}, name,
                                                               query_type='subclass')

        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        embed.title = result.name
        embed.description = f"*Source: {result.source_str()}*"

        for level in result.levels:
            for feature in level:
                text = trim_str(feature.text, 1024)
                embed.add_field(name=feature.name, value=text, inline=False)

        handle_source_footer(embed, result, f"Use {ctx.prefix}classfeat to look up a feature if it is cut off.",
                             add_source_str=False)

        await (await self._get_destination(ctx)).send(embed=embed)

    # ==== backgrounds ====
    @commands.command()
    async def background(self, ctx, *, name: str):
        """Looks up a background."""
        result: gamedata.Background = await self._lookup_search3(ctx, {'background': compendium.backgrounds}, name)

        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        embed.title = result.name
        handle_source_footer(embed, result, "Background")

        for trait in result.traits:
            text = trim_str(trait.text, 1024)
            embed.add_field(name=trait.name, value=text, inline=False)

        await (await self._get_destination(ctx)).send(embed=embed)

    # ==== monsters ====
    @commands.command()
    async def monster(self, ctx, *, name: str):
        """Looks up a monster.
        Generally requires a Game Master role to show full stat block.
        Game Master Roles: GM, DM, Game Master, Dungeon Master
        __Valid Arguments__
        -h - Shows the obfuscated stat block, even if you can see the full stat block."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        pm_dm = guild_settings.get("pm_dm", False)
        req_dm_monster = guild_settings.get("req_dm_monster", True)

        visible_roles = {'gm', 'game master', 'dm', 'dungeon master'}
        if req_dm_monster and ctx.guild:
            visible = True if visible_roles.intersection(set(str(r).lower() for r in ctx.author.roles)) else False
        else:
            visible = True

        # #817 -h arg for monster lookup
        if name.endswith(' -h'):
            name = name[:-3]
            visible = False

        choices = await get_monster_choices(ctx, filter_by_license=False)
        monster = await self._lookup_search3(ctx, {'monster': choices}, name)

        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour

        embed_queue[-1].title = monster.name
        embed_queue[-1].url = monster.url

        def safe_append(title, desc):
            if len(desc) < 1024:
                embed_queue[-1].add_field(name=title, value=desc, inline=False)
            elif len(desc) < 2048:
                # noinspection PyTypeChecker
                # I'm adding an Embed to a list of Embeds, shut up.
                embed_queue.append(discord.Embed(colour=color, description=desc, title=title))
            else:
                # noinspection PyTypeChecker
                embed_queue.append(discord.Embed(colour=color, title=title))
                trait_all = [desc[i:i + 2040] for i in range(0, len(desc), 2040)]
                embed_queue[-1].description = trait_all[0]
                for t in trait_all[1:]:
                    # noinspection PyTypeChecker
                    embed_queue.append(discord.Embed(colour=color, description=t))

        if visible:
            embed_queue[-1].description = monster.get_meta()
            if monster.traits:
                trait = '\n\n'.join(f"**{a.name}:** {a.desc}" for a in monster.traits)
                if trait:
                    safe_append("Special Abilities", trait)
            if monster.actions:
                action = '\n\n'.join(f"**{a.name}:** {a.desc}" for a in monster.actions)
                if action:
                    safe_append("Actions", action)
            if monster.reactions:
                reaction = '\n\n'.join(f"**{a.name}:** {a.desc}" for a in monster.reactions)
                if reaction:
                    safe_append("Reactions", reaction)
            if monster.legactions:
                proper_name = f'The {monster.name}' if not monster.proper else monster.name
                legendary = [f"{proper_name} can take {monster.la_per_round} legendary actions, choosing from "
                             f"the options below. Only one legendary action can be used at a time and only at the "
                             f"end of another creature's turn. {proper_name} regains spent legendary actions at "
                             f"the start of its turn."]
                for a in monster.legactions:
                    if a.name:
                        legendary.append(f"**{a.name}:** {a.desc}")
                    else:
                        legendary.append(a.desc)
                if legendary:
                    safe_append("Legendary Actions", '\n\n'.join(legendary))

        else:
            hp = monster.hp
            ac = monster.ac
            size = monster.size
            _type = monster.race
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

            embed_queue[-1].description = f"{size} {_type}.\n" \
                                          f"**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {monster.speed}\n" \
                                          f"{monster.get_hidden_stat_array()}\n" \
                                          f"**Languages:** {languages}\n"

            if monster.traits:
                embed_queue[-1].add_field(name="Special Abilities", value=str(len(monster.traits)))

            if monster.actions:
                embed_queue[-1].add_field(name="Actions", value=str(len(monster.actions)))

            if monster.reactions:
                embed_queue[-1].add_field(name="Reactions", value=str(len(monster.reactions)))

            if monster.legactions:
                embed_queue[-1].add_field(name="Legendary Actions", value=str(len(monster.legactions)))

        handle_source_footer(embed_queue[-1], monster, "Creature")

        embed_queue[0].set_thumbnail(url=monster.get_image_url())
        await Stats.increase_stat(ctx, "monsters_looked_up_life")
        for embed in embed_queue:
            if pm or (visible and pm_dm and req_dm_monster):
                await ctx.author.send(embed=embed)
            else:
                await ctx.send(embed=embed)

    @commands.command()
    async def monimage(self, ctx, *, name):
        """Shows a monster's image."""
        choices = await get_monster_choices(ctx, filter_by_license=False)
        monster = await self._lookup_search3(ctx, {'monster': choices}, name)
        await Stats.increase_stat(ctx, "monsters_looked_up_life")

        url = monster.get_image_url()
        embed = EmbedWithAuthor(ctx)
        embed.title = monster.name
        embed.description = f"{monster.size} monster."

        if not url:
            return await ctx.channel.send("This monster has no image.")

        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.command()
    async def token(self, ctx, name=None, *args):
        """
        Shows a monster or your character's token.
        __Valid Arguments__
        -border <plain|none (player token only)> - Overrides the token border.
        """
        if name is None or name.startswith('-'):
            token_cmd = self.bot.get_command('playertoken')
            if token_cmd is None:
                return await ctx.send("Error: SheetManager cog not loaded.")
            if name:
                args = (name, *args)
            return await ctx.invoke(token_cmd, *args)

        # select monster
        choices = await get_monster_choices(ctx, filter_by_license=False)
        monster = await self._lookup_search3(ctx, {'monster': choices}, name)
        await Stats.increase_stat(ctx, "monsters_looked_up_life")

        # select border
        ddb_user = await self.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        is_subscriber = ddb_user and ddb_user.is_subscriber
        token_args = argparse(args)

        if monster.homebrew:
            # homebrew: generate token
            if not monster.get_image_url():
                return await ctx.send("This monster has no image.")
            try:
                image = await img.generate_token(monster.get_image_url(), is_subscriber, token_args)
            except Exception as e:
                return await ctx.send(f"Error generating token: {e}")
        else:
            # official monsters
            token_url = monster.get_token_url(is_subscriber)
            if token_args.last('border') == 'plain':
                token_url = monster.get_token_url(False)

            if not token_url:
                return await ctx.send("This monster has no image.")

            image = await img.fetch_monster_image(token_url)

        embed = EmbedWithAuthor(ctx)
        embed.title = monster.name
        embed.description = f"{monster.size} monster."

        file = discord.File(image, filename="image.png")
        embed.set_image(url="attachment://image.png")
        await ctx.send(embed=embed, file=file)

    # ==== spells ====
    @commands.command()
    async def spell(self, ctx, *, name: str):
        """Looks up a spell."""
        choices = await get_spell_choices(ctx, filter_by_license=False)
        spell = await self._lookup_search3(ctx, {'spell': choices}, name)

        embed = EmbedWithAuthor(ctx)
        embed.url = spell.url
        color = embed.colour

        embed.title = spell.name
        school_level = f"{spell.get_level()} {spell.get_school().lower()}" if spell.level > 0 \
            else f"{spell.get_school().lower()} cantrip"
        embed.description = f"*{school_level}. " \
                            f"({', '.join(itertools.chain(spell.classes, spell.subclasses))})*"
        if spell.ritual:
            time = f"{spell.time} (ritual)"
        else:
            time = spell.time

        meta = f"**Casting Time**: {time}\n" \
               f"**Range**: {spell.range}\n" \
               f"**Components**: {spell.components}\n" \
               f"**Duration**: {spell.duration}"
        embed.add_field(name="Meta", value=meta)

        text = spell.description
        higher_levels = spell.higherlevels

        if len(text) > 1020:
            pieces = [text[:1020]] + [text[i:i + 2040] for i in range(1020, len(text), 2040)]
        else:
            pieces = [text]

        embed.add_field(name="Description", value=pieces[0], inline=False)

        embed_queue = [embed]
        if len(pieces) > 1:
            for piece in pieces[1:]:
                temp_embed = discord.Embed()
                temp_embed.colour = color
                temp_embed.description = piece
                embed_queue.append(temp_embed)

        if higher_levels:
            add_fields_from_long_text(embed_queue[-1], "At Higher Levels", higher_levels)

        handle_source_footer(embed_queue[-1], spell, "Spell")
        if spell.image:
            embed_queue[0].set_thumbnail(url=spell.image)

        await Stats.increase_stat(ctx, "spells_looked_up_life")
        destination = await self._get_destination(ctx)
        for embed in embed_queue:
            await destination.send(embed=embed)

    # ==== items ====
    @commands.command(name='item')
    async def item_lookup(self, ctx, *, name):
        """Looks up an item."""
        choices = await get_item_choices(ctx, filter_by_license=False)
        item = await self._lookup_search3(ctx, {'magic-item': choices}, name, query_type='item')

        embed = EmbedWithAuthor(ctx)

        embed.title = item.name
        embed.url = item.url
        embed.description = item.meta

        if item.attunement:
            if item.attunement is True:  # can be truthy, but not true
                embed.add_field(name="Attunement", value=f"Requires Attunement")
            else:
                embed.add_field(name="Attunement", value=f"Requires Attunement {item.attunement}", inline=False)

        text = trim_str(item.desc, 5500)
        add_fields_from_long_text(embed, "Description", text)

        if item.image:
            embed.set_thumbnail(url=item.image)

        handle_source_footer(embed, item, "Item")

        await Stats.increase_stat(ctx, "items_looked_up_life")
        await (await self._get_destination(ctx)).send(embed=embed)

    # ==== server settings ====
    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def lookup_settings(self, ctx, *args):
        """Changes settings for the lookup module.
        __Valid Settings__
        -req_dm_monster [True/False] - Requires a Game Master role to show a full monster stat block.
            -pm_dm [True/False] - PMs a DM the full monster stat block instead of outputting to chat, if req_dm_monster is True.
        -pm_result [True/False] - PMs the result of the lookup to reduce spam.
        """
        guild_id = str(ctx.guild.id)
        guild_settings = await self.bot.mdb.lookupsettings.find_one({"server": guild_id})
        if guild_settings is None:
            guild_settings = {}
        out = ""
        if '-req_dm_monster' in args:
            try:
                setting = args[args.index('-req_dm_monster') + 1]
            except IndexError:
                setting = 'True'
            setting = get_positivity(setting)
            guild_settings['req_dm_monster'] = setting if setting is not None else True
            out += 'req_dm_monster set to {}!\n'.format(str(guild_settings['req_dm_monster']))
        if '-pm_dm' in args:
            try:
                setting = args[args.index('-pm_dm') + 1]
            except IndexError:
                setting = 'True'
            setting = get_positivity(setting)
            guild_settings['pm_dm'] = setting if setting is not None else True
            out += 'pm_dm set to {}!\n'.format(str(guild_settings['pm_dm']))
        if '-pm_result' in args:
            try:
                setting = args[args.index('-pm_result') + 1]
            except IndexError:
                setting = 'False'
            setting = get_positivity(setting)
            guild_settings['pm_result'] = setting if setting is not None else False
            out += 'pm_result set to {}!\n'.format(str(guild_settings['pm_result']))

        if guild_settings:
            await self.bot.mdb.lookupsettings.update_one({"server": guild_id}, {"$set": guild_settings}, upsert=True)
            await ctx.send("Lookup settings set:\n" + out)
        else:
            await ctx.send("No settings found. Make sure your syntax is correct.")

    # ==== helpers ====
    async def get_settings(self, guild):
        settings = {}  # default PM settings
        if guild is not None:
            settings = await self.bot.mdb.lookupsettings.find_one({"server": str(guild.id)})
        return settings or {}

    async def _add_training_data(self, lookup_type, query, result_name, metadata=None, srd=True, could_view=True):
        data = {"type": lookup_type, "query": query, "result": result_name, "srd": srd, "could_view": could_view}
        if metadata:
            data['given_options'] = metadata.get('num_options', 1)
            data['chosen_index'] = metadata.get('chosen_index', 0)
            data['homebrew'] = metadata.get('homebrew', False)
        await self.bot.mdb.nn_training.insert_one(data)

    async def _get_destination(self, ctx):
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        return ctx.author if pm else ctx.channel

    async def _lookup_search3(self, ctx, entities, query, query_type=None):
        """
        :type ctx: discord.ext.commands.Context
        :param entities: A dict mapping entitlements entity types to the entities themselves.
        :type entities: dict[str, list[gamedata.shared.Sourced]]
        :type query: str
        :param str query_type: The type of the object being queried for (default entity type if only one dict key)
        :rtype: gamedata.shared.Sourced
        :raises: RequiresLicense if an entity that requires a license is selected
        """
        # sanity checks
        if len(entities) == 0:
            raise ValueError("At least 1 entity type must be passed in")
        if query_type is None and len(entities) != 1:
            raise ValueError("Query type must be passed for multiple entity types")
        elif query_type is None:
            query_type = list(entities.keys())[0]

        # this may take a while, so type
        await ctx.trigger_typing()

        # get licensed objects, mapped by entity type
        available_ids = {k: await self.bot.ddb.get_accessible_entities(ctx, ctx.author.id, k) for k in entities}

        # the selection display key
        def selectkey(e):
            the_entity, the_etype = e
            if the_entity.homebrew:
                return f"{the_entity.name} ({HOMEBREW_EMOJI})"
            elif can_access(the_entity, available_ids[the_etype]):
                return the_entity.name
            return f"{the_entity.name}\\*"

        # get the object
        choices = []
        for etype, es in entities.items():
            for entity in es:
                choices.append((entity, etype))  # entity, entity type

        result, metadata = await search_and_select(
            ctx, choices, query, lambda e: e[0].name, return_metadata=True,
            selectkey=selectkey)

        # get the entity
        entity, entity_type = result

        # log the query
        await self._add_training_data(query_type, query, entity.name, metadata=metadata, srd=entity.is_free,
                                      could_view=can_access(entity, available_ids[entity_type]))

        # display error if not srd
        if not can_access(entity, available_ids[entity_type]):
            raise errors.RequiresLicense(entity, available_ids[entity_type] is not None)
        return entity

    # ==== various listeners ====
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # This method automatically allows full monster lookup for new large servers.
        # These settings can be changed by any server admin.
        existing_guild_settings = await self.bot.mdb.lookupsettings.find_one({"server": str(guild.id)})
        if existing_guild_settings is not None:
            return

        if guild.member_count >= LARGE_THRESHOLD:
            default_guild_settings = {"req_dm_monster": False}
            await self.bot.mdb.lookupsettings.update_one({"server": str(guild.id)}, {"$set": default_guild_settings},
                                                         upsert=True)


def setup(bot):
    bot.add_cog(Lookup(bot))
