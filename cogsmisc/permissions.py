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
        
    async def on_ready(self):
        self.bot.global_prefixes = self.bot.db.not_json_get("prefixes", {})
    
    def __check(self, ctx):
        msg = ctx.message
        if checks.is_owner_check(ctx):
            return True

        try: 
            entry = self.bot.db.not_json_get("permissions", {})[msg.server.id]
        except (KeyError, AttributeError):
            return True
        else:
            name = ctx.command.qualified_name.split(' ')[0]
            return name not in entry

    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def prefix(self, ctx, prefix: str):
        """Sets the bot's prefix for this server.

        You must have Manage Server permissions or the
        Bot Admin role to use this command.
        
        Forgot the prefix? Reset it with "@Avrae#6944 prefix !".
        """
        guild_id = ctx.message.server.id
        self.bot.global_prefixes[guild_id] = prefix
        self.bot.db.not_json_set("prefixes", self.bot.global_prefixes)
        await self.bot.say("Prefix set to `{}` for this server.".format(prefix))
        
    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def disable(self, ctx, *, command: str):
        """Disables a command for this server. Case-sensitive.

        You must have Manage Server permissions or the
        Bot Admin role to use this command.
        """

        if command in ('enable', 'disable'):
            return await self.bot.say('Cannot disable that command.')

        if command not in self.bot.commands:
            return await self.bot.say('I do not have this command registered.')

        guild_id = ctx.message.server.id
        global_entries = self.bot.db.not_json_get("permissions", {})
        guild_entries = global_entries.get(guild_id, {})
        guild_entries[command] = True
        global_entries[guild_id] = guild_entries
        self.bot.db.not_json_set("permissions", global_entries)
        await self.bot.say('"%s" command disabled in this server.' % command)

    @commands.command(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def enable(self, ctx, *, command: str):
        """Enables a command for this server.

        You must have Manage Server permissions or the
        Bot Admin role to use this command.
        """
        guild_id = ctx.message.server.id
        global_entries = self.bot.db.not_json_get("permissions", {})
        guild_entries = global_entries.get(guild_id, {})

        try:
            guild_entries.pop(command)
            global_entries[guild_id] = guild_entries
        except KeyError:
            await self.bot.say('The command does not exist or is not disabled.')
        else:
            self.bot.db.not_json_set("permissions", global_entries)
            await self.bot.say('"%s" command enabled in this server.' % command)
