'''
Created on Sep 23, 2016

@author: andrew
'''
import asyncio
import os
import sys
import traceback

import discord
from discord.channel import PrivateChannel
from discord.ext import commands

from utils import checks


class AdminUtils:
    '''
    Administrative Utilities.
    '''


    def __init__(self, bot):
        self.bot = bot
        self.muted = []
        self.assume_dir_control_chan = None
    
    
    @commands.command(hidden=True)
    @checks.is_owner()
    async def restart(self):
        """Restarts Avrae. May fail sometimes due to bad programming on zhu.exe's end.
        Requires: Owner"""
        await self.bot.say("Byeeeeeee!")
        await self.bot.logout()
        sys.exit()
            
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def chanSay(self, ctx, channel : str, * , message : str):
        """Like .say, but works across servers. Requires channel id."""
        channel = self.bot.get_channel(channel)
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
    async def servInfo(self, server:str=None):
        out = ''
        if server is None:
            for s in sorted(self.bot.servers, key=lambda k: len(k.members), reverse=True):
                out += "\n{} ({}, {} members)".format(s, s.id, len(s.members))
        else:
            s = self.bot.get_server(server)
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
            
    @commands.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def assume_direct_control(self, ctx, chan:str):
        """Assumes direct control of Avrae."""
        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])
    
            # remove `foo`
            return content.strip('` \n')
        self.assume_dir_control_chan = self.bot.get_channel(chan)
        if self.assume_dir_control_chan is None:
            self.assume_dir_control_chan = await self.bot.get_user_info(chan)
        while True:
            response = await self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                       check=lambda m: m.content.startswith('`'))
            cleaned = cleanup_code(response.content)
            if cleaned in ('quit', 'exit', 'exit()'):
                await self.bot.say('Exiting.')
                self.assume_dir_control_chan = None
                return
            else:
                await self.bot.send_message(self.assume_dir_control_chan, cleaned)
            
    async def on_message(self, message):
        if message.author in self.muted:
            try:
                await self.bot.delete_message(message)
            except:
                pass
        if self.assume_dir_control_chan is not None:
            if isinstance(message.channel, PrivateChannel):
                if message.channel.user.id == self.assume_dir_control_chan.id:
                    await self.bot.send_message(self.bot.owner, "**" + message.author.display_name + "**: " + message.content)
            elif message.channel.id == self.assume_dir_control_chan.id:
                await self.bot.send_message(self.bot.owner, "**" + message.author.display_name + "**: " + message.content)
        
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
    
