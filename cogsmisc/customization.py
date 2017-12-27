"""
Created on Jan 30, 2017

@author: andrew
"""
import asyncio
import shlex
import textwrap
import traceback
import uuid

from discord.ext import commands

from cogs5e.models.character import Character
from cogs5e.models.errors import NoCharacter, EvaluationError, AvraeException
from utils.functions import confirm


class Customization:
    """Commands to help streamline using the bot."""

    def __init__(self, bot):
        self.bot = bot
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        self.serv_aliases = self.bot.db.jget('serv_aliases', {})
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
                self.serv_aliases = self.bot.db.jget('serv_aliases', {})
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
            command = self.aliases.get(message.author.id, {}).get(alias) or \
                      self.serv_aliases.get(message.server.id, {}).get(alias)
            if command:
                message.content = self.handle_alias_arguments(command, message)
                # message.content = message.content.replace(alias, command, 1)
                try:
                    ctx = Context(self.bot, message)
                    message.content = Character.from_ctx(ctx).parse_cvars(message.content, ctx)
                except NoCharacter:
                    pass  # TODO: parse aliases anyway
                except EvaluationError as err:
                    e = err.original
                    if not isinstance(e, AvraeException):
                        tb = f"```py\n{''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))}\n```"
                        try:
                            await self.bot.send_message(message.author, tb)
                        except Exception as e:
                            pass
                    return await self.bot.send_message(message.channel, err)
                except Exception as e:
                    return await self.bot.send_message(message.channel, e)
                await self.bot.process_commands(message)

    def handle_alias_arguments(self, command, message):
        """Takes an alias name, alias value, and message and handles percent-encoded args.
        Returns: string"""
        args = " ".join(self.bot.prefix.join(message.content.split(self.bot.prefix)[1:]).split(' ')[1:])
        s = shlex.shlex(args, posix=True)
        s.whitespace = ' '  # doofy workaround
        s.whitespace_split = True
        s.commenters = ''
        args = list(s)
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

    @commands.group(pass_context=True, invoke_without_command=True)
    async def alias(self, ctx, alias_name, *, commands=None):
        """Adds an alias for a long command.
        After an alias has been added, you can instead run the aliased command with !<alias_name>.
        If a user and a server have aliases with the same name, the user alias will take priority."""
        user_id = ctx.message.author.id
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        user_aliases = self.aliases.get(user_id, {})
        if alias_name in self.bot.commands:
            return await self.bot.say('There is already a built-in command with that name!')

        if commands is None:
            alias = user_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = '!' + alias
            return await self.bot.say('**' + alias_name + '**:\n```md\n' + alias + "\n```")

        user_aliases[alias_name] = commands.lstrip('!')
        await self.bot.say('Alias `!{}` added for command:\n`!{}`'.format(alias_name, commands.lstrip('!')))

        self.aliases[user_id] = user_aliases
        self.bot.db.not_json_set('cmd_aliases', self.aliases)

    @alias.command(pass_context=True, name='list')
    async def alias_list(self, ctx):
        """Lists all user aliases."""
        user_id = ctx.message.author.id
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        user_aliases = self.aliases.get(user_id, {})
        aliases = [name for name in user_aliases.keys()]
        sorted_aliases = sorted(aliases)
        return await self.bot.say('Your aliases:\n{}'.format(', '.join(sorted_aliases)))

    @alias.command(pass_context=True, name='delete', aliases=['remove'])
    async def alias_delete(self, ctx, alias_name):
        """Deletes a user alias."""
        user_id = ctx.message.author.id
        self.aliases = self.bot.db.not_json_get('cmd_aliases', {})
        user_aliases = self.aliases.get(user_id, {})

        try:
            del user_aliases[alias_name]
        except KeyError:
            return await self.bot.say('Alias not found.')
        await self.bot.say('Alias {} removed.'.format(alias_name))

        self.aliases[user_id] = user_aliases
        self.bot.db.not_json_set('cmd_aliases', self.aliases)

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['serveralias'])
    async def servalias(self, ctx, alias_name, *, commands=None):
        """Adds an alias that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have aliases with the same name, the user alias will take priority."""
        server_id = ctx.message.server.id
        self.serv_aliases = self.bot.db.not_json_get('serv_aliases', {})
        server_aliases = self.serv_aliases.get(server_id, {})
        if alias_name in self.bot.commands:
            return await self.bot.say('There is already a built-in command with that name!')

        if commands is None:
            alias = server_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = '!' + alias
            return await self.bot.say('**' + alias_name + '**:\n```md\n' + alias + "\n```")

        if not self.can_edit_servaliases(ctx):
            return await self.bot.say("You do not have permission to edit server aliases. Either __Administrator__ "
                                      "Discord permissions or a role called \"Server Aliaser\" is required.")

        server_aliases[alias_name] = commands.lstrip('!')
        await self.bot.say('Server alias `!{}` added for command:\n`!{}`'.format(alias_name, commands.lstrip('!')))

        self.serv_aliases[server_id] = server_aliases
        self.bot.db.not_json_set('serv_aliases', self.serv_aliases)

    @servalias.command(pass_context=True, name='list')
    async def servalias_list(self, ctx):
        """Lists all server aliases."""
        server_id = ctx.message.server.id
        self.serv_aliases = self.bot.db.not_json_get('serv_aliases', {})
        server_aliases = self.serv_aliases.get(server_id, {})
        aliases = [name for name in server_aliases.keys()]
        sorted_aliases = sorted(aliases)
        return await self.bot.say('This server\'s aliases:\n{}'.format(', '.join(sorted_aliases)))

    @servalias.command(pass_context=True, name='delete', aliases=['remove'])
    async def servalias_delete(self, ctx, alias_name):
        """Deletes a server alias.
        Any user with permission to create a server alias can delete one from the server."""
        if not self.can_edit_servaliases(ctx):
            return await self.bot.say("You do not have permission to edit server aliases. Either __Administrator__ "
                                      "Discord permissions or a role called \"Server Aliaser\" is required.")
        server_id = ctx.message.server.id
        self.serv_aliases = self.bot.db.not_json_get('serv_aliases', {})
        server_aliases = self.serv_aliases.get(server_id, {})

        try:
            del server_aliases[alias_name]
        except KeyError:
            return await self.bot.say('Server alias not found.')
        await self.bot.say('Server alias {} removed.'.format(alias_name))

        self.serv_aliases[server_id] = server_aliases
        self.bot.db.not_json_set('serv_aliases', self.serv_aliases)

    def can_edit_servaliases(self, ctx):
        """
        Returns whether a user can edit server aliases in the current context.
        """
        return ctx.message.author.server_permissions.administrator or \
               'server aliaser' in (r.name.lower() for r in ctx.message.author.roles) or \
               ctx.message.author.id == ctx.bot.owner.id

    @commands.command(pass_context=True)
    async def test(self, ctx, *, str):
        """Parses `str` as if it were in an alias, for testing."""
        char = Character.from_ctx(ctx)
        await self.bot.say(f"{ctx.message.author.display_name}: {char.parse_cvars(str, ctx)}")

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['uvar'])
    async def uservar(self, ctx, name, *, value=None):
        """Commands to manage user variables for use in snippets and aliases.
        User variables can be called in the `-phrase` tag by surrounding the variable name with `{}` (calculates) or `<>` (prints).
        Arguments surrounded with `{{}}` will be evaluated as a custom script.
        See http://avrae.io/cheatsheets/aliasing for more help."""
        user_vars = self.bot.db.jhget("user_vars", ctx.message.author.id, {})

        if value is None:  # display value
            uvar = user_vars.get(name)
            if uvar is None: uvar = 'Not defined.'
            return await self.bot.say(f'**{name}**:\n`{uvar}`')

        try:
            assert not name in STAT_VAR_NAMES
            assert not any(c in name for c in '-/()[]\\.^$*+?|{}')
        except AssertionError:
            return await self.bot.say("Could not create uvar: already builtin, or contains invalid character!")

        user_vars[name] = value
        self.bot.db.jhset("user_vars", ctx.message.author.id, user_vars)
        await self.bot.say('User variable `{}` set to: `{}`'.format(name, value))

    @uservar.command(pass_context=True, name='remove', aliases=['delete'])
    async def uvar_remove(self, ctx, name):
        """Deletes a uvar from the user."""
        user_vars = self.bot.db.jhget("user_vars", ctx.message.author.id, {})

        try:
            del user_vars[name]
        except KeyError:
            return await self.bot.say('User variable not found.')

        self.bot.db.jhset("user_vars", ctx.message.author.id, user_vars)

        await self.bot.say('User variable {} removed.'.format(name))

    @uservar.command(pass_context=True, name='list')
    async def uvar_list(self, ctx):
        """Lists all uvars for the user."""
        user_vars = self.bot.db.jhget("user_vars", ctx.message.author.id, {})

        await self.bot.say('Your user variables:\n{}'.format(', '.join(sorted([name for name in user_vars.keys()]))))

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['gvar'])
    async def globalvar(self, ctx, name):
        """Commands to manage global, community variables for use in snippets and aliases.
        If run without a subcommand, shows the value of a global variable.
        Global variables are readable by all users, but only editable by the creator.
        Global variables must be accessed through scripting, with `get_gvar(gvar_id)`.
        See http://avrae.io/cheatsheets/aliasing for more help."""
        glob_vars = self.bot.db.jget("global_vars", {})

        gvar = glob_vars.get(name)
        if gvar is None: gvar = {'owner_name': 'None', 'value': 'Not defined.'}
        return await self.bot.say(f"**{name}**:\n*Owner: {gvar['owner_name']}* ```\n{gvar['value']}\n```")

    @globalvar.command(pass_context=True, name='create')
    async def gvar_create(self, ctx, *, value):
        """Creates a global variable.
        A name will be randomly assigned upon creation."""
        glob_vars = self.bot.db.jget("global_vars", {})
        name = str(uuid.uuid4())
        glob_vars[name] = {'owner': ctx.message.author.id, 'owner_name': str(ctx.message.author), 'value': value}
        self.bot.db.jset("global_vars", glob_vars)
        await self.bot.say(f"Created global variable `{name}`.")

    @globalvar.command(pass_context=True, name='edit')
    async def gvar_edit(self, ctx, name, *, value):
        """Edits a global variable."""
        glob_vars = self.bot.db.jget("global_vars", {})

        gvar = glob_vars.get(name)
        if gvar is None:
            return await self.bot.say("Global variable not found.")
        elif gvar['owner'] != ctx.message.author.id:
            return await self.bot.say("You are not the owner of this variable.")
        else:
            glob_vars[name]['value'] = value

        self.bot.db.jset("global_vars", glob_vars)
        await self.bot.say(f'Global variable `{name}` edited.')

    @globalvar.command(pass_context=True, name='remove', aliases=['delete'])
    async def gvar_remove(self, ctx, name):
        """Deletes a global variable."""
        glob_vars = self.bot.db.jget("global_vars", {})

        gvar = glob_vars.get(name)
        if gvar is None:
            return await self.bot.say("Global variable not found.")
        elif gvar['owner'] != ctx.message.author.id:
            return await self.bot.say("You are not the owner of this variable.")
        else:
            if await confirm(ctx, f"Are you sure you want to delete `{name}`?"):
                del glob_vars[name]
            else:
                return await self.bot.say("Ok, cancelling.")

        self.bot.db.jset("global_vars", glob_vars)

        await self.bot.say('Global variable {} removed.'.format(name))

    @globalvar.command(pass_context=True, name='list')
    async def gvar_list(self, ctx):
        """Lists all global variables for the user."""
        glob_vars = self.bot.db.jget("global_vars", {})
        user_vars = {k: v['value'] for k, v in glob_vars.items() if v['owner'] == ctx.message.author.id}

        await self.bot.say('Your global variables:\n{}'.format('\n'.join(
            f"`{k}`: {textwrap.shorten(v, 20)}" for k, v in
            sorted(((k, v) for k, v in user_vars.items()), key=lambda i: i[0]))))


STAT_VAR_NAMES = ("armor",
                  "charisma", "charismaMod", "charismaSave",
                  "constitution", "constitutionMod", "constitutionSave",
                  "description",
                  "dexterity", "dexterityMod", "dexteritySave",
                  "hp", "image",
                  "intelligence", "intelligenceMod", "intelligenceSave",
                  "level", "name", "proficiencyBonus",
                  "strength", "strengthMod", "strengthSave",
                  "wisdom", "wisdomMod", "wisdomSave")


class Context:
    """A singleton class to pretend to be ctx."""

    def __init__(self, bot, message):
        self.bot = bot
        self.message = message
