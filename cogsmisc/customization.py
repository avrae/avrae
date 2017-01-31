'''
Created on Jan 30, 2017

@author: andrew
'''
from discord.ext import commands

class Customization:
    """Commands to help streamline using the bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        
    async def on_message(self, message):
        await self.handle_aliases(message)
        
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
            
    async def handle_aliases(self, message):
        if message.content.startswith(self.bot.prefix):
            for alias, command in self.aliases.get(message.author.id, {}).items():
                if '!'.join(message.content.split(self.bot.prefix)[1:]).split(' ')[0] == alias:
                    message.content = message.content.replace(alias, command, 1)
                    await self.bot.process_commands(message)
                    break
        
    @commands.command(pass_context=True)
    async def alias(self, ctx, alias_name, *, commands):
        """Adds an alias for a long command.
        After an alias has been added, you can instead run the aliased command with !<alias_name>."""
        user_id = ctx.message.author.id
        user_aliases = self.aliases.get(user_id, {})
        if alias_name in self.bot.commands:
            return await self.bot.say('There is already a built-in command with that name!')
        
        user_aliases[alias_name] = commands
        
        self.aliases[user_id] = user_aliases
        self.bot.db.not_json_set('cmd_aliases', self.aliases)
        await self.bot.say('Alias {} added for command:\n`{}`'.format(alias_name, commands))
        
        
        