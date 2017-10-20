"""
Created on Nov 29, 2016

@author: andrew
"""
import shlex
import textwrap
from urllib import parse

from discord.ext import commands

from cogs5e.funcs.lookupFuncs import *
from cogs5e.models.embeds import EmbedWithAuthor
from utils import checks
from utils.functions import get_positivity

CLASS_RESOURCE_MAP = {'slots': "Spell Slots",  # a weird one - see fighter
                      'spellsknown': "Spells Known",
                      'rages': "Rages", 'ragedamage': "Rage Damage",
                      'martialarts': "Martial Arts", 'kipoints': "Ki", 'unarmoredmovement': "Unarmored Movement",
                      'sorcerypoints': "Sorcery Points", 'sneakattack': "Sneak Attack",
                      'invocationsknown': "Invocations Known", 'spellslots': "Spell Slots", 'slotlevel': "Slot Level",
                      'talentsknown': "Talents Known", 'disciplinesknown': "Disciplines Known",
                      'psipoints': "Psi Points", 'psilimit': "Psi Limit"}


class Lookup:
    """Commands to help look up items, status effects, rules, etc."""

    def __init__(self, bot):
        self.bot = bot
        self.settings = self.bot.db.not_json_get("lookup_settings", {}) if bot is not None else {}

    @commands.command(pass_context=True, aliases=['status'])
    async def condition(self, ctx, *, name: str):
        """Looks up a condition."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        result = searchCondition(name)
        if result is None:
            return await self.bot.say('Condition not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.description = result['desc']

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def rule(self, ctx, *, name: str):
        """Looks up a rule."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        result = searchRule(name)
        if result is None:
            return await self.bot.say('Rule not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        desc = result['desc']
        desc = [desc[i:i + 1024] for i in range(0, len(desc), 1024)]
        embed.description = ''.join(desc[:2])
        for piece in desc[2:]:
            embed.add_field(name="con't", value=piece)

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def feat(self, ctx, *, name: str):
        """Looks up a feat."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        result = searchFeat(name)
        if result is None:
            return await self.bot.say('Feat not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        if isinstance(result['text'], list):
            result['text'] = '\n'.join(
                t for t in result.get('text', []) if t is not None and not t.startswith('Source:'))
        result['prerequisite'] = result.get('prerequisite') or "None"

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.add_field(name="Prerequisite", value=result['prerequisite'])
        embed.add_field(name="Source", value=result['source'])
        for piece in [result['text'][i:i + 1024] for i in range(0, len(result['text']), 1024)]:
            embed.add_field(name="Description", value=piece)
        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def racefeat(self, ctx, *, name: str):
        """Looks up a racial feature."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        result = searchRacialFeat(name)
        if result is None:
            return await self.bot.say('Race feature not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        if isinstance(result['text'], list):
            result['text'] = '\n'.join(t for t in result.get('text', []) if t is not None)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        desc = result['text']
        desc = [desc[i:i + 1024] for i in range(0, len(desc), 1024)]
        embed.description = ''.join(desc[:2])
        for piece in desc[2:]:
            embed.add_field(name="con't", value=piece)

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def race(self, ctx, *, name: str):
        """Looks up a race."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        result = searchRace(name)
        if result is None:
            return await self.bot.say('Race not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        _sizes = {'T': "Tiny", 'S': "Small",
                  'M': "Medium", 'L': "Large", 'H': "Huge"}
        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.description = f"Source: {result.get('source', 'unknown')}"
        embed.add_field(name="Speed", value=f"{result.get('speed', 'unknown')} ft.")
        embed.add_field(name="Size", value=_sizes.get(result.get('size'), 'unknown'))
        embed.add_field(name="Ability Bonuses", value=result.get('ability', 'none'))
        if result.get('proficiency'):
            embed.add_field(name="Proficiencies", value=result.get('proficiency', 'none'))
        for t in result.get('trait', []):
            embed.add_field(name=t['name'],
                            value='\n'.join(txt for txt in t['text'] if txt) if isinstance(t['text'], list) else t[
                                'text'])
        # trait_str = ', '.join(t['name'] for t in result.get('trait', []))
        # embed.add_field(name="Traits", value=trait_str, inline=False)
        # embed.set_footer(text="Use !racefeat to look up a trait.")

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def classfeat(self, ctx, *, name: str):
        """Looks up a class feature."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        result = searchClassFeat(name)
        if result is None:
            return await self.bot.say('Condition not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        if isinstance(result['text'], list):
            result['text'] = '\n'.join(t for t in result.get('text', []) if t is not None)

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        desc = result['text']
        desc = [desc[i:i + 1024] for i in range(0, len(desc), 1024)]
        embed.description = ''.join(desc[:2])
        for piece in desc[2:]:
            embed.add_field(name="con't", value=piece)

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True, name='class')
    async def _class(self, ctx, name: str, level: int = None):
        """Looks up a class, or all features of a certain level."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False
        destination = ctx.message.author if pm else ctx.message.channel

        if level is not None and not 0 < level < 21:
            return await self.bot.say("Invalid level.")

        result = searchClass(name)
        if result is None:
            return await self.bot.say('Class not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        embed = EmbedWithAuthor(ctx)
        if level is None:
            embed.title = result['name']
            embed.add_field(name="Hit Die", value=f"1d{result['hd']}")
            embed.add_field(name="Saving Throws", value=result['proficiency'])

            levels = []
            starting_profs = "None"
            starting_items = "None"
            for level in range(1, 21):
                level_str = []
                level_features = [f for f in result['autolevel'] if f['_level'] == str(level)]
                for feature in level_features:
                    for f in feature.get('feature', []):
                        if not f.get('_optional') and not (
                                    f['name'] in ("Starting Proficiencies", "Starting Equipment")):
                            level_str.append(f['name'])
                        elif f['name'] == "Starting Proficiencies":
                            starting_profs = '\n'.join(t for t in f['text'] if t)
                        elif f['name'] == "Starting Equipment":
                            starting_items = '\n'.join(t for t in f['text'] if t)
                    if not 'feature' in feature:
                        pass
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

            level_features = []
            level_resources = {}
            level_features_objs = [f for f in result['autolevel'] if f['_level'] == str(level)]
            for obj in level_features_objs:
                for f in obj.get('feature', []):
                    if not f.get('_optional') and not (f['name'] in ("Starting Proficiencies", "Starting Equipment")):
                        level_features.append(f)
                if not 'feature' in obj:
                    for k, v in obj.items():
                        if not k.startswith('_'):
                            level_resources[k] = v

            for res, val in level_resources.items():
                value = val
                if res == 'slots':
                    if isinstance(val, dict):  # EK/AT/Art
                        continue
                    if result['name'] == 'Warlock':  # Warlock
                        res = 'Cantrips Known'
                        value = val.split(',')[0]
                    else:
                        slots = val.split(',')
                        value = f"`Cantrips` - {slots[0]}"
                        for i, l in enumerate(slots[1:]):
                            value += f"`; L{i+1}` - {l}"
                if res == 'spellsknown' and isinstance(level_resources.get('slots'), dict):  # EK/AT/Art
                    continue

                embed.add_field(name=CLASS_RESOURCE_MAP.get(res, res), value=value)

            for f in level_features:
                text = '\n'.join(t for t in f['text'] if t)
                embed.add_field(name=f['name'], value=(text[:1019] + "...") if len(text) > 1023 else text)

            embed.set_footer(text="Use !classfeat to look up a feature if it is cut off.")

        await self.bot.send_message(destination, embed=embed)

    @commands.command(pass_context=True)
    async def background(self, ctx, *, name: str):
        """Looks up a background."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

        result = searchBackground(name)
        if result is None:
            return await self.bot.say('Background not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

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
                              -pm_result [True/False] - PMs the result of the lookup to reduce spam."""
        args = shlex.split(args.lower())
        guild_id = ctx.message.server.id
        self.settings = self.bot.db.not_json_get("lookup_settings", {})
        guild_settings = self.settings.get(guild_id, {})
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

        self.settings[guild_id] = guild_settings
        self.bot.db.not_json_set("lookup_settings", self.settings)
        await self.bot.say("Lookup settings set:\n" + out)

    @commands.command(pass_context=True)
    async def token(self, ctx, *, name):
        """Shows a token for a monster. May not support all monsters."""
        result = searchMonster(name)
        if result is None:
            return await self.bot.say('Monster not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        src = parse.quote(parsesource(result.get('type', '').split(',')[-1]))
        url = f"https://astranauta.github.io/img/{src}/{parse.quote(result['name'])}.png"

        embed = EmbedWithAuthor(ctx)
        embed.title = result['name']
        embed.description = f"{parsesize(result['size'])} monster."
        embed.set_image(url=url)
        embed.set_footer(text="This command may not support all monsters.")

        await self.bot.say(embed=embed)

    @commands.command(pass_context=True)
    async def monster(self, ctx, *, name: str):
        """Looks up a monster.
        Generally requires a Game Master role to show full stat block.
        Game Master Roles: GM, DM, Game Master, Dungeon Master"""

        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
            visible_roles = ['gm', 'game master', 'dm', 'dungeon master']
            if self.settings.get(guild_id, {}).get("req_dm_monster", True):
                visible = True if any(
                    ro in [str(r).lower() for r in ctx.message.author.roles] for ro in visible_roles) else False
            else:
                visible = True
        except:
            visible = True
            pm = False

        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')

        result = searchMonster(name)
        if result is None:
            return await self.bot.say('Monster not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        embed_queue = [EmbedWithAuthor(ctx)]
        color = embed_queue[-1].colour
        monster = copy.copy(result)

        embed_queue[-1].title = monster['name']

        src = parse.quote(parsesource(monster.get('type', '').split(',')[-1]))

        if visible:
            monster['size'] = parsesize(monster['size'])
            monster['type'] = ','.join(monster['type'].split(',')[:-1])
            for stat in ['str', 'dex', 'con', 'wis', 'int', 'cha']:
                monster[stat + 'Str'] = monster[stat] + " ({:+})".format(floor((int(monster[stat]) - 10) / 2))
            if monster.get('skill') is not None:
                monster['skill'] = monster['skill'][0]
            if monster.get('senses') is None:
                monster['senses'] = "passive Perception {}".format(monster['passive'])
            else:
                monster['senses'] = monster.get('senses') + ", passive Perception {}".format(monster['passive'])

            desc = "{size} {type}. {alignment}.\n**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {speed}\n".format(
                **monster)
            desc += "**STR:** {strStr} **DEX:** {dexStr} **CON:** {conStr}\n**WIS:** {wisStr} **INT:** {intStr} **CHA:** {chaStr}\n".format(
                **monster)

            if monster.get('save') is not None:
                desc += "**Saving Throws:** {save}\n".format(**monster)
            if monster.get('skill') is not None:
                desc += "**Skills:** {skill}\n".format(**monster)
            desc += "**Senses:** {senses}.\n".format(**monster)
            if monster.get('vulnerable', '') is not '':
                desc += "**Vulnerabilities:** {vulnerable}\n".format(**monster)
            if monster.get('resist', '') is not '':
                desc += "**Resistances:** {resist}\n".format(**monster)
            if monster.get('immune', '') is not '':
                desc += "**Damage Immunities:** {immune}\n".format(**monster)
            if monster.get('conditionImmune', '') is not '':
                desc += "**Condition Immunities:** {conditionImmune}\n".format(**monster)
            if monster.get('languages', '') is not '':
                desc += "**Languages:** {languages}\n".format(**monster)
            else:
                desc += "**Languages:** --\n".format(**monster)
            desc += "**CR:** {cr}\n".format(**monster)

            embed_queue[-1].description = desc

            if "trait" in monster:
                trait = ""
                for a in monster["trait"]:
                    if isinstance(a['text'], list):
                        a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                    trait += "**{name}:** {text}\n".format(**a)
                if trait:
                    if len(trait) < 1024:
                        embed_queue[-1].add_field(name="Special Abilities", value=trait)
                    elif len(trait) < 2048:
                        embed_queue.append(discord.Embed(colour=color, description=trait, title="Special Abilities"))
                    else:
                        embed_queue.append(discord.Embed(colour=color, title="Special Abilities"))
                        trait_all = [trait[i:i + 2040] for i in range(0, len(trait), 2040)]
                        embed_queue[-1].description = trait_all[0]
                        for a in trait_all[1:]:
                            embed_queue.append(discord.Embed(colour=color, description=a))

            if "action" in monster:
                action = ""
                for a in monster["action"]:
                    if isinstance(a['text'], list):
                        a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                    action += "**{name}:** {text}\n".format(**a)
                if action:
                    if len(action) < 1024:
                        embed_queue[-1].add_field(name="Actions", value=action)
                    elif len(action) < 2048:
                        embed_queue.append(discord.Embed(colour=color, description=action, title="Actions"))
                    else:
                        embed_queue.append(discord.Embed(colour=color, title="Actions"))
                        action_all = [action[i:i + 2040] for i in range(0, len(action), 2040)]
                        embed_queue[-1].description = action_all[0]
                        for a in action_all[1:]:
                            embed_queue.append(discord.Embed(colour=color, description=a))

            if "reaction" in monster:
                reaction = ""
                a = monster["reaction"]
                if isinstance(a['text'], list):
                    a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                if reaction:
                    if len(reaction) < 1024:
                        embed_queue[-1].add_field(name="Reactions", value=reaction)
                    elif len(reaction) < 2048:
                        embed_queue.append(discord.Embed(colour=color, description=reaction, title="Reactions"))
                    else:
                        embed_queue.append(discord.Embed(colour=color, title="Reactions"))
                        reaction_all = [reaction[i:i + 2040] for i in range(0, len(reaction), 2040)]
                        embed_queue[-1].description = reaction_all[0]
                        for a in reaction_all[1:]:
                            embed_queue.append(discord.Embed(colour=color, description=a))

            if "legendary" in monster:
                legendary = ""
                for a in monster["legendary"]:
                    if isinstance(a['text'], list):
                        a['text'] = '\n'.join(t for t in a['text'] if t is not None)
                    if a['name'] is not '':
                        legendary += "**{name}:** {text}\n".format(**a)
                    else:
                        legendary += "{text}\n".format(**a)
                if legendary:
                    if len(legendary) < 1024:
                        embed_queue[-1].add_field(name="Legendary Actions", value=legendary)
                    elif len(legendary) < 2048:
                        embed_queue.append(
                            discord.Embed(colour=color, description=legendary, title="Legendary Actions"))
                    else:
                        embed_queue.append(discord.Embed(colour=color, title="Legendary Actions"))
                        legendary_all = [legendary[i:i + 2040] for i in range(0, len(legendary), 2040)]
                        embed_queue[-1].description = legendary_all[0]
                        for a in legendary_all[1:]:
                            embed_queue.append(discord.Embed(colour=color, description=a))

        else:
            monster['hp'] = int(monster['hp'].split(' (')[0])
            monster['ac'] = int(monster['ac'].split(' (')[0])
            monster['size'] = parsesize(monster['size'])
            monster['type'] = ','.join(monster['type'].split(',')[:-1])
            if monster["hp"] < 10:
                monster["hp"] = "Very Low"
            elif 10 <= monster["hp"] < 50:
                monster["hp"] = "Low"
            elif 50 <= monster["hp"] < 100:
                monster["hp"] = "Medium"
            elif 100 <= monster["hp"] < 200:
                monster["hp"] = "High"
            elif 200 <= monster["hp"] < 400:
                monster["hp"] = "Very High"
            elif 400 <= monster["hp"]:
                monster["hp"] = "Godly"

            if monster["ac"] < 6:
                monster["ac"] = "Very Low"
            elif 6 <= monster["ac"] < 9:
                monster["ac"] = "Low"
            elif 9 <= monster["ac"] < 15:
                monster["ac"] = "Medium"
            elif 15 <= monster["ac"] < 17:
                monster["ac"] = "High"
            elif 17 <= monster["ac"] < 22:
                monster["ac"] = "Very High"
            elif 22 <= monster["ac"]:
                monster["ac"] = "Godly"

            for stat in ["str", "dex", "con", "wis", "int", "cha"]:
                monster[stat] = int(monster[stat])
                if monster[stat] <= 3:
                    monster[stat] = "Very Low"
                elif 3 < monster[stat] <= 7:
                    monster[stat] = "Low"
                elif 7 < monster[stat] <= 15:
                    monster[stat] = "Medium"
                elif 15 < monster[stat] <= 21:
                    monster[stat] = "High"
                elif 21 < monster[stat] <= 25:
                    monster[stat] = "Very High"
                elif 25 < monster[stat]:
                    monster[stat] = "Godly"

            if monster.get("languages"):
                monster["languages"] = len(monster["languages"].split(", "))
            else:
                monster["languages"] = 0

            embed_queue[-1].description = "{size} {type}.\n" \
                                          "**AC:** {ac}.\n**HP:** {hp}.\n**Speed:** {speed}\n" \
                                          "**STR:** {str} **DEX:** {dex} **CON:** {con}\n**WIS:** {wis} **INT:** {int} **CHA:** {cha}\n" \
                                          "**Languages:** {languages}\n".format(**monster)

            if "trait" in monster:
                embed_queue[-1].add_field(name="Special Abilities", value=str(len(monster["trait"])))

            if "action" in monster:
                embed_queue[-1].add_field(name="Actions", value=str(len(monster["action"])))

            if "reaction" in monster:
                embed_queue[-1].add_field(name="Reactions", value=str(len(monster["reaction"])))

            if "legendary" in monster:
                embed_queue[-1].add_field(name="Legendary Actions", value=str(len(monster["legendary"])))

        embed_queue[0].set_thumbnail(url=f"https://astranauta.github.io/img/{src}/{parse.quote(monster['name'])}.png")

        for embed in embed_queue:
            if pm:
                await self.bot.send_message(ctx.message.author, embed=embed)
            else:
                await self.bot.say(embed=embed)

    @commands.command(pass_context=True)
    async def spell(self, ctx, *, name: str):
        """Looks up a spell."""

        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

        self.bot.botStats["spells_looked_up_session"] += 1
        self.bot.db.incr('spells_looked_up_life')

        result = searchSpell(name)
        if result is None:
            return await self.bot.say('Spell not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r, r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')
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
        else:
            higher_levels = None

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
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

        self.bot.botStats["items_looked_up_session"] += 1
        self.bot.db.incr('items_looked_up_life')

        result = searchItem(name)
        if result is None:
            return await self.bot.say('Item not found.')
        strict = result[1]
        results = result[0]

        if strict:
            result = results
        else:
            if len(results) == 1:
                result = results[0]
            else:
                result = await get_selection(ctx, [(r['name'], r) for r in results])
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        embed = EmbedWithAuthor(ctx)
        item = result

        def parsetype(_type):
            if _type == "G": return "Adventuring Gear"
            if _type == "SCF": return "Spellcasting Focus"
            if _type == "AT": return "Artisan Tool"
            if _type == "T": return "Tool"
            if _type == "GS": return "Gaming Set"
            if _type == "INS": return "Instrument"
            if _type == "A": return "Ammunition"
            if _type == "M": return "Melee Weapon"
            if _type == "R": return "Ranged Weapon"
            if _type == "LA": return "Light Armor"
            if _type == "MA": return "Medium Armor"
            if _type == "HA": return "Heavy Armor"
            if _type == "S": return "Shield"
            if _type == "W": return "Wondrous Item"
            if _type == "P": return "Potion"
            if _type == "ST": return "Staff"
            if _type == "RD": return "Rod"
            if _type == "RG": return "Ring"
            if _type == "WD": return "Wand"
            if _type == "SC": return "Scroll"
            if _type == "EXP": return "Explosive"
            if _type == "GUN": return "Firearm"
            if _type == "SIMW": return "Simple Weapon"
            if _type == "MARW": return "Martial Weapon"
            if _type == "$": return "Valuable Object"
            return "n/a"

        def parsedamagetype(damagetype):
            if damagetype == "B": return "bludgeoning"
            if damagetype == "P": return "piercing"
            if damagetype == "S": return "slashing"
            if damagetype == "N": return "necrotic"
            if damagetype == "R": return "radiant"
            return 'n/a'

        def parseproperty(_property):
            if _property == "A": return "ammunition"
            if _property == "LD": return "loading"
            if _property == "L": return "light"
            if _property == "F": return "finesse"
            if _property == "T": return "thrown"
            if _property == "H": return "heavy"
            if _property == "R": return "reach"
            if _property == "2H": return "two-handed"
            if _property == "V": return "versatile"
            if _property == "S": return "special"
            if _property == "RLD": return "reload"
            if _property == "BF": return "burst fire"
            return "n/a"

        itemDict = {}
        itemDict['name'] = item['name']
        itemDict['type'] = ', '.join(parsetype(t) for t in item['type'].split(','))
        itemDict['rarity'] = item.get('rarity')
        itemDict['type_and_rarity'] = itemDict['type'] + (
            (', ' + itemDict['rarity']) if itemDict['rarity'] is not None else '')
        itemDict['value'] = (item.get('value', 'n/a') + (', ' if 'weight' in item else '')) if 'value' in item else ''
        itemDict['weight'] = (item.get('weight', 'n/a') + (
            ' lb.' if item.get('weight', 'n/a') == '1' else ' lbs.')) if 'weight' in item else ''
        itemDict['weight_and_value'] = itemDict['value'] + itemDict['weight']
        itemDict['damage'] = ''
        for iType in item['type'].split(','):
            if iType in ('M', 'R', 'GUN'):
                itemDict['damage'] = (item.get('dmg1', 'n/a') + ' ' + parsedamagetype(
                    item.get('dmgType', 'n/a'))) if 'dmg1' in item and 'dmgType' in item else ''
            if iType == 'S': itemDict['damage'] = "AC +" + item.get('ac', 'n/a')
            if iType == 'LA': itemDict['damage'] = "AC " + item.get('ac', 'n/a') + '+ DEX'
            if iType == 'MA': itemDict['damage'] = "AC " + item.get('ac', 'n/a') + '+ DEX (Max 2)'
            if iType == 'HA': itemDict['damage'] = "AC " + item.get('ac', 'n/a')
        itemDict['properties'] = ""
        for prop in item.get('property', '').split(','):
            if prop == '': continue
            a = b = prop
            a = parseproperty(a)
            if b == 'V': a += " (" + item.get('dmg2', 'n/a') + ")"
            if b in ('T', 'A'): a += " (" + item.get('range', 'n/a') + "ft.)"
            if b == 'RLD': a += " (" + item.get('reload', 'n/a') + " shots)"
            if len(itemDict['properties']): a = ', ' + a
            itemDict['properties'] += a
        itemDict['damage_and_properties'] = (itemDict['damage'] + ' - ' + itemDict['properties']) if itemDict[
                                                                                                         'properties'] is not '' else \
            itemDict['damage']
        itemDict['damage_and_properties'] = (' --- ' + itemDict['damage_and_properties']) if itemDict[
                                                                                                 'weight_and_value'] is not '' and \
                                                                                             itemDict[
                                                                                                 'damage_and_properties'] is not '' else \
            itemDict['damage_and_properties']

        embed.title = itemDict['name']
        embed.description = f"*{itemDict['type_and_rarity']}*\n{itemDict['weight_and_value']}{itemDict['damage_and_properties']}"

        text = '\n'.join(a for a in item['text'] if a is not None and 'Rarity:' not in a and 'Source:' not in a)
        if len(text) > 5500:
            text = text[:5500] + "..."

        field_name = "Description"
        for piece in [text[i:i + 1024] for i in range(0, len(text), 1024)]:
            embed.add_field(name=field_name, value=piece)
            field_name = "con't"

        if pm:
            await self.bot.send_message(ctx.message.author, embed=embed)
        else:
            await self.bot.say(embed=embed)


def parsesize(size):
    if size == "T": size = "Tiny";
    if size == "S": size = "Small";
    if size == "M": size = "Medium";
    if size == "L": size = "Large";
    if size == "H": size = "Huge";
    if size == "G": size = "Gargantuan";
    return size


def parsesource(src):
    source = src.strip()
    if source == "monster manual": source = "MM";
    if source == "Volo's Guide": source = "VGM";
    if source == "elemental evil": source = "PotA";
    if source == "storm kings thunder": source = "SKT";
    if source == "tyranny of dragons": source = "ToD";
    if source == "out of the abyss": source = "OotA";
    if source == "curse of strahd": source = "CoS";
    if source == "lost mine of phandelver": source = "LMoP";
    if source == "Tales from the Yawning Portal": source = "TYP";
    if source == "tome of beasts": source = "ToB 3pp";
    if source == "Plane Shift Amonkhet": source = "PSA";
    if source == "Plane Shift Innistrad": source = "PSI";
    if source == "Plane Shift Kaladesh": source = "PSK";
    if source == "Plane Shift Zendikar": source = "PSZ";
    if source == "Tomb of Annihilation": source = "ToA";
    if source == "The Tortle Package": source = "TTP";
    return source
