"""
Created on Jan 30, 2017

@author: andrew
"""
import asyncio
import textwrap
import traceback
import uuid

import discord
from discord.ext import commands
from discord.ext.commands import BucketType, UserInputError

from cogs5e.funcs import scripting
from cogs5e.funcs.scripting import ScriptingEvaluator
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import AvraeException, EvaluationError, NoCharacter
from utils.argparser import argquote, argsplit
from utils.functions import auth_and_chan, clean_content, confirm

ALIASER_ROLES = ("server aliaser", "dragonspeaker")


class Customization(commands.Cog):
    """Commands to help streamline using the bot."""

    def __init__(self, bot):
        self.bot = bot

    async def on_ready(self):
        if getattr(self.bot, "shard_id", 0) == 0:
            cmds = list(self.bot.all_commands.keys())
            self.bot.rdb.jset('default_commands', cmds)

    async def on_message(self, message):
        if str(message.author.id) in self.bot.muted:
            return
        await self.handle_aliases(message)

    @commands.command()
    @commands.cooldown(1, 20, BucketType.user)
    async def multiline(self, ctx, *, cmds: str):
        """Runs each line as a separate command, with a 1 second delay between commands.
        Limited to 1 multiline every 20 seconds, with a max of 20 commands, due to abuse.
        Usage:
        "!multiline
        !roll 1d20
        !spell Fly
        !monster Rat"
        """
        cmds = cmds.splitlines()
        for c in cmds[:20]:
            ctx.message.content = c
            await self.bot.process_commands(ctx.message)
            await asyncio.sleep(1)

    async def handle_aliases(self, message):
        prefix = self.bot.get_server_prefix(message)
        if message.content.startswith(prefix):
            alias = prefix.join(message.content.split(prefix)[1:]).split(' ')[0]
            if message.guild:
                command = (await self.bot.mdb.aliases.find_one({"owner": str(message.author.id), "name": alias},
                                                               ['commands'])) or \
                          (await self.bot.mdb.servaliases.find_one({"server": str(message.guild.id), "name": alias},
                                                                   ['commands']))
            else:
                command = await self.bot.mdb.aliases.find_one({"owner": str(message.author.id), "name": alias},
                                                              ['commands'])
            if command:
                command = command['commands']
                try:
                    message.content = self.handle_alias_arguments(command, message)
                except UserInputError as e:
                    return await message.channel.send(f"Invalid input: {e}")
                ctx = Context(self.bot, message)
                char = None
                try:
                    char = await Character.from_ctx(ctx)
                except NoCharacter:
                    pass

                try:
                    if char:
                        message.content = await char.parse_cvars(message.content, ctx)
                    else:
                        message.content = await self.parse_no_char(message.content, ctx)
                except EvaluationError as err:
                    e = err.original
                    if not isinstance(e, AvraeException):
                        tb = ''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))
                        try:
                            await message.author.send(f"```py\nError when parsing expression {err.expression}:\n"
                                                      f"{tb}\n```")
                        except Exception:
                            pass
                    return await message.channel.send(err)
                except Exception as e:
                    return await message.channel.send(e)
                await self.bot.process_commands(message)

    def handle_alias_arguments(self, command, message):
        """Takes an alias name, alias value, and message and handles percent-encoded args.
        Returns: string"""
        prefix = self.bot.get_server_prefix(message)
        rawargs = " ".join(prefix.join(message.content.split(prefix)[1:]).split(' ')[1:])
        args = argsplit(rawargs)
        tempargs = args[:]
        new_command = command
        if '%*%' in command:
            new_command = new_command.replace('%*%', argquote(rawargs) if ' ' in rawargs else rawargs)
            tempargs = []
        if '&*&' in command:
            new_command = new_command.replace('&*&', rawargs.replace("\"", "\\\"").replace("'", "\\'"))
            tempargs = []
        if '&ARGS&' in command:
            new_command = new_command.replace('&ARGS&', str(tempargs))
            tempargs = []
        for index, value in enumerate(args):
            key = '%{}%'.format(index + 1)
            to_remove = False
            if key in command:
                new_command = new_command.replace(key, argquote(value) if ' ' in value else value)
                to_remove = True
            key = '&{}&'.format(index + 1)
            if key in command:
                new_command = new_command.replace(key, value.replace("\"", "\\\"").replace("'", "\\'"))
                to_remove = True
            if to_remove:
                try:
                    tempargs.remove(value)
                except ValueError:
                    pass

        quoted_args = ' '.join(map(argquote, tempargs))
        return f"{prefix}{new_command} {quoted_args}".strip()

    async def parse_no_char(self, cstr, ctx):
        """
        Parses cvars and whatnot without an active character.
        :param cstr: The string to parse.
        :param ctx: The Context to parse the string in.
        :return: The parsed string.
        :rtype: str
        """
        evaluator = await ScriptingEvaluator.new(ctx)
        out = await asyncio.get_event_loop().run_in_executor(None, evaluator.parse, cstr)
        await evaluator.run_commits()
        return out

    @commands.group(invoke_without_command=True)
    async def alias(self, ctx, alias_name=None, *, cmds=None):
        """Adds an alias for a long command.
        After an alias has been added, you can instead run the aliased command with !<alias_name>.
        If a user and a server have aliases with the same name, the user alias will take priority."""
        if alias_name is None:
            return await ctx.invoke(self.bot.get_command("alias list"))
        if alias_name in self.bot.all_commands:
            return await ctx.send('There is already a built-in command with that name!')

        if ' ' in alias_name or not alias_name:
            return await ctx.send('Invalid alias name.')

        user_aliases = await scripting.get_aliases(ctx)
        if cmds is None:
            alias = user_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = f'{ctx.prefix}alias {alias_name} {alias}'
            return await ctx.send(f'**{alias_name}**:\n(Copy-pastable)\n```md\n{alias}\n```')

        await self.bot.mdb.aliases.update_one({"owner": str(ctx.author.id), "name": alias_name},
                                              {"$set": {"commands": cmds.lstrip('!')}}, True)
        await ctx.send(f'Alias `{ctx.prefix}{alias_name}` added for command:\n`{ctx.prefix}{cmds.lstrip("!")}`')

    @alias.command(name='list')
    async def alias_list(self, ctx):
        """Lists all user aliases."""
        user_aliases = await scripting.get_aliases(ctx)
        aliases = list(user_aliases.keys())
        sorted_aliases = sorted(aliases)
        return await ctx.send('Your aliases:\n{}'.format(', '.join(sorted_aliases)))

    @alias.command(name='delete', aliases=['remove'])
    async def alias_delete(self, ctx, alias_name):
        """Deletes a user alias."""
        result = await self.bot.mdb.aliases.delete_one({"owner": str(ctx.author.id), "name": alias_name})
        if not result.deleted_count:
            return await ctx.send('Alias not found.')
        await ctx.send('Alias {} removed.'.format(alias_name))

    @alias.command(name='deleteall', aliases=['removeall'])
    async def alias_deleteall(self, ctx):
        """Deletes ALL user aliases."""
        await ctx.send("This will delete **ALL** of your user aliases. "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
        if not reply.content == "Yes, I am sure":
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.aliases.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your aliases.")

    @commands.group(invoke_without_command=True, aliases=['serveralias'])
    @commands.guild_only()
    async def servalias(self, ctx, alias_name=None, *, cmds=None):
        """Adds an alias that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have aliases with the same name, the user alias will take priority."""
        if alias_name is None:
            return await ctx.invoke(self.bot.get_command("servalias list"))

        server_aliases = await scripting.get_servaliases(ctx)
        if alias_name in self.bot.all_commands:
            return await ctx.send('There is already a built-in command with that name!')

        if cmds is None:
            alias = server_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = f'{ctx.prefix}servalias {alias_name} {alias}'
            return await ctx.send(f'**{alias_name}**:\n(Copy-pastable)```md\n{alias}\n```')

        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server aliases. Either __Administrator__ "
                                  "Discord permissions or a role named \"Server Aliaser\" or \"Dragonspeaker\" "
                                  "is required.")

        await self.bot.mdb.servaliases.update_one({"server": str(ctx.guild.id), "name": alias_name},
                                                  {"$set": {"commands": cmds.lstrip('!')}}, True)
        await ctx.send(f'Server alias `{ctx.prefix}{alias_name}` added for command:\n`{ctx.prefix}{cmds.lstrip("!")}`')

    @servalias.command(name='list')
    @commands.guild_only()
    async def servalias_list(self, ctx):
        """Lists all server aliases."""
        server_aliases = await scripting.get_servaliases(ctx)
        aliases = list(server_aliases.keys())
        sorted_aliases = sorted(aliases)
        return await ctx.send('This server\'s aliases:\n{}'.format(', '.join(sorted_aliases)))

    @servalias.command(name='delete', aliases=['remove'])
    @commands.guild_only()
    async def servalias_delete(self, ctx, alias_name):
        """Deletes a server alias.
        Any user with permission to create a server alias can delete one from the server."""
        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server aliases. Either __Administrator__ "
                                  "Discord permissions or a role called \"Server Aliaser\" is required.")
        result = await self.bot.mdb.servaliases.delete_one({"server": str(ctx.guild.id), "name": alias_name})
        if not result.deleted_count:
            return await ctx.send('Server alias not found.')
        await ctx.send('Server alias {} removed.'.format(alias_name))

    @staticmethod
    def can_edit_servaliases(ctx):
        """
        Returns whether a user can edit server aliases in the current context.
        """
        return ctx.author.guild_permissions.administrator or \
               any(r.name.lower() in ALIASER_ROLES for r in ctx.author.roles) or \
               ctx.author.id == ctx.bot.owner.id

    @commands.group(invoke_without_command=True)
    async def snippet(self, ctx, snipname=None, *, snippet=None):
        """Creates a snippet to use in attack macros.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*."""
        if snipname is None:
            return await ctx.invoke(self.bot.get_command("snippet list"))
        user_snippets = await scripting.get_snippets(ctx)

        if snippet is None:
            return await ctx.send(f'**{snipname}**:\n'
                                  f'(Copy-pastable)```md\n'
                                  f'{ctx.prefix}snippet {snipname} {user_snippets.get(snipname, "Not defined.")}'
                                  f'\n```')

        if len(snipname) < 2: return await ctx.send("Snippets must be at least 2 characters long!")
        await self.bot.mdb.snippets.update_one({"owner": str(ctx.author.id), "name": snipname},
                                               {"$set": {"snippet": snippet}}, True)
        await ctx.send('Shortcut {} added for arguments:\n`{}`'.format(snipname, snippet))

    @snippet.command(name='list')
    async def snippet_list(self, ctx):
        """Lists your user snippets."""
        user_snippets = await scripting.get_snippets(ctx)
        await ctx.send('Your snippets:\n{}'.format(', '.join(sorted([name for name in user_snippets.keys()]))))

    @snippet.command(name='delete', aliases=['remove'])
    async def snippet_delete(self, ctx, snippet_name):
        """Deletes a snippet."""
        result = await self.bot.mdb.snippets.delete_one({"owner": str(ctx.author.id), "name": snippet_name})
        if not result.deleted_count:
            return await ctx.send('Snippet not found.')
        await ctx.send('Shortcut {} removed.'.format(snippet_name))

    @snippet.command(name='deleteall', aliases=['removeall'])
    async def snippet_deleteall(self, ctx):
        """Deletes ALL user snippets."""
        await ctx.send("This will delete **ALL** of your user snippets. "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=lambda m: auth_and_chan(ctx)(m))
        if not reply.content == "Yes, I am sure":
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.snippets.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your snippets.")

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def servsnippet(self, ctx, snipname=None, *, snippet=None):
        """Creates a snippet to use in attack macros for the entire server.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have snippets with the same name, the user snippet will take priority.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*."""
        if snipname is None:
            return await ctx.invoke(self.bot.get_command("servsnippet list"))
        server_id = str(ctx.guild.id)
        server_snippets = await scripting.get_servsnippets(ctx)

        if snippet is None:
            return await ctx.send(f'**{snipname}**:\n'
                                  f'(Copy-pastable)```md\n'
                                  f'{ctx.prefix}snippet {snipname} {server_snippets.get(snipname, "Not defined.")}\n'
                                  f'```')

        if self.can_edit_servaliases(ctx):
            if len(snipname) < 2: return await ctx.send("Snippets must be at least 2 characters long!")
            await self.bot.mdb.servsnippets.update_one({"server": server_id, "name": snipname},
                                                       {"$set": {"snippet": snippet}}, True)
            await ctx.send('Server snippet {} added for arguments:\n`{}`'.format(snipname, snippet))
        else:
            return await ctx.send("You do not have permission to edit server snippets. Either __Administrator__ "
                                  "Discord permissions or a role named \"Server Aliaser\" or \"Dragonspeaker\" "
                                  "is required.")

    @servsnippet.command(name='list')
    @commands.guild_only()
    async def servsnippet_list(self, ctx):
        """Lists this server's snippets."""
        server_snippets = await scripting.get_servsnippets(ctx)
        await ctx.send(
            'This server\'s snippets:\n{}'.format(', '.join(sorted([name for name in server_snippets.keys()]))))

    @servsnippet.command(name='delete', aliases=['remove'])
    @commands.guild_only()
    async def servsnippet_delete(self, ctx, snippet_name):
        """Deletes a server snippet.
        Any user that can create a server snippet can delete one."""
        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server snippets. Either __Administrator__ "
                                  "Discord permissions or a role called \"Server Aliaser\" is required.")
        result = await self.bot.mdb.servsnippets.delete_one({"server": str(ctx.guild.id), "name": snippet_name})
        if not result.deleted_count:
            return await ctx.send('Snippet not found.')
        await ctx.send('Server snippet {} removed.'.format(snippet_name))

    @commands.command()
    async def test(self, ctx, *, teststr):
        """Parses `str` as if it were in an alias, for testing."""
        char = await Character.from_ctx(ctx)
        parsed = await char.parse_cvars(teststr, ctx)
        parsed = clean_content(parsed, ctx)
        await ctx.send(f"{ctx.author.display_name}: {parsed}")

    @commands.group(invoke_without_command=True, aliases=['uvar'])
    async def uservar(self, ctx, name=None, *, value=None):
        """Commands to manage user variables for use in snippets and aliases.
        User variables can be called in the `-phrase` tag by surrounding the variable name with `{}` (calculates) or `<>` (prints).
        Arguments surrounded with `{{}}` will be evaluated as a custom script.
        See http://avrae.io/cheatsheets/aliasing for more help."""
        if name is None:
            return await ctx.invoke(self.bot.get_command("uservar list"))

        user_vars = await scripting.get_uvars(ctx)

        if value is None:  # display value
            uvar = user_vars.get(name)
            if uvar is None: uvar = 'Not defined.'
            return await ctx.send(f'**{name}**:\n`{uvar}`')

        if name in STAT_VAR_NAMES or any(c in name for c in '-/()[]\\.^$*+?|{}'):
            return await ctx.send("Could not create uvar: already builtin, or contains invalid character!")

        await scripting.set_uvar(ctx, name, value)
        await ctx.send('User variable `{}` set to: `{}`'.format(name, value))

    @uservar.command(name='remove', aliases=['delete'])
    async def uvar_remove(self, ctx, name):
        """Deletes a uvar from the user."""
        result = await self.bot.mdb.uvars.delete_one({"owner": str(ctx.author.id), "name": name})
        if not result.deleted_count:
            return await ctx.send("Uvar does not exist.")
        await ctx.send('User variable {} removed.'.format(name))

    @uservar.command(name='list')
    async def uvar_list(self, ctx):
        """Lists all uvars for the user."""
        user_vars = await scripting.get_uvars(ctx)
        await ctx.send('Your user variables:\n{}'.format(', '.join(sorted([name for name in user_vars.keys()]))))

    @uservar.command(name='deleteall', aliases=['removeall'])
    async def uvar_deleteall(self, ctx):
        """Deletes ALL user variables."""
        await ctx.send("This will delete **ALL** of your user variables (uvars). "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=lambda m: auth_and_chan(ctx)(m))
        if (not reply) or (not reply.content == "Yes, I am sure"):
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.uvars.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your uvars.")

    @commands.group(invoke_without_command=True, aliases=['gvar'])
    async def globalvar(self, ctx, name=None):
        """Commands to manage global, community variables for use in snippets and aliases.
        If run without a subcommand, shows the value of a global variable.
        Global variables are readable by all users, but only editable by the creator.
        Global variables must be accessed through scripting, with `get_gvar(gvar_id)`.
        See http://avrae.io/cheatsheets/aliasing for more help."""
        if name is None:
            return await ctx.invoke(self.bot.get_command("globalvar list"))

        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None: gvar = {'owner_name': 'None', 'value': 'Not defined.'}
        return await ctx.send(f"**{name}**:\n*Owner: {gvar['owner_name']}* ```\n{gvar['value']}\n```")

    @globalvar.command(name='create')
    async def gvar_create(self, ctx, *, value):
        """Creates a global variable.
        A name will be randomly assigned upon creation."""
        name = str(uuid.uuid4())
        data = {'key': name, 'owner': str(ctx.author.id), 'owner_name': str(ctx.author), 'value': value,
                'editors': []}
        await self.bot.mdb.gvars.insert_one(data)
        await ctx.send(f"Created global variable `{name}`.")

    @globalvar.command(name='edit')
    async def gvar_edit(self, ctx, name, *, value):
        """Edits a global variable."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")
        elif gvar['owner'] != str(ctx.author.id) and not str(ctx.author.id) in gvar.get('editors', []):
            return await ctx.send("You are not allowed to edit this variable.")
        else:
            await self.bot.mdb.gvars.update_one({"key": name}, {"$set": {"value": value}})
        await ctx.send(f'Global variable `{name}` edited.')

    @globalvar.command(name='editor')
    async def gvar_editor(self, ctx, name, user: discord.Member = None):
        """Toggles the editor status of a user."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")

        if user is not None:
            if gvar['owner'] != str(ctx.author.id):
                return await ctx.send("You are not the owner of this variable.")
            else:
                e = gvar.get('editors', [])
                if str(user.id) in e:
                    e.remove(str(user.id))
                    msg = f"Removed {user} from the editor list."
                else:
                    e.append(str(user.id))
                    msg = f"Added {user} to the editor list."
                await self.bot.mdb.gvars.update_one({"key": name}, {"$set": {"editors": e}})
            await ctx.send(f'Global variable `{name}` edited: {msg}')
        else:
            embed = EmbedWithAuthor(ctx)
            embed.title = "Editors"
            editor_mentions = []
            for editor in gvar.get('editors', []):
                editor_mentions.append(f"<@{editor}>")
            embed.description = ', '.join(editor_mentions) or "No editors."
            await ctx.send(embed=embed)

    @globalvar.command(name='remove', aliases=['delete'])
    async def gvar_remove(self, ctx, name):
        """Deletes a global variable."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")
        elif gvar['owner'] != str(ctx.author.id):
            return await ctx.send("You are not the owner of this variable.")
        else:
            if await confirm(ctx, f"Are you sure you want to delete `{name}`?"):
                await self.bot.mdb.gvars.delete_one({"key": name})
            else:
                return await ctx.send("Ok, cancelling.")

        await ctx.send('Global variable {} removed.'.format(name))

    @globalvar.command(name='list')
    async def gvar_list(self, ctx):
        """Lists all global variables for the user."""
        user_vars = []
        async for gvar in self.bot.mdb.gvars.find({"owner": str(ctx.author.id)}):
            user_vars.append((gvar['key'], gvar['value']))
        gvar_list = [f"`{k}`: {textwrap.shorten(v, 20)}" for k, v in sorted(user_vars, key=lambda i: i[0])]
        say_list = ['']
        for g in gvar_list:
            if len(g) + len(say_list[-1]) < 1900:
                say_list[-1] += f'\n{g}'
            else:
                say_list.append(g)
        await ctx.send('Your global variables:{}'.format(say_list[0]))
        for m in say_list[1:]:
            await ctx.send(m)


def setup(bot):
    bot.add_cog(Customization(bot))


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
    """A class to pretend to be ctx."""

    def __init__(self, bot, message):
        self.bot = bot
        self.message = message

    @property
    def author(self):
        return self.message.author

    @property
    def guild(self):
        return self.message.guild

    @property
    def channel(self):
        return self.message.channel
