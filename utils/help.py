'''
Created on Jan 17, 2017

@author: andrew
'''
import asyncio
import inspect
import itertools
import re

import discord
from discord.ext import commands
from discord.ext.commands.core import Command
from discord.ext.commands.formatter import HelpFormatter
from discord.errors import Forbidden


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
    async def _default_help_command(self, ctx, *commands : str):
        """Shows this message."""
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
                    await bot.send_message(destination, bot.command_not_found.format(name))
                    return
    
            embed = self.formatter.format_help_for(ctx, command)
        else:
            name = self._mention_pattern.sub(repl, commands[0])
            command = bot.commands.get(name)
            if command is None:
                await bot.send_message(destination, bot.command_not_found.format(name))
                return
    
            for key in commands[1:]:
                try:
                    key = self._mention_pattern.sub(repl, key)
                    command = command.commands.get(key)
                    if command is None:
                        await bot.send_message(destination, bot.command_not_found.format(key))
                        return
                except AttributeError:
                    await bot.send_message(destination, bot.command_has_no_subcommands.format(command, key))
                    return
    
            embed = self.formatter.format_help_for(ctx, command)
        
        try:
            await bot.send_message(destination, embed=embed)
        except Forbidden:
            await bot.send_message(ctx.message.channel, 'Error: I cannot send messages to this user or channel.')
        else:
            if bot.pm_help:
                await bot.send_message(ctx.message.channel, 'I have sent help to your PMs.')
        
class CustomHelpFormatter(HelpFormatter):
    
    def _get_subcommands(self, commands):
        out = ''
        for name, command in commands:
            if name in command.aliases:
                # skip aliases
                continue

            entry = '**{0}** - {1}\n'.format(name, command.short_doc)
            shortened = self.shorten(entry)
            out += shortened
        return out

    def format(self):
        """Handles the actual behaviour involved with formatting.
        To change the behaviour, this method should be overridden.
        Returns
        --------
        embed
            An embed.
        """
        self.embed = discord.Embed()

        # we need a padding of ~80 or so

        description = self.command.description if not self.is_cog() else inspect.getdoc(self.command)

        if description:
            # <description> portion
            self.embed.description = description

        if isinstance(self.command, Command):
            # <signature portion>
            signature = self.get_command_signature()
            self.embed.title = signature

            # <long doc> section
            if self.command.help:
                self.embed.description = self.command.help

            # end it here if it's just a regular command
            if not self.has_subcommands():
                return self.embed

        max_width = self.max_name_size

        def category(tup):
            cog = tup[1].cog_name
            # we insert the zero width space there to give it approximate
            # last place sorting position.
            return cog if cog is not None else '\u200bNo Category'

        if self.is_bot():
            data = sorted(self.filter_command_list(), key=category)
            for category, commands in itertools.groupby(data, key=category):
                # there simply is no prettier way of doing this.
                commands = list(commands)
                if len(commands) > 0:
                    title = category
                    value = self._get_subcommands(commands)
                    self.embed.add_field(name=title, value=value, inline=False)

        else:
            title = 'Commands'
            value = self._get_subcommands(self.filter_command_list())
            self.embed.add_field(name=title, value=value, inline=False)

        ending_note = self.get_ending_note()
        self.embed.add_field(name='More Help', value=ending_note, inline=False)
        return self.embed