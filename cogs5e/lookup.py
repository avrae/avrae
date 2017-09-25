'''
Created on Nov 29, 2016

@author: andrew
'''
import random
import shlex
import textwrap

import discord
from discord.ext import commands

from cogs5e.funcs.lookupFuncs import searchCondition, searchRule, searchRacialFeat, searchFeat, \
    searchClassFeat, searchMonster, getMonster, searchSpell, getSpell, searchItem, getItem, searchBackground, \
    searchRace, searchClass
from cogs5e.models.embeds import EmbedWithAuthor
from utils import checks
from utils.functions import discord_trim, get_positivity

CLASS_RESOURCE_MAP = {'slots': "Spell Slots", # a weird one - see fighter
                      'spellsknown': "Spells Known",
                      'rages': "Rages", 'ragedamage': "Rage Damage",
                      'martialarts': "Martial Arts", 'kipoints': "Ki", 'unarmoredmovement': "Unarmored Movement",
                      'sorcerypoints': "Sorcery Points",
                      'invocationsknown': "Invocations Known", 'spellslots': "Spell Slots", 'slotlevel': "Slot Level",
                      'talentsknown': "Talents Known", 'disciplinesknown': "Disciplines Known",
                      'psipoints': "Psi Points", 'psilimit': "Psi Limit"}

class Lookup:
    """Commands to help look up items (WIP), status effects, rules, etc."""

    def __init__(self, bot):
        self.bot = bot
        self.settings = self.bot.db.not_json_get("lookup_settings", {}) if bot is not None else {}

    async def get_selection(self, results, ctx, returns_object=True):
        results = results[:10]  # sanity
        if returns_object:
            names = [r['name'] for r in results]
        else:
            names = results
        embed = discord.Embed()
        embed.title = "Multiple Matches Found"
        selectStr = " Which one were you looking for? (Type the number, or \"c\" to cancel)\n"
        for i, r in enumerate(names):
            selectStr += f"**[{i+1}]** - {r}\n"
        embed.description = selectStr
        embed.colour = random.randint(0, 0xffffff)
        selectMsg = await self.bot.send_message(ctx.message.channel, embed=embed)

        def chk(msg):
            valid = [str(v) for v in range(1, len(results) + 1)] + ["c"]
            return msg.content in valid

        m = await self.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=selectMsg.channel,
                                            check=chk)

        if m is None or m.content == "c": return None
        return results[int(m.content) - 1]

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
                result = await self.get_selection(results, ctx)
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
                result = await self.get_selection(results, ctx)
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
                result = await self.get_selection(results, ctx)
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
                result = await self.get_selection(results, ctx)
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
                result = await self.get_selection(results, ctx)
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
        trait_str = ', '.join(t['name'] for t in result.get('trait', []))
        embed.add_field(name="Traits", value=trait_str, inline=False)
        embed.set_footer(text="Use !racefeat to look up a trait.")

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
                result = await self.get_selection(results, ctx)
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
                result = await self.get_selection(results, ctx)
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
                        if not f.get('_optional') and not (f['name'] in ("Starting Proficiencies", "Starting Equipment")):
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
                    if isinstance(val, dict): # EK/AT/Art
                        continue
                    if result['name'] == 'Warlock': # Warlock
                        res = 'Cantrips Known'
                        value = val.split(',')[0]
                    else:
                        slots = val.split(',')
                        value = f"`Cantrips` - {slots[0]}"
                        for i, l in enumerate(slots[1:]):
                            value += f"`; L{i+1}` - {l}"
                if res == 'spellsknown' and isinstance(level_resources.get('slots'), dict): # EK/AT/Art
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
                result = await self.get_selection(results, ctx)
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
    async def monster(self, ctx, *, monstername: str):
        """Looks up a monster.
        Generally requires a Game Master role to show full stat block.
        Game Master Roles: GM, DM, Game Master, Dungeon Master"""

        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
            visible_roles = ['gm', 'game master', 'dm', 'dungeon master']
            if self.settings.get(guild_id, {}).get("req_dm_monster", True):
                visible = 0
                for ro in visible_roles:
                    visible = visible + 1 if ro in [str(r).lower() for r in ctx.message.author.roles] else visible
                visible = True if visible > 0 else False
            else:
                visible = True
        except:
            visible = True
            pm = False

        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')

        result = searchMonster(monstername)
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
                result = await self.get_selection(results, ctx, returns_object=False)
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        result = getMonster(result, visible=visible)

        # do stuff here
        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)

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
                result = await self.get_selection(results, ctx, returns_object=False)
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        result = getSpell(result)

        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)

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
                result = await self.get_selection(results, ctx, returns_object=False)
                if result is None: return await self.bot.say('Selection timed out or was cancelled.')

        result = getItem(result)

        for r in discord_trim(result):
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)
