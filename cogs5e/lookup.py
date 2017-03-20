'''
Created on Nov 29, 2016

@author: andrew
'''

import asyncio
import json
import math
import re
import shlex

import discord
from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import searchCondition, searchMonster, searchSpell, \
    searchItem
from utils import checks
from utils.functions import discord_trim, print_table, list_get, get_positivity


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
        
        result = searchCondition(name)
        if result is None:
            return await self.bot.say('Condition not found.')
        
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
    
    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def lookup_settings(self, ctx, *, args:str):
        """Changes settings for the lookup module.
        Usage: !lookup_settings -req_dm_monster True
        Current settings are: -req_dm_monster [True/False] - Requires a Game Master role to show a full monster stat block.
                              -pm_result [True/False] - PMs the result of the lookup to reduce spam."""
        args = shlex.split(args.lower())
        guild_id = ctx.message.server.id
        guild_settings = self.settings.get(guild_id, {})
        if '-req_dm_monster' in args:
            try:
                setting = args[args.index('-req_dm_monster') + 1]
            except IndexError:
                setting = 'True'
            setting = get_positivity(setting)
            guild_settings['req_dm_monster'] = setting if setting is not None else True
        if '-pm_result' in args:
            try:
                setting = args[args.index('-pm_result') + 1]
            except IndexError:
                setting = 'False'
            setting = get_positivity(setting)
            guild_settings['pm_result'] = setting if setting is not None else False
            
        self.settings[guild_id] = guild_settings
        self.bot.db.not_json_set("lookup_settings", self.settings)
        await self.bot.say("Lookup settings set.")
    
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
        
        result = searchMonster(monstername, visible=visible)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.botStats["monsters_looked_up_life"] += 1
    
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
        
        result = searchSpell(args)
        self.bot.botStats["spells_looked_up_session"] += 1
        self.bot.botStats["spells_looked_up_life"] += 1

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
        
        result = searchItem(itemname)
        self.bot.botStats["items_looked_up_session"] += 1
        self.bot.botStats["items_looked_up_life"] += 1

        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r)
                
    
    
    