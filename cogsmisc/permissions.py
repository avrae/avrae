"""
Created on Dec 29, 2016

@author: andrew
"""

from discord.ext import commands

from utils import checks


class Permissions(commands.Cog):
    """Handles the bot's permission system.

    This is how you disable or enable certain commands
    for your server.
    """

    def __init__(self, bot):
        self.bot = bot
        self.disabled_commands = self.bot.rdb.not_json_get("permissions", {})

    def __global_check(self, ctx):
        msg = ctx.message
        if checks.is_owner(ctx):
            return True

        try:
            entry = self.disabled_commands[str(msg.guild.id)]
        except (KeyError, AttributeError):
            return True
        else:
            name = ctx.command.qualified_name.split(' ')[0]
            return name not in entry

    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def prefix(self, ctx, prefix: str = None):
        """Sets the bot's prefix for this server.

        You must have Manage Server permissions or a role called "Bot Admin" to use this command.
        
        Forgot the prefix? Reset it with "@Avrae#6944 prefix !".
        """
        guild_id = str(ctx.guild.id)
        if prefix is None:
            current_prefix = await self.bot.get_server_prefix(ctx.message)
            return await ctx.send(f"My current prefix is: `{current_prefix}`")
        # insert into cache
        self.bot.prefixes[guild_id] = prefix

        # update db
        await self.bot.mdb.prefixes.update_one(
            {"guild_id": guild_id},
            {"$set": {"prefix": prefix}},
            upsert=True
        )

        await ctx.send("Prefix set to `{}` for this server.".format(prefix))

    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def disable(self, ctx, *, command: str):
        """Disables a command for this server. Case-sensitive.

        You must have Manage Server permissions or a role called "Bot Admin" to use this command.
        """

        if command in ('enable', 'disable'):
            return await ctx.send('Cannot disable that command.')

        if command not in self.bot.all_commands:
            return await ctx.send('I do not have this command registered.')

        guild_id = str(ctx.guild.id)
        guild_entries = self.disabled_commands.get(guild_id, {})
        guild_entries[command] = True
        self.disabled_commands[guild_id] = guild_entries
        self.bot.rdb.not_json_set("permissions", self.disabled_commands)
        await ctx.send('"%s" command disabled in this server.' % command)

    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def enable(self, ctx, *, command: str):
        """Enables a command for this server.

        You must have Manage Server permissions or a role called "Bot Admin" to use this command.
        """
        guild_id = str(ctx.guild.id)
        guild_entries = self.disabled_commands.get(guild_id, {})

        try:
            guild_entries.pop(command)
            self.disabled_commands[guild_id] = guild_entries
        except KeyError:
            await ctx.send('The command does not exist or is not disabled.')
        else:
            self.bot.rdb.not_json_set("permissions", self.disabled_commands)
            await ctx.send('"%s" command enabled in this server.' % command)


def setup(bot):
    bot.add_cog(Permissions(bot))
