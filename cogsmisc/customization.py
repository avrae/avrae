"""
Created on Jan 30, 2017

@author: andrew
"""
import asyncio
import shlex

from discord.ext import commands

from cogs5e.models.character import Character


class Customization:
    """Commands to help streamline using the bot."""

    def __init__(self, bot):
        self.bot = bot
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        self.bot.loop.create_task(self.update_aliases())
        self.bot.loop.create_task(self.backup_aliases())

    async def on_ready(self):
        if getattr(self.bot, "shard_id", 0) == 0:
            commands = list(self.bot.commands.keys())
            self.bot.db.jset('default_commands', commands)

    async def update_aliases(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(10)
                self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        except asyncio.CancelledError:
            pass

    async def backup_aliases(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(1800)
                self.bot.db.jset('cmd_aliases_backup', self.bot.db.not_json_get('cmd_aliases', {}))
        except asyncio.CancelledError:
            pass

    async def on_message(self, message):
        await self.handle_aliases(message)

    @commands.command(pass_context=True)
    async def multiline(self, ctx, *, commands: str):
        """Runs each line as a separate command, with a 1 second delay between commands.
        Usage:
        "!multiline
        !roll 1d20
        !spell Fly
        !monster Rat"
        """
        commands = commands.splitlines()
        for c in commands:
            ctx.message.content = c
            if not hasattr(self.bot, 'global_prefixes'):  # bot's still starting up!
                return
            try:
                guild_prefix = self.bot.global_prefixes.get(ctx.message.server.id, self.bot.prefix)
            except:
                guild_prefix = self.bot.prefix
            if ctx.message.content.startswith(guild_prefix):
                ctx.message.content = ctx.message.content.replace(guild_prefix, self.bot.prefix, 1)
            elif ctx.message.content.startswith(self.bot.prefix):
                return
            await self.bot.process_commands(ctx.message)
            await asyncio.sleep(1)

    async def handle_aliases(self, message):
        if message.content.startswith(self.bot.prefix):
            alias = self.bot.prefix.join(message.content.split(self.bot.prefix)[1:]).split(' ')[0]
            command = self.aliases.get(message.author.id, {}).get(alias)
            if command:
                message.content = self.handle_alias_arguments(command, message)
                # message.content = message.content.replace(alias, command, 1)
                user_characters = self.bot.db.not_json_get(message.author.id + '.characters',
                                                           {})  # grab user's characters
                if len(user_characters) > 0:
                    active_character = self.bot.db.not_json_get('active_characters', {}).get(
                        message.author.id)  # get user's active
                    if active_character is not None:
                        try:
                            message.content = Character.from_bot_and_ids(self.bot, message.author.id,
                                                                         active_character).parse_cvars(message.content,
                                                                                                       Context(self.bot,
                                                                                                               message))
                        except Exception as e:
                            return await self.bot.send_message(message.channel, e)
                await self.bot.process_commands(message)

    def handle_alias_arguments(self, command, message):
        """Takes an alias name, alias value, and message and handles percent-encoded args.
        Returns: string"""
        args = " ".join(self.bot.prefix.join(message.content.split(self.bot.prefix)[1:]).split(' ')[1:])
        args = shlex.split(args)
        for index, arg in enumerate(args):
            if " " in arg:
                args[index] = shlex.quote(arg)
        tempargs = args[:]
        new_command = command
        for index, value in enumerate(args):
            key = '%{}%'.format(index + 1)
            if key in command:
                new_command = new_command.replace(key, value)
                tempargs.remove(value)

        return self.bot.prefix + new_command + " " + ' '.join(tempargs)

    @commands.command(pass_context=True)
    async def alias(self, ctx, alias_name, *, commands=None):
        """Adds an alias for a long command.
        After an alias has been added, you can instead run the aliased command with !<alias_name>.
        Valid Commands: *!alias list* - lists your aliases.
        *!alias [alias name]* - reveals what the alias runs.
        *!alias remove [alias name]* - removes an alias."""
        user_id = ctx.message.author.id
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        user_aliases = self.aliases.get(user_id, {})
        if alias_name in self.bot.commands:
            return await self.bot.say('There is already a built-in command with that name!')

        if alias_name == 'list':
            aliases = [name for name in user_aliases.keys()]
            sorted_aliases = sorted(aliases)
            return await self.bot.say('Your aliases:\n{}'.format(', '.join(sorted_aliases)))

        if commands is None:
            alias = user_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = '!' + alias
            return await self.bot.say('**' + alias_name + '**:\n```md\n' + alias + "\n```")

        if alias_name == 'remove' or alias_name == 'delete':
            try:
                del user_aliases[commands]
            except KeyError:
                return await self.bot.say('Alias not found.')
            await self.bot.say('Alias {} removed.'.format(commands))
        else:
            user_aliases[alias_name] = commands
            await self.bot.say('Alias `!{}` added for command:\n`!{}`'.format(alias_name, commands))

        self.aliases[user_id] = user_aliases
        self.bot.db.not_json_set('cmd_aliases', self.aliases)

    @commands.command(pass_context=True)
    async def test(self, ctx, *, str):
        """Parses `str` as if it were in an alias, for testing."""
        char = Character.from_ctx(ctx)
        await self.bot.say(f"{ctx.message.author.display_name}: {char.parse_cvars(str, ctx)}")

class Context:
    """A singleton class to pretend to be ctx."""
    def __init__(self, bot, message):
        self.bot = bot
        self.message = message