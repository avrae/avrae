'''
Created on Nov 29, 2016

@author: andrew
'''

import asyncio
import json
import math
import random
import re
import shlex

import discord
from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import searchCondition, searchMonster, searchSpell, \
    searchItem, searchRule, searchFeat, searchRacialFeat, searchClassFeat
from utils import checks
from utils.functions import discord_trim, print_table, list_get, get_positivity, \
    fuzzywuzzy_search, fuzzywuzzy_search_all


class Lookup:
    """Commands to help look up items (WIP), status effects, rules, etc."""
    
    def __init__(self, bot):
        self.bot = bot
        self.settings = self.bot.db.not_json_get("lookup_settings", {}) if bot is not None else {}
            
    @commands.command(pass_context=True, aliases=['status'])
    async def condition(self, ctx, *, name : str):
        """Looks up a condition."""
        try:
            guild_id = ctx.message.server.id 
            pm = self.settings.get(guild_id, {}).get("pm_result", False)    
        except:
            pm = False
        
        result = searchCondition(name, search=fuzzywuzzy_search_all)
        if result is None:
            return await self.bot.say('Condition not found.')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Condition not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchCondition(top_key)
        
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
    async def rule(self, ctx, *, name : str):
        """Looks up a rule."""
        try:
            guild_id = ctx.message.server.id 
            pm = self.settings.get(guild_id, {}).get("pm_result", False)    
        except:
            pm = False
        
        result = searchRule(name, search=fuzzywuzzy_search_all)
        if result is None:
            return await self.bot.say('Rule not found. PM the bot author if you think this rule is missing.')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Rule not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchRule(top_key)
        
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
        
        result = searchFeat(name, search=fuzzywuzzy_search_all)
        if result is None:
            return await self.bot.say('Feat not found.')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Feat not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchFeat(top_key)
        
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
        
        result = searchRacialFeat(name, search=fuzzywuzzy_search_all)
        if result is None:
            return await self.bot.say('Racial feature not found.')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Racial feature not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchRacialFeat(top_key)
        
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
        
        result = searchClassFeat(name, search=fuzzywuzzy_search_all)
        if result is None:
            return await self.bot.say('Class feature not found.')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Class feature not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchClassFeat(top_key)
        
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
        
        result = searchMonster(monstername, visible=visible, search=fuzzywuzzy_search_all)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr('monsters_looked_up_life')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Monster not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchMonster(top_key, visible=visible)
    
        # do stuff here
        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)
            
    @commands.command(pass_context=True)
    async def spell(self, ctx, *, args : str):
        """Looks up a spell."""
        valid_args = {'--class', '--level', '--school'}
        
        try:
            guild_id = ctx.message.server.id 
            pm = self.settings.get(guild_id, {}).get("pm_result", False)    
        except:
            pm = False
        
        result = searchSpell(args, search=fuzzywuzzy_search_all)
        self.bot.botStats["spells_looked_up_session"] += 1
        self.bot.db.incr('spells_looked_up_life')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Spell not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchSpell(top_key)
        
        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)
                
    @commands.command(pass_context=True, name='item')
    async def item_lookup(self, ctx, *, itemname):
        """Looks up an item."""
        try:
            guild_id = ctx.message.server.id 
            pm = self.settings.get(guild_id, {}).get("pm_result", False)    
        except:
            pm = False
        
        result = searchItem(itemname, search=fuzzywuzzy_search_all)
        self.bot.botStats["items_looked_up_session"] += 1
        self.bot.db.incr('items_looked_up_life')
        
        top = result[0]
        top_score = top[1]
        top_key = top[0]
        if top_score < 60:
            results = "Item not found! Did you mean:\n"
            results += '\n'.join("{0} ({1}% match)".format(a[0], a[1]) for a in result)
            return await self.bot.say(results)
        else:
            result = searchItem(top_key)

        for r in discord_trim(result):
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)
                
    
    
    