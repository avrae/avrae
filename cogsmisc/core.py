'''
Created on Dec 26, 2016

@author: andrew
'''
from datetime import timedelta, datetime
from math import floor
import os
import time

import discord
from discord.channel import PrivateChannel
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
        
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def bitmask(self, ctx, *args):
        """Edits/shows the bitmask.
        Requires: Owner"""
        if args:
            self.bot.mask = int(args[0], base=2)
            if not len(args[0]) == 8:
                await self.bot.say("Invalid bitmask!")
            else:
                with open('./resources.txt', 'w') as f:
                    f.write("{0:0>8b}".format(self.bot.mask))
        await self.bot.say("```Bitmask: {0:0>8b}```".format(self.bot.mask))
        
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
        
    @commands.command(pass_context=True, aliases=['feedback'])
    async def bug(self, ctx, *, report:str):
        """Reports a bug to the developer."""
        if not isinstance(ctx.message.channel, PrivateChannel):
            await self.bot.send_message(self.bot.owner, "Bug reported by {} ({}) from {} ({}):\n{}".format(ctx.message.author.mention, str(ctx.message.author), ctx.message.server, ctx.message.server.id, report))
        else:
            await self.bot.send_message(self.bot.owner, "Bug reported by {} ({}):\n{}".format(ctx.message.author.mention, str(ctx.message.author), report))
        await self.bot.say("Bug report sent to developer! He'll get to it eventually.")
        
    @commands.command(hidden=True, pass_context=True)
    async def avatar(self, ctx, user : discord.User=None):
        """Gets a user's avatar.
        Usage: !avatar <USER>"""
        if user is None:
            user = ctx.message.author
        if user.avatar_url is not "":
            await self.bot.say(user.avatar_url)
        else:
            await self.bot.say(user.display_name + " is using the default avatar.")
    
    @commands.command(pass_context=True)
    async def ping(self, ctx):
        """Checks the ping time to the bot."""
        now = datetime.utcnow()
        pong = await self.bot.say("Pong.")
        delta = datetime.utcnow() - now
        msec = floor(delta.total_seconds() * 1000)
        await self.bot.edit_message(pong, "Pong.\nPing = {} ms.".format(msec))
        
    @commands.command()
    async def invite(self):
        """Prints a link to invite Avrae to your server."""
        await self.bot.say("You can invite Avrae to your server here:\nhttps://discordapp.com/oauth2/authorize?&client_id=***REMOVED***&scope=bot&permissions=36727808")
        
    @commands.command()
    async def donate(self):
        """Prints a link to donate to the bot developer."""
        await self.bot.say("You can donate to me here:\n<https://www.paypal.me/avrae>\n\u2764")
        
    @commands.command(aliases=['stats', 'info'])
    async def about(self):
        """Information about the bot."""
        statKeys = ["dice_rolled_life", "spells_looked_up_life", "monsters_looked_up_life", "commands_used_life", "items_looked_up_life"]
        for k in statKeys:
            self.bot.botStats[k] = int(self.bot.db.get(k))
        embed = discord.Embed(description='Avrae, a bot to streamline D&D 5e online.')
        embed.title = "Invite Avrae to your server!"
        embed.url = "https://discordapp.com/oauth2/authorize?&client_id=***REMOVED***&scope=bot&permissions=36727808"
        embed.colour = 0xff3333
        embed.set_author(name=str(self.bot.owner), icon_url=self.bot.owner.avatar_url)
        total_members = sum(len(s.members) for s in self.bot.servers)
        total_online = sum(1 for m in self.bot.get_all_members() if m.status != discord.Status.offline)
        unique_members = set(self.bot.get_all_members())
        unique_online = sum(1 for m in unique_members if m.status != discord.Status.offline)
        text = len([c for c in self.bot.get_all_channels() if c.type is discord.ChannelType.text])
        voice = len([c for c in self.bot.get_all_channels() if c.type is discord.ChannelType.voice])
        members = '%s total\n%s online\n%s unique\n%s unique online' % (total_members, total_online, len(unique_members), unique_online)
        embed.add_field(name='Shard Members', value=members)
        embed.add_field(name='Shard Channels', value='{} total\n{} text\n{} voice'.format(text + voice, text, voice))
        embed.add_field(name='Uptime', value=str(timedelta(seconds=round(time.monotonic() - self.start_time))))
        embed.set_footer(text='May the RNG be with you | Build {} | Cluster {} | Shard {}'.format(self.bot.db.get('build_num'), floor(int(getattr(self.bot, 'shard_id', 0)) / 3) + 1, getattr(self.bot, 'shard_id', 0)), icon_url='http://www.clipartkid.com/images/25/six-sided-dice-clip-art-at-clker-com-vector-clip-art-online-royalty-tUAGdd-clipart.png')
        commands_run = "{commands_used_life} total\n{dice_rolled_life} dice rolled\n{spells_looked_up_life} spells looked up\n{monsters_looked_up_life} monsters looked up\n{items_looked_up_life} items looked up".format(**self.bot.botStats)
        embed.add_field(name="Commands Run", value=commands_run)
        embed.add_field(name="Servers", value=str(len(self.bot.servers)) + ' on this shard\n' + str(sum(a for a in self.bot.db.jget('shard_servers', {0: len(self.bot.servers)}).values())) + ' total')
        memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
        embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
        embed.add_field(name='About', value='Bot coded by @zhu.exe#4211\nFound a bug? Report it with `!bug`!\nHelp me buy a cup of coffee [here](https://www.paypal.me/avrae)!\nJoin the official testing server [here](https://discord.gg/pQbd4s6)!', inline=False)
        
        await self.bot.say(embed=embed)
                
        
