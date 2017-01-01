'''
Created on Dec 26, 2016

@author: andrew
'''
from datetime import timedelta, datetime
from math import floor
import os
import time

import discord
from discord.ext import commands
import psutil

from utils import checks


class Core:
    '''
    Core utilty and general commands.
    '''
    
    def __init__(self, bot):
        self.bot = bot
        self.quiet_mask = 0x01
        self.verbose_mask = 0x02
        self.debug_mask = 0x04
        self.monitor_mask = 0x08
        self.start_time = time.monotonic()
        
    @commands.command(pass_context=True)
    @checks.admin_or_permissions(manage_messages=True)
    async def purge(self, ctx, num):
        """Purges messages from the channel.
        Usage: !purge <Number of messages to purge>
        Requires: Bot Admin or Manage Messages"""
        if self.bot.mask & self.monitor_mask:
            await self.bot.send_message(self.bot.owner, "Purging {} messages from {}.".format(str(int(num) + 1), ctx.message.server))
        try:
            await self.bot.purge_from(ctx.message.channel, limit=(int(num) + 1))
        except Exception as e:
            await self.bot.say('Failed to purge: ' + str(e))
        
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def bitmask(self, ctx, *args):
        """Edits/shows the bitmask.
        Requires: Owner"""
        if args:
            mask = int(args[0], base=2)
            if not len(args[0]) == 8:
                await self.bot.say("Invalid bitmask!")
            else:
                with open('./resources.txt', 'w') as f:
                    f.write("{0:0>8b}".format(mask))
        await self.bot.say("```Bitmask: {0:0>8b}```".format(mask))
        
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def toggle_flag(self, ctx, flag : str):
        """Toggles a bitmask flag.
        Requires: Owner"""
        if flag.lower() == 'verbose':
            self.bot.mask = self.bot.mask ^ self.verbose_mask
        elif flag.lower() == 'quiet':
            self.bot.mask = self.bot.mask ^ self.quiet_mask
        elif flag.lower() == 'debug':
            self.bot.mask = self.bot.mask ^ self.debug_mask
        elif flag.lower() == 'monitor':
            self.bot.mask = self.bot.mask ^ self.monitor_mask
        with open('./resources.txt', 'w') as f:
            f.write("{0:0>8b}".format(self.bot.mask))
        await self.bot.say('Toggled flag ' + flag + "```Bitmask: {0:0>8b}```".format(self.bot.mask))
        
    @commands.command(pass_context=True)
    async def bug(self, ctx, *, report:str):
        """Reports a bug to the developer."""
        await self.bot.send_message(self.bot.owner, "Bug reported by {} from {}:\n{}".format(ctx.message.author.mention, ctx.message.server, report))
        await self.bot.say("Bug report sent to developer! He'll get to it eventually.")
        
    @commands.command(hidden=True)
    @checks.mod_or_permissions(manage_nicknames=True)
    async def avatar(self, user : discord.User):
        """Gets a user's avatar.
        Usage: !avatar <USER>
        Requires: Bot Mod or Manage Nicknames"""
        if user.avatar_url is not "":
            await self.bot.say(user.avatar_url)
        else:
            await self.bot.say(user.display_name + " is using the default avatar.")
    
    @commands.command(pass_context=True)
    async def ping(self, ctx):
        """Checks the ping time to the bot."""
        now = datetime.utcnow()
        pong = await self.bot.say("Pong.")
        delta = pong.timestamp - now
        msec = floor(delta.total_seconds() * 1000)
        await self.bot.edit_message(pong, "Pong.\nPing = {} ms.".format(msec))
        
    @commands.command()
    async def invite(self):
        """Prints a link to invite Avrae to your server."""
        await self.bot.say("https://discordapp.com/oauth2/authorize?&client_id=***REMOVED***&scope=bot&permissions=36727808")
        
    @commands.command(aliases=['stats'])
    async def about(self):
        """Information about the bot."""
        embed = discord.Embed(description='Avrae, a bot to streamline D&D 5e online.')
        embed.title = "Invite Avrae to your server!"
        embed.url = "https://discordapp.com/oauth2/authorize?&client_id=***REMOVED***&scope=bot&permissions=36727808"
        embed.colour = 0xec3333
        embed.set_author(name=str(self.bot.owner), icon_url=self.bot.owner.avatar_url)
        total_members = sum(len(s.members) for s in self.bot.servers)
        total_online  = sum(1 for m in self.bot.get_all_members() if m.status != discord.Status.offline)
        unique_members = set(self.bot.get_all_members())
        unique_online = sum(1 for m in unique_members if m.status != discord.Status.offline)
        text = len([c for c in self.bot.get_all_channels() if c.type is discord.ChannelType.text])
        voice = len([c for c in self.bot.get_all_channels() if c.type is discord.ChannelType.voice])
        members = '%s total\n%s online\n%s unique\n%s unique online' % (total_members, total_online, len(unique_members), unique_online)
        embed.add_field(name='Members', value=members)
        embed.add_field(name='Channels', value='{} total\n{} text\n{} voice'.format(text + voice, text, voice))
        embed.add_field(name='Uptime', value=str(timedelta(seconds=round(time.monotonic() - self.start_time))))
        embed.set_footer(text='May the RNG be with you', icon_url='http://www.clipartkid.com/images/25/six-sided-dice-clip-art-at-clker-com-vector-clip-art-online-royalty-tUAGdd-clipart.png')
        commands_run = "{commands_used_life} total\n{dice_rolled_life} dice rolled\n{spells_looked_up_life} spells looked up\n{monsters_looked_up_life} monsters looked up".format(**self.bot.botStats)
        embed.add_field(name="Commands Run", value=commands_run)
        embed.add_field(name="Servers", value=len(self.bot.servers))
        memory_usage = psutil.Process().memory_full_info().uss / 1024**2
        embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
        embed.add_field(name='Credits', value='Bot coded by @zhu.exe#4211\nDice foundation contributed by @Iridian#7625\ndiscord.py created by @Danny#0007\nHelp me buy a cup of coffee [here](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=HUDJTWSTPF7ML&lc=US&item_name=Avrae%20Developer&currency_code=USD&bn=PP%2dDonationsBF%3abtn_donateCC_LG%2egif%3aNonHosted)!', inline=False)
        
        await self.bot.say(embed=embed)
        
    @commands.command(pass_context=True)
    async def multiline(self, ctx, *, commands:str):
        """Runs each line as a separate command.
        Usage:
        "!multiline
        !roll 1d20
        !spell Fly
        !monster Rat"
        """
        commands = commands.splitlines()
        for c in commands:
            ctx.message.content = c
            if not hasattr(self.bot, 'global_prefixes'): # bot's still starting up!
                return
            try:
                guild_prefix = self.bot.global_prefixes.get(ctx.message.server.id, self.bot.prefix)
            except:
                guild_prefix = self.bot.prefix
            if ctx.message.content.startswith(guild_prefix):
                ctx.message.content = ctx.message.content.replace(guild_prefix, self.bot.prefix, 1)
            elif ctx.message.content.startswith(self.bot.prefix): return
            await self.bot.process_commands(ctx.message)
                
        