"""
Created on Nov 29, 2016

@author: andrew
"""
import itertools
import textwrap

import discord
from discord.ext import commands

from cogs5e.funcs.lookupFuncs import HOMEBREW_EMOJI, HOMEBREW_ICON, compendium, select_monster_full, select_spell_full
from cogs5e.models.embeds import EmbedWithAuthor, add_fields_from_long_text, add_homebrew_footer, set_maybe_long_desc
from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew.pack import Pack
from cogsmisc.stats import Stats
from utils import checks
from utils.functions import ABILITY_MAP, generate_token, get_positivity, parse_data_entry, search_and_select

CLASS_RESOURCE_MAP = {'slots': "Spell Slots",  # a weird one - see fighter
                      'spellsknown': "Spells Known",
                      'rages': "Rages", 'ragedamage': "Rage Damage",
                      'martialarts': "Martial Arts", 'kipoints': "Ki", 'unarmoredmovement': "Unarmored Movement",
                      'sorcerypoints': "Sorcery Points", 'sneakattack': "Sneak Attack",
                      'invocationsknown': "Invocations Known", 'spellslots': "Spell Slots", 'slotlevel': "Slot Level",
                      'talentsknown': "Talents Known", 'disciplinesknown': "Disciplines Known",
                      'psipoints': "Psi Points", 'psilimit': "Psi Limit"}

ITEM_TYPES = {"G": "Adventuring Gear", "SCF": "Spellcasting Focus", "AT": "Artisan Tool", "T": "Tool",
              "GS": "Gaming Set", "INS": "Instrument", "A": "Ammunition", "M": "Melee Weapon", "R": "Ranged Weapon",
              "LA": "Light Armor", "MA": "Medium Armor", "HA": "Heavy Armor", "S": "Shield", "W": "Wondrous Item",
              "P": "Potion", "ST": "Staff", "RD": "Rod", "RG": "Ring", "WD": "Wand", "SC": "Scroll", "EXP": "Explosive",
              "GUN": "Firearm", "SIMW": "Simple Weapon", "MARW": "Martial Weapon", "$": "Valuable Object",
              'TAH': "Tack and Harness", 'TG': "Trade Goods", 'MNT': "Mount", 'VEH': "Vehicle", 'SHP': "Ship",
              'GV': "Generic Variant", 'AF': "Futuristic", 'siege weapon': "Siege Weapon", 'generic': "Generic"}

DMGTYPES = {"B": "bludgeoning", "P": "piercing", "S": "slashing", "N": "necrotic", "R": "radiant"}

SIZES = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge", "G": "Gargantuan"}

PROPS = {"A": "ammunition", "LD": "loading", "L": "light", "F": "finesse", "T": "thrown", "H": "heavy", "R": "reach",
         "2H": "two-handed", "V": "versatile", "S": "special", "RLD": "reload", "BF": "burst fire", "CREW": "Crew",
         "PASS": "Passengers", "CARGO": "Cargo", "DMGT": "Damage Threshold", "SHPREP": "Ship Repairs"}

LARGE_THRESHOLD = 200


class Lookup(commands.Cog):
    """Commands to help look up items, status effects, rules, etc."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['status'])
    async def condition(self, ctx, *, name: str):
        """Looks up a condition."""
        # this is an invoke instead of an alias to make more sense in docs
        await ctx.invoke(self.rule, name=f"Condition: {name}")

    @staticmethod
    async def _show_reference_options(ctx, destination):
        embed = EmbedWithAuthor(ctx)
        embed.title = "Rules"
        categories = ', '.join(a['type'] for a in compendium.rule_references)
        embed.description = f"Use `{ctx.prefix}{ctx.invoked_with} <category>` to look at all actions of " \
                            f"a certain type.\nCategories: {categories}"

        for actiontype in compendium.rule_references:
            embed.add_field(name=actiontype['fullName'], value=', '.join(a['name'] for a in actiontype['items']))

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

    @commands.command(aliases=['reference'])
    async def rule(self, ctx, *, name: str = None):
        """Looks up a rule."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        if name is None:
            return await self._show_reference_options(ctx, destination)

        options = []
        for actiontype in compendium.rule_references:
            if name == actiontype['type']:
                return await self._show_action_options(ctx, actiontype, destination)
            else:
                options.extend(actiontype['items'])

        result, metadata = await search_and_select(ctx, options, name, lambda e: e['fullName'], return_metadata=True)
        await self.add_training_data("reference", name, result['fullName'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['fullName']
        embed.description = f"*{result['short']}*"
        add_fields_from_long_text(embed, "Description", result['desc'])
        embed.set_footer(text=f"Rule | {result['source']}")

        await destination.send(embed=embed)

    @commands.command()
    async def feat(self, ctx, *, name: str):
        """Looks up a feat."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        result, metadata = await search_and_select(ctx, compendium.feats, name, lambda e: e['name'],
                                                   return_metadata=True)
        await self.add_training_data("feat", name, result['name'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        if result['prerequisite']:
            embed.add_field(name="Prerequisite", value=result['prerequisite'])
        if result['ability']:
            embed.add_field(name="Ability Improvement",
                            value=f"Increase your {result['ability']} score by 1, up to a maximum of 20.")

        add_fields_from_long_text(embed, "Description", result['desc'])
        embed.set_footer(text=f"Feat | {result['source']} {result['page']}")
        await destination.send(embed=embed)

    @commands.command()
    async def racefeat(self, ctx, *, name: str):
        """Looks up a racial feature."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        result, metadata = await search_and_select(ctx, compendium.rfeats, name, lambda e: e['name'],
                                                   return_metadata=True)
        await self.add_training_data("racefeat", name, result['name'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        set_maybe_long_desc(embed, result['text'])

        await destination.send(embed=embed)

    @commands.command()
    async def race(self, ctx, *, name: str):
        """Looks up a race."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        result, metadata = await search_and_select(ctx, compendium.fancyraces, name, lambda e: e.name,
                                                   return_metadata=True)
        await self.add_training_data("race", name, result.name, metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.description = f"Source: {result.source}"
        embed.add_field(name="Speed", value=result.get_speed_str())
        embed.add_field(name="Size", value=result.size)
        if result.ability:
            embed.add_field(name="Ability Bonuses", value=result.get_asi_str())
        for t in result.get_traits():
            f_text = t['text']
            f_text = [f_text[i:i + 1024] for i in range(0, len(f_text), 1024)]
            embed.add_field(name=t['name'], value=f_text[0])
            for piece in f_text[1:]:
                embed.add_field(name="** **", value=piece)

        await destination.send(embed=embed)

    @commands.command()
    async def classfeat(self, ctx, *, name: str):
        """Looks up a class feature."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        result, metadata = await search_and_select(ctx, compendium.cfeats, name, lambda e: e['name'],
                                                   return_metadata=True)
        await self.add_training_data("classfeat", name, result['name'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        set_maybe_long_desc(embed, result['text'])

        await destination.send(embed=embed)

    @commands.command(name='class')
    async def _class(self, ctx, name: str, level: int = None):
        """Looks up a class, or all features of a certain level."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        if level is not None and not 0 < level < 21:
            return await ctx.send("Invalid level.")

        result, metadata = await search_and_select(ctx, compendium.classes, name, lambda e: e['name'],
                                                   return_metadata=True)
        await self.add_training_data("class", name, result['name'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        if level is None:
            embed.title = result['name']
            embed.add_field(name="Hit Die", value=f"1d{result['hd']['faces']}")
            embed.add_field(name="Saving Throws", value=', '.join(ABILITY_MAP.get(p) for p in result['proficiency']))

            levels = []
            starting_profs = f"You are proficient with the following items, " \
                             f"in addition to any proficiencies provided by your race or background.\n" \
                             f"Armor: {', '.join(result['startingProficiencies'].get('armor', ['None']))}\n" \
                             f"Weapons: {', '.join(result['startingProficiencies'].get('weapons', ['None']))}\n" \
                             f"Tools: {', '.join(result['startingProficiencies'].get('tools', ['None']))}\n" \
                             f"Skills: Choose {result['startingProficiencies']['skills']['choose']} from " \
                             f"{', '.join(result['startingProficiencies']['skills']['from'])}"

            equip_choices = '\n'.join(f"• {i}" for i in result['startingEquipment']['default'])
            gold_alt = f"Alternatively, you may start with {result['startingEquipment']['goldAlternative']} gp " \
                       f"to buy your own equipment." if 'goldAlternative' in result['startingEquipment'] else ''
            starting_items = f"You start with the following items, plus anything provided by your background.\n" \
                             f"{equip_choices}\n" \
                             f"{gold_alt}"
            for level in range(1, 21):
                level_str = []
                level_features = result['classFeatures'][level - 1]
                for feature in level_features:
                    level_str.append(feature.get('name'))
                levels.append(', '.join(level_str))

            embed.add_field(name="Starting Proficiencies", value=starting_profs)
            embed.add_field(name="Starting Equipment", value=starting_items)

            level_features_str = ""
            for i, l in enumerate(levels):
                level_features_str += f"`{i + 1}` {l}\n"
            embed.description = level_features_str

            embed.set_footer(text=f"Use {ctx.prefix}classfeat to look up a feature.")
        else:
            embed.title = f"{result['name']}, Level {level}"

            level_resources = {}
            level_features = result['classFeatures'][level - 1]

            for table in result.get('classTableGroups', []):
                relevant_row = table['rows'][level - 1]
                for i, col in enumerate(relevant_row):
                    level_resources[table['colLabels'][i]] = parse_data_entry([col])

            for res_name, res_value in level_resources.items():
                if res_value != '0':
                    embed.add_field(name=res_name, value=res_value)

            for f in level_features:
                text = parse_data_entry(f['entries'])
                embed.add_field(name=f['name'], value=(text[:1019] + "...") if len(text) > 1023 else text)

            embed.set_footer(text=f"Use {ctx.prefix}classfeat to look up a feature if it is cut off.")

        await destination.send(embed=embed)

    @commands.command()
    async def subclass(self, ctx, name: str):
        """Looks up a subclass."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        destination = ctx.author if pm else ctx.channel

        result, metadata = await search_and_select(ctx, compendium.subclasses, name, lambda e: e['name'],
                                                   return_metadata=True)
        await self.add_training_data("subclass", name, result['name'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.description = f"*Source: {result['source']}*"

        for level_features in result['subclassFeatures']:
            for feature in level_features:
                for entry in feature['entries']:
                    if not isinstance(entry, dict): continue
                    if not entry.get('type') == 'entries': continue
                    text = parse_data_entry(entry['entries'])
                    embed.add_field(name=entry['name'], value=(text[:1019] + "...") if len(text) > 1023 else text)

        embed.set_footer(text=f"Use {ctx.prefix}classfeat to look up a feature if it is cut off.")

        await destination.send(embed=embed)

    @commands.command()
    async def background(self, ctx, *, name: str):
        """Looks up a background."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)

        result, metadata = await search_and_select(ctx, compendium.backgrounds, name, lambda e: e.name,
                                                   return_metadata=True)
        await self.add_training_data("background", name, result.name, metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        embed.title = result.name
        embed.set_footer(text=f"Background | {result.source} {result.page}")

        ignored_fields = ['suggested characteristics', 'personality trait', 'ideal', 'bond', 'flaw', 'specialty',
                          'harrowing event']
        for trait in result.traits:
            if trait['name'].lower() in ignored_fields: continue
            text = trait['text']
            text = textwrap.shorten(text, width=1020, placeholder="...")
            embed.add_field(name=trait['name'], value=text)

        # do stuff here
        if pm:
            await ctx.author.send(embed=embed)
        else:
            await ctx.send(embed=embed)

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

    @commands.command()
    async def token(self, ctx, *, name=None):
        """Shows a token for a monster or player. May not support all monsters."""

        if name is None:
            token_cmd = self.bot.get_command('playertoken')
            if token_cmd is None:
                return await ctx.send("Error: SheetManager cog not loaded.")
            return await ctx.invoke(token_cmd)

        monster, metadata = await select_monster_full(ctx, name, return_metadata=True)

        metadata['homebrew'] = monster.source == 'homebrew'
        await self.add_training_data("monster", name, monster.name, metadata=metadata)

        url = monster.get_image_url()
        embed = EmbedWithAuthor(ctx)
        embed.title = monster.name
        embed.description = f"{monster.size} monster."

        if not monster.source == 'homebrew':
            embed.set_image(url=url)
            embed.set_footer(text="This command may not support all monsters.")

            await ctx.send(embed=embed)
        else:
            if not url:
                return await ctx.channel.send("This monster has no image.")

            try:
                processed = await generate_token(url)
            except Exception as e:
                return await ctx.channel.send(f"Error generating token: {e}")

            file = discord.File(processed, filename="image.png")
            embed.set_image(url="attachment://image.png")
            await ctx.send(file=file, embed=embed)

    @commands.command()
    async def monster(self, ctx, *, name: str):
        """Looks up a monster.
        Generally requires a Game Master role to show full stat block.
        Game Master Roles: GM, DM, Game Master, Dungeon Master"""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)
        pm_dm = guild_settings.get("pm_dm", False)
        req_dm_monster = guild_settings.get("req_dm_monster", True)

        visible_roles = ['gm', 'game master', 'dm', 'dungeon master']
        if req_dm_monster and ctx.guild:
            visible = True if any(
                ro in [str(r).lower() for r in ctx.author.roles] for ro in visible_roles) else False
        else:
            visible = True

        monster, metadata = await select_monster_full(ctx, name, return_metadata=True)

        metadata['homebrew'] = monster.source == 'homebrew'
        await self.add_training_data("monster", name, monster.name, metadata=metadata)

        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour

        embed_queue[-1].title = monster.name

        def safe_append(title, desc):
            if len(desc) < 1024:
                embed_queue[-1].add_field(name=title, value=desc)
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
                trait = ""
                for a in monster.traits:
                    trait += f"**{a.name}:** {a.desc}\n"
                if trait:
                    safe_append("Special Abilities", trait)
            if monster.actions:
                action = ""
                for a in monster.actions:
                    action += f"**{a.name}:** {a.desc}\n"
                if action:
                    safe_append("Actions", action)
            if monster.reactions:
                reaction = ""
                for a in monster.reactions:
                    reaction += f"**{a.name}:** {a.desc}\n"
                if reaction:
                    safe_append("Reactions", reaction)
            if monster.legactions:
                legendary = ""
                for a in monster.legactions:
                    if a.name:
                        legendary += f"**{a.name}:** {a.desc}\n"
                    else:
                        legendary += f"{a.desc}\n"
                if legendary:
                    safe_append("Legendary Actions", legendary)

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

        if monster.source == 'homebrew':
            embed_queue[-1].set_footer(text="Homebrew content.", icon_url=HOMEBREW_ICON)
        else:
            embed_queue[-1].set_footer(text=f"Creature | {monster.source} {monster.page}")

        embed_queue[0].set_thumbnail(url=monster.get_image_url())

        for embed in embed_queue:
            if pm or (visible and pm_dm and req_dm_monster):
                await ctx.author.send(embed=embed)
            else:
                await ctx.send(embed=embed)

    @commands.command()
    async def spell(self, ctx, *, name: str):
        """Looks up a spell."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)

        spell, metadata = await select_spell_full(ctx, name, return_metadata=True)

        metadata['homebrew'] = spell.source == 'homebrew'
        await self.add_training_data("spell", name, spell.name, metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        color = embed.colour

        embed.title = spell.name
        embed.description = f"*{spell.get_level()} {spell.get_school().lower()}. " \
                            f"({', '.join(itertools.chain(spell.classes, spell.subclasses))})*"
        if spell.ritual:
            time = f"{spell.time} (ritual)"
        else:
            time = spell.time
        embed.add_field(name="Casting Time", value=time)
        embed.add_field(name="Range", value=spell.range)
        embed.add_field(name="Components", value=spell.components)
        embed.add_field(name="Duration", value=spell.duration)

        text = spell.description
        higher_levels = spell.higherlevels

        if len(text) > 1020:
            pieces = [text[:1020]] + [text[i:i + 2040] for i in range(1020, len(text), 2040)]
        else:
            pieces = [text]

        embed.add_field(name="Description", value=pieces[0])

        embed_queue = [embed]
        if len(pieces) > 1:
            for piece in pieces[1:]:
                temp_embed = discord.Embed()
                temp_embed.colour = color
                temp_embed.description = piece
                embed_queue.append(temp_embed)

        if higher_levels:
            embed_queue[-1].add_field(name="At Higher Levels", value=higher_levels)

        if spell.source == 'homebrew':
            embed_queue[-1].set_footer(text="Homebrew content.", icon_url=HOMEBREW_ICON)
        else:
            embed_queue[-1].set_footer(text=f"Spell | {spell.source} {spell.page}")

        if spell.image:
            embed_queue[0].set_thumbnail(url=spell.image)

        for embed in embed_queue:
            if pm:
                await ctx.author.send(embed=embed)
            else:
                await ctx.send(embed=embed)

    @commands.command(name='item')
    async def item_lookup(self, ctx, *, name):
        """Looks up an item."""
        guild_settings = await self.get_settings(ctx.guild)
        pm = guild_settings.get("pm_result", False)

        try:
            pack = await Pack.from_ctx(ctx)
            custom_items = pack.get_search_formatted_items()
            pack_id = pack.id
        except NoActiveBrew:
            custom_items = []
            pack_id = None
        choices = list(itertools.chain(compendium.items, custom_items))
        if ctx.guild:
            async for servpack in ctx.bot.mdb.packs.find({"server_active": str(ctx.guild.id)}):
                if servpack['_id'] != pack_id:
                    choices.extend(Pack.from_dict(servpack).get_search_formatted_items())

        def get_homebrew_formatted_name(_item):
            if _item.get('source') == 'homebrew':
                return f"{_item['name']} ({HOMEBREW_EMOJI})"
            return _item['name']

        result, metadata = await search_and_select(ctx, choices, name, lambda e: e['name'],
                                                   selectkey=get_homebrew_formatted_name, return_metadata=True)

        metadata['homebrew'] = result.get('source') == 'homebrew'
        await self.add_training_data("item", name, result['name'], metadata=metadata)

        embed = EmbedWithAuthor(ctx)
        item = result

        name = item['name']
        proptext = ""

        if not item.get('source') == 'homebrew':
            damage = ''
            extras = ''
            properties = []

            if 'type' in item:
                type_ = ', '.join(
                    i for i in ([ITEM_TYPES.get(t, 'n/a') for t in item['type'].split(',')] +
                                ["Wondrous Item" if item.get('wondrous') else ''])
                    if i)
                for iType in item['type'].split(','):
                    if iType in ('M', 'R', 'GUN'):
                        damage = f"{item.get('dmg1', 'n/a')} {DMGTYPES.get(item.get('dmgType'), 'n/a')}" \
                            if 'dmg1' in item and 'dmgType' in item else ''
                        type_ += f', {item.get("weaponCategory")}'
                    if iType == 'S': damage = f"AC +{item.get('ac', 'n/a')}"
                    if iType == 'LA': damage = f"AC {item.get('ac', 'n/a')} + DEX"
                    if iType == 'MA': damage = f"AC {item.get('ac', 'n/a')} + DEX (Max 2)"
                    if iType == 'HA': damage = f"AC {item.get('ac', 'n/a')}"
                    if iType == 'SHP':  # ships
                        for p in ("CREW", "PASS", "CARGO", "DMGT", "SHPREP"):
                            a = PROPS.get(p, 'n/a')
                            proptext += f"**{a.title()}**: {compendium.itemprops[p]}\n"
                        extras = f"Speed: {item.get('speed')}\nCarrying Capacity: {item.get('carryingcapacity')}\n" \
                                 f"Crew {item.get('crew')}, AC {item.get('vehAc')}, HP {item.get('vehHp')}"
                        if 'vehDmgThresh' in item:
                            extras += f", Damage Threshold {item['vehDmgThresh']}"
                    if iType == 'siege weapon':
                        extras = f"Size: {SIZES.get(item.get('size'), 'Unknown')}\n" \
                                 f"AC {item.get('ac')}, HP {item.get('hp')}\n" \
                                 f"Immunities: {item.get('immune')}"
            else:
                type_ = ', '.join(
                    i for i in ("Wondrous Item" if item.get('wondrous') else '', item.get('technology')) if i)
            rarity = str(item.get('rarity')).replace('None', '')
            if 'tier' in item:
                if rarity:
                    rarity += f', {item["tier"]}'
                else:
                    rarity = item['tier']
            type_and_rarity = type_ + (f", {rarity}" if rarity else '')
            value = (item.get('value', 'n/a') + (', ' if 'weight' in item else '')) if 'value' in item else ''
            weight = (item.get('weight', 'n/a') + (' lb.' if item.get('weight') == '1' else ' lbs.')) \
                if 'weight' in item else ''
            weight_and_value = value + weight
            for prop in item.get('property', []):
                if not prop: continue
                a = b = prop
                a = PROPS.get(a, 'n/a')
                if b in compendium.itemprops:
                    proptext += f"**{a.title()}**: {compendium.itemprops[b]}\n"
                if b == 'V': a += " (" + item.get('dmg2', 'n/a') + ")"
                if b in ('T', 'A'): a += " (" + item.get('range', 'n/a') + "ft.)"
                if b == 'RLD': a += " (" + item.get('reload', 'n/a') + " shots)"
                properties.append(a)
            properties = ', '.join(properties)
            damage_and_properties = f"{damage} - {properties}" if properties else damage
            damage_and_properties = (' --- ' + damage_and_properties) if weight_and_value and damage_and_properties else \
                damage_and_properties

            meta = f"*{type_and_rarity}*\n{weight_and_value}{damage_and_properties}\n{extras}"
            text = item['desc']

            if 'reqAttune' in item:
                if item['reqAttune'] is True:  # can be truthy, but not true
                    embed.add_field(name="Attunement", value=f"Requires Attunement")
                else:
                    embed.add_field(name="Attunement", value=f"Requires Attunement {item['reqAttune']}")

            embed.set_footer(text=f"Item | {item.get('source', 'Unknown')} {item.get('page', 'Unknown')}")
        else:
            meta = item['meta']
            text = item['desc']
            if 'image' in item:
                embed.set_thumbnail(url=item['image'])
            add_homebrew_footer(embed)

        embed.title = name
        embed.description = meta  # no need to render, has been prerendered

        if proptext:
            text = f"{text}\n{proptext}"
        if len(text) > 5500:
            text = text[:5500] + "..."

        field_name = "Description"
        for piece in [text[i:i + 1024] for i in range(0, len(text), 1024)]:
            embed.add_field(name=field_name, value=piece)
            field_name = "** **"

        if pm:
            await ctx.author.send(embed=embed)
        else:
            await ctx.send(embed=embed)

        await Stats.increase_stat(ctx, "items_looked_up_life")

    async def get_settings(self, guild):
        settings = {}  # default PM settings
        if guild is not None:
            settings = await self.bot.mdb.lookupsettings.find_one({"server": str(guild.id)})
        return settings or {}

    async def add_training_data(self, lookup_type, query, result_name, metadata=None):
        data = {"type": lookup_type, "query": query, "result": result_name, "srd": True}
        if metadata:
            data['given_options'] = metadata.get('num_options', 1)
            data['chosen_index'] = metadata.get('chosen_index', 0)
            data['homebrew'] = metadata.get('homebrew', False)
        await self.bot.mdb.nn_training.insert_one(data)

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
