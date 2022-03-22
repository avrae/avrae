"""
Created on Nov 29, 2016

@author: andrew
"""
import itertools

import discord
from discord.ext import commands

import gamedata
import ui
import utils.settings
from cogs5e.models import errors
from cogs5e.models.embeds import EmbedWithAuthor, add_fields_from_long_text, set_maybe_long_desc
from cogsmisc.stats import Stats
from gamedata.compendium import compendium
from gamedata.klass import ClassFeature
from gamedata.lookuputils import (HOMEBREW_EMOJI, available, can_access, get_item_choices, get_monster_choices,
    get_spell_choices, handle_source_footer)
from gamedata.race import RaceFeature
from utils import checks, img
from utils.argparser import argparse
from utils.functions import chunk_text, get_positivity, search_and_select, smart_trim, trim_str

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
            embed.add_field(
                name=actiontype['fullName'], value=', '.join(a['name'] for a in actiontype['items']),
                inline=False
            )

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
    async def condition(self, ctx, *, name: str = None):
        """Looks up a condition."""
        if not name:
            name = 'condition'
        else:
            name = f"Condition: {name}"
        # this is an invoke instead of an alias to make more sense in docs
        await self.rule(ctx, name=name)

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
        result: RaceFeature = await self._lookup_search3(
            ctx,
            {'race': compendium.rfeats, 'subrace': compendium.subrfeats},
            name, 'racefeat'
        )

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.url = result.url
        set_maybe_long_desc(embed, result.text)
        handle_source_footer(embed, result, "Race Feature")

        await (await self._get_destination(ctx)).send(embed=embed)

    @commands.command()
    async def race(self, ctx, *, name: str):
        """Looks up a race."""
        result: gamedata.Race = await self._lookup_search3(
            ctx,
            {'race': compendium.races, 'subrace': compendium.subraces},
            name, 'race'
        )

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
        result: ClassFeature = await self._lookup_search3(
            ctx,
            {'class': compendium.cfeats, 'class-feature': compendium.optional_cfeats},
            name, query_type='classfeat'
        )

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
                level_features = result.levels[level - 1]
                feature_names = [feature.name for feature in level_features]
                if level in result.subclass_feature_levels:
                    feature_names.append(f"{result.subclass_title} Feature")
                levels.append(', '.join(feature_names))

            level_features_str = ""
            for i, l in enumerate(levels):
                level_features_str += f"`{i + 1}` {l}\n"
            embed.description = level_features_str

            available_ocfs = await available(ctx, result.optional_features, entity_type='class-feature')
            if available_ocfs:
                ocf_names = ', '.join(ocf.name for ocf in available_ocfs)
                embed.add_field(name="Optional Class Features", value=ocf_names, inline=False)

            embed.add_field(name="Starting Proficiencies", value=result.proficiencies, inline=False)
            embed.add_field(name="Starting Equipment", value=result.equipment, inline=False)

            handle_source_footer(
                embed, result, f"Use {ctx.prefix}classfeat to look up a feature.",
                add_source_str=False
            )
        else:
            embed.title = f"{result.name}, Level {level}"

            level_features = result.levels[level - 1]

            for resource, value in zip(result.table.headers, result.table.levels[level - 1]):
                if value != '0':
                    embed.add_field(name=resource, value=value)

            for f in level_features:
                embed.add_field(name=f.name, value=trim_str(f.text, 1024), inline=False)

            handle_source_footer(
                embed, result, f"Use {ctx.prefix}classfeat to look up a feature if it is cut off.",
                add_source_str=False
            )

        await (await self._get_destination(ctx)).send(embed=embed)

    @commands.command()
    async def subclass(self, ctx, *, name: str):
        """Looks up a subclass."""
        result: gamedata.Subclass = await self._lookup_search3(
            ctx, {'class': compendium.subclasses}, name,
            query_type='subclass'
        )

        embed = EmbedWithAuthor(ctx)
        embed.url = result.url
        embed.title = result.name
        embed.description = smart_trim(result.description, 2048)

        for level in result.levels:
            for feature in level:
                text = smart_trim(feature.text, 1024)
                embed.add_field(name=feature.name, value=text, inline=False)

        handle_source_footer(
            embed, result, f"Use {ctx.prefix}classfeat to look up a feature if it is cut off",
            add_source_str=True
        )

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
            pm_dm = guild_settings.lookup_pm_dm
            req_dm_monster = guild_settings.lookup_dm_required
            visible = (not req_dm_monster) or guild_settings.is_dm(ctx.author)
        else:
            pm = False
            pm_dm = False
            req_dm_monster = False
            visible = True

        # #1735 -h arg for monster lookup
        image_args = argparse(name)
        hide_name = image_args.get("h", False, bool)
        name = name.replace(" -h", "").rstrip()

        if visible:
            visible = visible and not hide_name

        choices = await get_monster_choices(ctx, filter_by_license=False)
        monster = await self._lookup_search3(ctx, {'monster': choices}, name)

        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour

        embed_queue[-1].title = monster.name if not hide_name else ''
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
                trait_all = chunk_text(desc, max_chunk_size=2048)
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
            if monster.bonus_actions:
                bonus_action = '\n\n'.join(f"**{a.name}:** {a.desc}" for a in monster.bonus_actions)
                if bonus_action:
                    safe_append("Bonus Actions", bonus_action)
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
            if monster.mythic_actions:
                mythic_action = '\n\n'.join(f"**{a.name}:** {a.desc}" for a in monster.mythic_actions)
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

            embed_queue[-1].description = f"{size} {_type}.\n" \
                                          f"**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {monster.speed}\n" \
                                          f"{monster.get_hidden_stat_array()}\n" \
                                          f"**Languages:** {languages}\n"

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

        handle_source_footer(embed_queue[-1], monster, "Creature")

        embed_queue[0].set_thumbnail(url=monster.get_image_url())
        await Stats.increase_stat(ctx, "monsters_looked_up_life")
        for embed in embed_queue:
            if pm or (visible and pm_dm and req_dm_monster):
                await ctx.author.send(embed=embed)
            else:
                await ctx.send(embed=embed)

    @commands.command()
    async def monimage(self, ctx, *, name: str):
        """Shows a monster's image."""
        # #1735 -h arg for monster lookup
        image_args = argparse(name)
        hide_name = image_args.get("h", False, bool)
        name = name.replace(" -h", "").rstrip()

        choices = await get_monster_choices(ctx, filter_by_license=False)
        monster = await self._lookup_search3(ctx, {'monster': choices}, name)
        await Stats.increase_stat(ctx, "monsters_looked_up_life")

        url = monster.get_image_url()
        embed = EmbedWithAuthor(ctx)
        embed.title = monster.name if not hide_name else ""
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

        higher_levels = spell.higherlevels
        pieces = chunk_text(spell.description)

        embed.add_field(name="Description", value=pieces[0], inline=False)

        embed_queue = [embed]
        if len(pieces) > 1:
            for i, piece in enumerate(pieces[1::2]):
                temp_embed = discord.Embed()
                temp_embed.colour = color
                if (next_idx := (i + 1) * 2) < len(pieces):  # this is chunked into 1024 pieces, and descs can handle 2
                    temp_embed.description = piece + pieces[next_idx]
                else:
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
                embed.add_field(name="Attunement", value="Requires Attunement")
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
    @commands.command(hidden=True)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def lookup_settings(self, ctx, *args):
        """This command has been replaced by `!servsettings`. If you're used to it, it still works like before!"""
        guild_settings = await ctx.get_server_settings()
        if not args:
            settings_ui = ui.ServerSettingsUI.new(ctx.bot, owner=ctx.author, settings=guild_settings, guild=ctx.guild)
            await settings_ui.send_to(ctx)
            return

        # old deprecated CLI behaviour
        args = argparse(args)
        out = []
        if 'req_dm_monster' in args:
            setting = get_positivity(args.last('req_dm_monster', True))
            guild_settings.lookup_dm_required = setting
            out.append(f'req_dm_monster set to {setting}!')
        if 'pm_dm' in args:
            setting = get_positivity(args.last('pm_dm', True))
            guild_settings.lookup_pm_dm = setting
            out.append(f'pm_dm set to {setting}!')
        if 'pm_result' in args:
            setting = get_positivity(args.last('pm_result', True))
            guild_settings.lookup_pm_result = setting
            out.append(f'pm_result set to {setting}!')

        if out:
            await guild_settings.commit(ctx.bot.mdb)
            await ctx.send("Lookup settings set:\n" + '\n'.join(out))
        else:
            await ctx.send(f"No settings found. Try using `{ctx.prefix}lookup_settings` to open an interactive menu.")

    # ==== helpers ====
    async def _add_training_data(self, lookup_type, query, result_name, metadata=None, srd=True, could_view=True):
        data = {"type": lookup_type, "query": query, "result": result_name, "srd": srd, "could_view": could_view}
        if metadata:
            data['given_options'] = metadata.get('num_options', 1)
            data['chosen_index'] = metadata.get('chosen_index', 0)
            data['homebrew'] = metadata.get('homebrew', False)
        await self.bot.mdb.nn_training.insert_one(data)

    @staticmethod
    async def _get_destination(ctx):
        guild_settings = await ctx.get_server_settings()
        if guild_settings is None:
            return ctx
        return ctx.author if guild_settings.lookup_pm_result else ctx

    async def _lookup_search3(self, ctx, entities, query, query_type=None):
        """
        :type ctx: discord.ext.commands.Context
        :param entities: A dict mapping entitlements entity types to the entities themselves.
        :type entities: dict[str, list[T]]
        :type query: str
        :param str query_type: The type of the object being queried for (default entity type if only one dict key)
        :rtype: T
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
        for entity_entitlement_type, es in entities.items():
            for entity in es:
                choices.append((entity, entity_entitlement_type))  # entity, entity type

        result, metadata = await search_and_select(
            ctx, choices, query, lambda e: e[0].name, return_metadata=True,
            selectkey=selectkey
        )

        # get the entity
        entity, entity_entitlement_type = result

        # log the query
        await self._add_training_data(
            query_type, query, entity.name, metadata=metadata, srd=entity.is_free,
            could_view=can_access(entity, available_ids[entity_entitlement_type])
        )

        # display error if not srd
        if not can_access(entity, available_ids[entity_entitlement_type]):
            raise errors.RequiresLicense(entity, available_ids[entity_entitlement_type] is not None)
        return entity

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
