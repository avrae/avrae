'''
Created on Nov 29, 2016

@author: andrew
'''
import random
import shlex

import discord
from discord.ext import commands

from cogs5e.funcs.lookupFuncs import searchCondition, searchRule, searchRacialFeat, searchFeat, \
    searchClassFeat, searchMonster, getMonster, searchSpell, getSpell, searchItem, getItem
from utils import checks
from utils.functions import discord_trim, get_positivity


class Lookup:
    """Commands to help look up items (WIP), status effects, rules, etc."""
    
    def __init__(self, bot):
        self.bot = bot
        self.settings = self.bot.db.not_json_get("lookup_settings", {}) if bot is not None else {}

    async def get_selection(self, results, ctx, returns_object=True):
        results = results[:10] # sanity
        if returns_object: names = [r['name'] for r in results]
        else: names = results
        embed = discord.Embed()
        embed.title = "Multiple Matches Found"
        selectStr = " Which one were you looking for? (Type the number, or \"c\" to cancel)\n"
        for i, r in enumerate(names):
            selectStr += f"**[{i+1}]** - {r}\n"
        embed.description = selectStr
        embed.color = random.randint(0, 0xffffff)
        selectMsg = await self.bot.send_message(ctx.message.channel, embed=embed)

        def chk(msg):
            valid = [str(v) for v in range(1, len(results) + 1)] + ["c"]
            return msg.content in valid

        m = await self.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=selectMsg.channel,
                                            check=chk)

        if m is None or m.content == "c": return None
        return results[int(m.content) - 1]
            
    @commands.command(pass_context=True, aliases=['status'])
    async def condition(self, ctx, *, name : str):
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
        
        conName = result['name']
        conHeader = '-' * len(conName)
        conDesc = result['desc']
        out = "```markdown\n{0}\n{1}\n{2}```".format(conName, conHeader, conDesc)

        # do stuff here
        for r in discord_trim(out):
            await self.bot.send_message(destination, r)
                
    @commands.command(pass_context=True)
    async def rule(self, ctx, *, name : str):
        """Looks up a rule."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

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

        conName = result['name']
        conHeader = '-' * len(conName)
        conDesc = result['desc']
        out = "```markdown\n{0}\n{1}\n{2}```".format(conName, conHeader, conDesc)

        # do stuff here
        for r in discord_trim(out):
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)

    @commands.command(pass_context=True)
    async def feat(self, ctx, *, name : str):
        """Looks up a feat."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

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
            result['text'] = '\n'.join(t for t in result.get('text', []) if t is not None and not t.startswith('Source:'))
        result['prerequisite'] = result.get('prerequisite') or "None"
        out = "**{name}**\n**Source**: {source}\n*Prerequisite: {prerequisite}*\n\n{text}".format(**result)

        # do stuff here
        for r in discord_trim(out):
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)

    @commands.command(pass_context=True)
    async def racefeat(self, ctx, *, name : str):
        """Looks up a racial feature."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

        result = searchRacialFeat(name)
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
        out = "**{name}**\n{text}".format(**result)

        # do stuff here
        for r in discord_trim(out):
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)

    @commands.command(pass_context=True)
    async def classfeat(self, ctx, *, name : str):
        """Looks up a class feature."""
        try:
            guild_id = ctx.message.server.id
            pm = self.settings.get(guild_id, {}).get("pm_result", False)
        except:
            pm = False

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
        out = "**{name}**\n{text}".format(**result)

        # do stuff here
        for r in discord_trim(out):
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)

    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def lookup_settings(self, ctx, *, args:str):
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
    async def monster(self, ctx, *, monstername : str):
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
    async def spell(self, ctx, *, name : str):
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



    