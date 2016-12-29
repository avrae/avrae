'''
Created on Dec 29, 2016

@author: andrew
'''

from discord.ext import commands

from utils import checks


class Permissions:
    """Handles the bot's permission system.

    This is how you disable or enable certain commands
    for your server.
    """

    def __init__(self, bot):
        self.bot = bot
    
    @commands.check
    def __check(self, ctx):
        msg = ctx.message
        if checks.is_owner_check(msg):
            return True

        entry = self.bot.db.get_whole_dict(msg.server.id + "_perms", {})
        name = ctx.command.qualified_name.split(' ')[0]
        return name not in entry

    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def disable(self, ctx, *, command: str):
        """Disables a command for this server.

        You must have Manage Server permissions or the
        Bot Admin role to use this command.
        """
        command = command.lower()

        if command in ('enable', 'disable'):
            return await self.bot.say('Cannot disable that command.')

        if command not in self.bot.commands:
            return await self.bot.say('I do not have this command registered.')

        guild_id = ctx.message.server.id
        entries = self.bot.db.get_whole_dict(guild_id + "_perms", {})
        entries[command] = True
        self.bot.db.set_dict(guild_id + "_perms", entries)
        await self.bot.say('"%s" command disabled in this server.' % command)

    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def enable(self, ctx, *, command: str):
        """Enables a command for this server.

        You must have Manage Server permissions or the
        Bot Admin role to use this command.
        """
        command = command.lower()
        guild_id = ctx.message.server.id
        entries = self.bot.db.get_whole_dict(guild_id + "_perms", {})

        try:
            entries.pop(command)
        except KeyError:
            await self.bot.say('The command does not exist or is not disabled.')
        else:
            self.bot.db.set_dict(guild_id + "_perms", entries)
            await self.bot.say('"%s" command enabled in this server.' % command)
