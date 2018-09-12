"""
Created on Nov 29, 2016

@author: andrew
"""
import copy
import shlex
import textwrap

import discord
from discord.ext import commands

from cogs5e.funcs.lookupFuncs import select_monster_full, c, getSpell
from cogs5e.models.embeds import EmbedWithAuthor
from utils import checks
from utils.functions import get_positivity, parse_data_entry, ABILITY_MAP, search_and_select, generate_token

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


class Lookup:
    """Commands to help look up items, status effects, rules, etc."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, aliases=['status'])
    async def condition(self, ctx, *, name: str):
        """Looks up a condition."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.conditions, name, lambda e: e['name'])

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.description = result['desc']

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def rule(self, ctx, *, name: str):
        """Looks up a rule."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.rules, name, lambda e: e['name'])

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        desc = result['desc']
        desc = [desc[i:i + 1024] for i in range(0, len(desc), 1024)]
        embed.description = ''.join(desc[:2])
        for piece in desc[2:]:
            embed.add_field(name="** **", value=piece)

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def feat(self, ctx, *, name: str):
        """Looks up a feat."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.feats, name, lambda e: e['name'])

        if not result['name'] == 'Grappler' and srd:  # the only SRD feat.
            return await self.send_srd_error(ctx, result)

        text = parse_data_entry(result['entries'])
        prereq = []

        if 'prerequisite' in result:
            for entry in result['prerequisite']:
                if 'race' in entry:
                    prereq.append(' or '.join(
                        f"{r['name']}" + (f" ({r['subrace']})" if 'subrace' in r else '') for r in entry['race']))
                if 'ability' in entry:
                    abilities = []
                    for ab in entry['ability']:
                        abilities.extend(f"{ABILITY_MAP.get(a)} {s}" for a, s in ab.items())
                    prereq.append(' or '.join(abilities))
                if 'spellcasting' in entry:
                    prereq.append("The ability to cast at least one spell")
                if 'proficiency' in entry:
                    prereq.append(f"Proficiency with {entry['proficiency'][0]['armor']} armor")
                if 'level' in entry:
                    prereq.append(f"Level {entry['level']}")
                if 'special' in entry:
                    prereq.append(entry['special'])

        if prereq:
            prereq = '\n'.join(prereq)
        else:
            prereq = "None"

        ability = None
        if 'ability' in result:
            if 'choose' in result['ability']:
                ability = ' or '.join(ABILITY_MAP.get(a) for a in result['ability']['choose'][0]['from'])
            else:
                ability = ' or '.join(ABILITY_MAP.get(a) for a in result['ability'].keys())

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.add_field(name="Prerequisite", value=prereq)
        embed.add_field(name="Source", value=result['source'])
        if ability:
            embed.add_field(name="Ability Improvement",
                            value=f"Increase your {ability} score by 1, up to a maximum of 20.")
        _name = 'Description'
        for piece in [text[i:i + 1024] for i in range(0, len(text), 1024)]:
            embed.add_field(name=_name, value=piece)
            _name = '** **'
        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def racefeat(self, ctx, *, name: str):
        """Looks up a racial feature."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.rfeats, name, lambda e: e['name'], srd=srd)

        if not result['srd'] and srd:
            return await self.send_srd_error(ctx, result)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        desc = result['text']
        desc = [desc[i:i + 1024] for i in range(0, len(desc), 1024)]
        embed.description = ''.join(desc[:2])
        for piece in desc[2:]:
            embed.add_field(name="** **", value=piece)

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def race(self, ctx, *, name: str):
        """Looks up a race."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.fancyraces, name, lambda e: e.name, srd=srd and (lambda e: e.srd))

        if not result.srd and srd:
            return await self.send_srd_error(ctx, result)

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

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def classfeat(self, ctx, *, name: str):
        """Looks up a class feature."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.cfeats, name, lambda e: e['name'], srd=srd)

        if not result['srd'] and srd:
            return await self.send_srd_error(ctx, result)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        desc = result['text']
        desc = [desc[i:i + 1024] for i in range(0, len(desc), 1024)]
        embed.description = ''.join(desc[:2])
        for piece in desc[2:]:
            embed.add_field(name="** **", value=piece)

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True, name='class')
    async def _class(self, ctx, name: str, level: int = None):
        """Looks up a class, or all features of a certain level."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        destination = ctx.message.author if pm else ctx.message.channel

        if level is not None and not 0 < level < 21:
            return await self.bot.say("Invalid level.")

        result = await search_and_select(ctx, c.classes, name, lambda e: e['name'], srd=srd)

        if not result['srd'] and srd:
            return await self.send_srd_error(ctx, result)

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
                level_features_str += f"`{i+1}` {l}\n"
            embed.description = level_features_str

            embed.set_footer(text="Use !classfeat to look up a feature.")
        else:
            embed.title = f"{result['name']}, Level {level}"

            level_resources = {}
            level_features = result['classFeatures'][level - 1]

            for table in result['classTableGroups']:
                relevant_row = table['rows'][level - 1]
                for i, col in enumerate(relevant_row):
                    level_resources[table['colLabels'][i]] = parse_data_entry([col])

            for res_name, res_value in level_resources.items():
                embed.add_field(name=res_name, value=res_value)

            for f in level_features:
                text = parse_data_entry(f['entries'])
                embed.add_field(name=f['name'], value=(text[:1019] + "...") if len(text) > 1023 else text)

            embed.set_footer(text="Use !classfeat to look up a feature if it is cut off.")

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def subclass(self, ctx, name: str):
        """Looks up a subclass."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        destination = ctx.message.author if pm else ctx.message.channel

        result = await search_and_select(ctx, c.subclasses, name, lambda e: e['name'], srd=srd)

        if not result.get('srd') and srd:
            return await self.send_srd_error(ctx, result)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']

        for level_features in result['subclassFeatures']:
            for feature in level_features:
                for entry in feature['entries']:
                    if not isinstance(entry, dict): continue
                    if not entry.get('type') == 'entries': continue
                    text = parse_data_entry(entry['entries'])
                    embed.add_field(name=entry['name'], value=(text[:1019] + "...") if len(text) > 1023 else text)

        embed.set_footer(text="Use !classfeat to look up a feature if it is cut off.")

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def background(self, ctx, *, name: str):
        """Looks up a background."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        result = await search_and_select(ctx, c.backgrounds, name, lambda e: e['name'], srd=srd)

        if not result['srd'] and srd:
            return await self.send_srd_error(ctx, result)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.description = f"*Source: {result.get('source', 'Unknown')}*"

        ignored_fields = ['suggested characteristics', 'personality trait', 'ideal', 'bond', 'flaw', 'specialty',
                          'harrowing event']
        for trait in result['trait']:
            if trait['name'].lower() in ignored_fields: continue
            text = '\n'.join(t for t in trait['text'] if t)
            text = textwrap.shorten(text, width=1020, placeholder="...")
            embed.add_field(name=trait['name'], value=text)

        # do stuff here
        if pm:
            await self.bot.send_message(ctx.message.author, embed=embed)
        else:
            await self.bot.say(embed=embed)

    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def lookup_settings(self, ctx, *, args: str):
        """Changes settings for the lookup module.
        Usage: !lookup_settings -req_dm_monster True
        Current settings are: -req_dm_monster [True/False] - Requires a Game Master role to show a full monster stat block.
                              -pm_result [True/False] - PMs the result of the lookup to reduce spam.
                              -srd [True/False] - toggles SRD lookup restriction in a server."""
        args = shlex.split(args.lower())
        guild_id = ctx.message.server.id
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
        if '-pm_result' in args:
            try:
                setting = args[args.index('-pm_result') + 1]
            except IndexError:
                setting = 'False'
            setting = get_positivity(setting)
            guild_settings['pm_result'] = setting if setting is not None else False
            out += 'pm_result set to {}!\n'.format(str(guild_settings['pm_result']))
        if '-srd' in args:
            try:
                setting = args[args.index('-srd') + 1]
            except IndexError:
                setting = 'False'
            setting = get_positivity(setting)
            guild_settings['srd'] = setting if setting is not None else False
            out += 'srd set to {}!\n'.format(str(guild_settings['srd']))

        if guild_settings:
            await self.bot.mdb.lookupsettings.update_one({"server": guild_id}, {"$set": guild_settings}, upsert=True)
            await self.bot.say("Lookup settings set:\n" + out)
        else:
            await self.bot.say("No settings found. Make sure your syntax is correct.")

    @commands.command(pass_context=True)
    async def token(self, ctx, *, name=None):
        """Shows a token for a monster or player. May not support all monsters."""

        if name is None:
            token_cmd = self.bot.get_command('playertoken')
            if token_cmd is None:
                return await self.bot.say("Error: SheetManager cog not loaded.")
            return await ctx.invoke(token_cmd)

        guild_settings = await self.get_settings(ctx.message.server)
        srd = guild_settings.get("srd", False)

        monster = await select_monster_full(ctx, name, srd=srd)

        if not monster.srd and srd:
            e = EmbedWithAuthor(ctx)
            e.title = monster.name
            e.description = "Token not available."
            return await self.bot.say(embed=e)

        url = monster.get_image_url()

        if not monster.source == 'homebrew':
            embed = EmbedWithAuthor(ctx)
            embed.title = monster.name
            embed.description = f"{monster.size} monster."
            embed.set_image(url=url)
            embed.set_footer(text="This command may not support all monsters.")

            await self.bot.say(embed=embed)
        else:
            if not url:
                return await self.bot.send_message(ctx.message.channel, "This monster has no image.")

            try:
                processed = await generate_token(url)
            except Exception as e:
                return await self.bot.send_message(ctx.message.channel, f"Error generating token: {e}")

            await self.bot.send_file(ctx.message.channel, processed,
                                     content="I generated this token for you! If it seems "
                                             "wrong, you can make your own at "
                                             "<http://rolladvantage.com/tokenstamp/>!",
                                     filename="image.png")

    @commands.command(pass_context=True)
    async def monster(self, ctx, *, name: str):
        """Looks up a monster.
        Generally requires a Game Master role to show full stat block.
        Game Master Roles: GM, DM, Game Master, Dungeon Master"""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        visible_roles = ['gm', 'game master', 'dm', 'dungeon master']
        if guild_settings.get("req_dm_monster", True) and ctx.message.server:
            visible = True if any(
                ro in [str(r).lower() for r in ctx.message.author.roles] for ro in visible_roles) else False
        else:
            visible = True

        self.bot.rdb.incr('monsters_looked_up_life')
        monster = await select_monster_full(ctx, name, srd=srd)

        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour

        embed_queue[-1].title = monster.name

        if not monster.srd and srd:
            e = EmbedWithAuthor(ctx)
            e.title = monster.name
            e.description = "Description not available."
            return await self.bot.say(embed=e)

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
            embed_queue[-1].set_footer(text="Homebrew content.", icon_url="https://avrae.io/static/homebrew.png")
        else:
            embed_queue[-1].set_footer(text=f"Creature | {monster.source} {monster.page}")

        embed_queue[0].set_thumbnail(url=monster.get_image_url())

        for embed in embed_queue:
            if pm:
                await self.bot.send_message(ctx.message.author, embed=embed)
            else:
                await self.bot.say(embed=embed)

    @commands.command(pass_context=True)
    async def spell(self, ctx, *, name: str):
        """Looks up a spell."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        self.bot.rdb.incr('spells_looked_up_life')

        result = await search_and_select(ctx, c.spells, name, lambda e: e['name'], return_key=True, srd=srd)
        result = getSpell(result)

        spellDesc = []
        embed = EmbedWithAuthor(ctx)
        color = embed.colour
        spell = copy.copy(result)

        def parseschool(school):
            if school == "A": return "abjuration"
            if school == "EV": return "evocation"
            if school == "EN": return "enchantment"
            if school == "I": return "illusion"
            if school == "D": return "divination"
            if school == "N": return "necromancy"
            if school == "T": return "transmutation"
            if school == "C": return "conjuration"
            return school

        def parsespelllevel(level):
            if level == "0": return "cantrip"
            if level == "2": return level + "nd level"
            if level == "3": return level + "rd level"
            if level == "1": return level + "st level"
            return level + "th level"

        spell['school'] = parseschool(spell.get('school'))
        spell['ritual'] = spell.get('ritual', 'no').lower()

        embed.title = spell['name']

        if spell.get("source") == "UAMystic":
            embed.description = "*{level} Mystic Talent. ({classes})*".format(**spell)
        else:
            spell['level'] = parsespelllevel(spell['level'])
            embed.description = "*{level} {school}. ({classes})*".format(**spell)
            embed.add_field(name="Casting Time", value=spell['time'])
            embed.add_field(name="Range", value=spell['range'])
            embed.add_field(name="Components", value=spell['components'])
            embed.add_field(name="Duration", value=spell['duration'])
            embed.add_field(name="Ritual", value=spell['ritual'])

        if isinstance(spell['text'], list):
            for a in spell["text"]:
                if a is '': continue
                spellDesc.append(a.replace("At Higher Levels: ", "**At Higher Levels:** ").replace(
                    "This spell can be found in the Elemental Evil Player's Companion", ""))
        else:
            spellDesc.append(spell['text'].replace("At Higher Levels: ", "**At Higher Levels:** ").replace(
                "This spell can be found in the Elemental Evil Player's Companion", ""))

        text = '\n'.join(spellDesc)
        if "**At Higher Levels:** " in text:
            text, higher_levels = text.split("**At Higher Levels:** ", 1)
        elif "At Higher Levels" in text:
            text, higher_levels = text.split("At Higher Levels", 1)
            text = text.strip('*\n')
            higher_levels = higher_levels.strip('* \n.:')
        else:
            higher_levels = None

        if not spell['srd'] and srd:
            text = "No description available."
            higher_levels = ''

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

        for embed in embed_queue:
            if pm:
                await self.bot.send_message(ctx.message.author, embed=embed)
            else:
                await self.bot.say(embed=embed)

    @commands.command(pass_context=True, name='item')
    async def item_lookup(self, ctx, *, name):
        """Looks up an item."""
        guild_settings = await self.get_settings(ctx.message.server)
        pm = guild_settings.get("pm_result", False)
        srd = guild_settings.get("srd", False)

        self.bot.rdb.incr('items_looked_up_life')

        result = await search_and_select(ctx, c.items, name, lambda e: e['name'], srd=srd)

        embed = EmbedWithAuthor(ctx)
        item = result

        if not item['srd'] and srd:
            return await self.send_srd_error(ctx, result)

        name = item['name']
        damage = ''
        extras = ''
        properties = []
        proptext = ""

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
                        proptext += f"**{a.title()}**: {c.itemprops[p]}\n"
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
            if b in c.itemprops:
                proptext += f"**{a.title()}**: {c.itemprops[b]}\n"
            if b == 'V': a += " (" + item.get('dmg2', 'n/a') + ")"
            if b in ('T', 'A'): a += " (" + item.get('range', 'n/a') + "ft.)"
            if b == 'RLD': a += " (" + item.get('reload', 'n/a') + " shots)"
            properties.append(a)
        properties = ', '.join(properties)
        damage_and_properties = f"{damage} - {properties}" if properties else damage
        damage_and_properties = (' --- ' + damage_and_properties) if weight_and_value and damage_and_properties else \
            damage_and_properties

        embed.title = name
        desc = f"*{type_and_rarity}*\n{weight_and_value}{damage_and_properties}\n{extras}"
        embed.description = desc  # no need to render, has been prerendered

        if 'reqAttune' in item:
            if item['reqAttune'] is True:  # can be truthy, but not true
                embed.add_field(name="Attunement", value=f"Requires Attunement")
            else:
                embed.add_field(name="Attunement", value=f"Requires Attunement {item['reqAttune']}")

        text = item['desc']
        if proptext:
            text = f"{text}\n{proptext}"
        if len(text) > 5500:
            text = text[:5500] + "..."

        field_name = "Description"
        for piece in [text[i:i + 1024] for i in range(0, len(text), 1024)]:
            embed.add_field(name=field_name, value=piece)
            field_name = "** **"

        embed.set_footer(text=f"Item | {item.get('source', 'Unknown')} {item.get('page', 'Unknown')}")

        if pm:
            await self.bot.send_message(ctx.message.author, embed=embed)
        else:
            await self.bot.say(embed=embed)

    async def send_srd_error(self, ctx, data):
        e = EmbedWithAuthor(ctx)
        e.title = data['name']
        e.description = "Description not available."
        return await self.bot.say(embed=e)

    async def get_settings(self, guild):
        settings = {}
        if guild is not None:
            settings = await self.bot.mdb.lookupsettings.find_one({"server": guild.id})
        return settings or {}


def setup(bot):
    bot.add_cog(Lookup(bot))
