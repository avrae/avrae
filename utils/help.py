"""
Created on Jan 17, 2017

@author: andrew
"""
import inspect
import itertools
import re
from math import floor

import discord
from discord.errors import Forbidden
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType
from discord.ext.commands.core import Command
from discord.ext.commands.formatter import HelpFormatter


class Help:
    
    def __init__(self, bot):
        self._mentions_transforms = {
            '@everyone': '@\u200beveryone',
            '@here': '@\u200bhere'
        }
        
        self._mention_pattern = re.compile('|'.join(self._mentions_transforms.keys()))
        
        self.formatter = CustomHelpFormatter(width = 2000)
        self.bot = bot
    
    @commands.command(name='help', aliases=['commands'], pass_context=True)
    @commands.cooldown(1, 2, BucketType.user)
    async def _default_help_command(self, ctx, *commands : str):
        """Shows this message.
        <argument> - This means the argument is __**required**__.
        [argument] - This means the argument is __**optional**__.
        [A|B] - This means the it can be __**either A or B**__.
        [argument...] - This means you can have multiple arguments.
        Now that you know the basics, it should be noted that __**you do not type in the brackets!**__"""
        bot = ctx.bot
        destination = ctx.message.author if bot.pm_help else ctx.message.channel
    
        def repl(obj):
            return self._mentions_transforms.get(obj.group(0), '')
    
        # help by itself just lists our own commands.
        if len(commands) == 0:
            embed = self.formatter.format_help_for(ctx, bot)
        elif len(commands) == 1:
            # try to see if it is a cog name
            name = self._mention_pattern.sub(repl, commands[0])
            command = None
            if name in bot.cogs:
                command = bot.cogs[name]
            else:
                command = bot.commands.get(name)
                if command is None:
                    try:
                        await bot.send_message(destination, bot.command_not_found.format(name))
                    except Forbidden:
                        await bot.send_message(ctx.message.channel, 'Error: I cannot send messages to this user or channel.')
                    return
    
            embed = self.formatter.format_help_for(ctx, command)
        else:
            name = self._mention_pattern.sub(repl, commands[0])
            command = bot.commands.get(name)
            if command is None:
                try:
                    await bot.send_message(destination, bot.command_not_found.format(name))
                except Forbidden:
                    await bot.send_message(ctx.message.channel, 'Error: I cannot send messages to this user or channel.')
                return
    
            for key in commands[1:]:
                try:
                    key = self._mention_pattern.sub(repl, key)
                    command = command.commands.get(key)
                    if command is None:
                        try:
                            await bot.send_message(destination, bot.command_not_found.format(key))
                        except Forbidden:
                            await bot.send_message(ctx.message.channel, 'Error: I cannot send messages to this user or channel.')
                        return
                except AttributeError:
                    try:
                        await bot.send_message(destination, bot.command_has_no_subcommands.format(command, key))
                    except Forbidden:
                        await bot.send_message(ctx.message.channel, 'Error: I cannot send messages to this user or channel.')
                    return
    
            embed = self.formatter.format_help_for(ctx, command)
        
        try:
            for e in embed:
                await bot.send_message(destination, embed=e)
        except Forbidden:
            await bot.send_message(ctx.message.channel, 'Error: I cannot send messages to this user or channel.')
        else:
            if bot.pm_help:
                await bot.send_message(ctx.message.channel, 'I have sent help to your PMs.')
        
class CustomHelpFormatter(HelpFormatter):
    
    def _get_subcommands(self, commands):
        out = []
        for name, command in commands:
            if name in command.aliases:
                # skip aliases
                continue

            entry = '**{0}** - {1}\n'.format(name, command.short_doc)
            shortened = self.shorten(entry)
            out.append(shortened)
        return ''.join(sorted(out))
    
    def get_ending_note(self):
        command_name = self.context.invoked_with
        return "Type {0}{1} command for more info on a command.\n" \
               "You can also type {0}{1} category for more info on a category.".format(self.clean_prefix, command_name)

    def format(self):
        """Handles the actual behaviour involved with formatting.
        To change the behaviour, this method should be overridden.
        Returns
        --------
        embed
            An embed.
        """
        
        embed = discord.Embed()
        self.embeds = [embed]
        length = 0

        # we need a padding of ~80 or so

        description = self.command.description if not self.is_cog() else inspect.getdoc(self.command)

        if description:
            # <description> portion
            embed.description = description
            length += len(description)

        if isinstance(self.command, Command):
            # <signature portion>
            signature = self.get_command_signature()
            embed.title = signature

            # <long doc> section
            if self.command.help:
                embed.description = self.command.help
                length += len(self.command.help)

            # end it here if it's just a regular command
            if not self.has_subcommands():
                return [embed]

        max_width = self.max_name_size

        def category(tup):
            cog = tup[1].cog_name
            # we insert the zero width space there to give it approximate
            # last place sorting position.
            return cog if cog is not None else '\u200bNo Category'
        
        current_embed = embed
        if self.is_bot():
            data = sorted(self.filter_command_list(), key=category)
            for category, commands in itertools.groupby(data, key=category):
                # there simply is no prettier way of doing this.
                commands = list(commands)
                if len(commands) > 0:
                    title = category
                    value = self._get_subcommands(commands)
                    length += len(value) + len(title)
                    field_length = len(value)
                    if length > 3500:
                        current_embed = discord.Embed()
                        self.embeds.append(current_embed)
                        length = 0
                    if field_length > 1024:
                        split = value.split('\n')
                        v1 = ""
                        v2 = ""
                        index = 0
                        while len(v1) + len(split[index]) < 1024:
                            v1 += split[index] + '\n'
                            index += 1
                        v2 = '\n'.join(split[index:])
                        current_embed.add_field(name=title, value=v1, inline=False)
                        current_embed.add_field(name=title + " Part 2", value=v2, inline=False)
                    else:
                        current_embed.add_field(name=title, value=value, inline=False)
        else:
            title = 'Commands'
            value = self._get_subcommands(self.filter_command_list())
            _v = []
            l = ""
            for val in value.split('\n'):
                val = f"\n{val}"
                if len(l) + len(val) > 1020:
                    _v.append(l)
                    l = ""
                l += val
            if l:
                _v.append(l)
            for i, v in enumerate(_v):
                if i == 0:
                    current_embed.add_field(name=title, value=v, inline=False)
                else:
                    current_embed.add_field(name="con't", value=v, inline=False)
        
        if length > 5500:
            current_embed = discord.Embed()
            self.embeds.append(current_embed)
            length = 0
        
        ending_note = self.get_ending_note()
        current_embed.add_field(name='More Help', value=ending_note, inline=False)
        return self.embeds