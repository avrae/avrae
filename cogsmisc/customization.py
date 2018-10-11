"""
Created on Jan 30, 2017

@author: andrew
"""
import asyncio
import copy
import re
import shlex
import textwrap
import traceback
import uuid

import discord
from discord.ext import commands
from discord.ext.commands import UserInputError, BucketType
from discord.ext.commands.view import quoted_word, StringView

from cogs5e.funcs import scripting
from cogs5e.funcs.dice import roll
from cogs5e.funcs.scripting import ScriptingEvaluator, SCRIPTING_RE
from cogs5e.models.character import Character
from cogs5e.models.errors import NoCharacter, EvaluationError, FunctionRequiresCharacter, \
    AvraeException
from utils.functions import confirm, clean_content


class Customization:
    """Commands to help streamline using the bot."""

    def __init__(self, bot):
        self.bot = bot
        self.serv_aliases = {}
        self.nochar_eval = NoCharacterEvaluator()

    async def on_ready(self):
        if getattr(self.bot, "shard_id", 0) == 0:
            cmds = list(self.bot.commands.keys())
            self.bot.rdb.jset('default_commands', cmds)

    async def on_message(self, message):
        if message.author.id in self.bot.get_cog("AdminUtils").muted:
            return
        await self.handle_aliases(message)

    @commands.command(pass_context=True)
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

        try:
            guild_prefix = self.bot.global_prefixes.get(ctx.message.server.id, self.bot.prefix)
        except:
            guild_prefix = self.bot.prefix
        cmds = cmds.split(guild_prefix)

        for c in cmds[:20]:
            ctx.message.content = guild_prefix + c
            if not hasattr(self.bot, 'global_prefixes'):  # bot's still starting up!
                return
            if ctx.message.content.startswith(guild_prefix):
                ctx.message.content = ctx.message.content.replace(guild_prefix, self.bot.prefix, 1)
            await self.bot.process_commands(ctx.message)
            await asyncio.sleep(1)

    async def handle_aliases(self, message):
        if message.content.startswith(self.bot.prefix):
            alias = self.bot.prefix.join(message.content.split(self.bot.prefix)[1:]).split(' ')[0]
            if not message.channel.is_private:
                command = (await self.bot.mdb.aliases.find_one({"owner": message.author.id, "name": alias},
                                                               ['commands'])) or \
                          (await self.bot.mdb.servaliases.find_one({"server": message.server.id, "name": alias},
                                                                   ['commands']))
            else:
                command = await self.bot.mdb.aliases.find_one({"owner": message.author.id, "name": alias}, ['commands'])
            if command:
                command = command['commands']
                try:
                    message.content = self.handle_alias_arguments(command, message)
                except UserInputError as e:
                    return await self.bot.send_message(message.channel, f"Invalid input: {e}")
                # message.content = message.content.replace(alias, command, 1)
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
                        tb = f"```py\n{''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))}\n```"
                        try:
                            await self.bot.send_message(message.author, tb)
                        except Exception:
                            pass
                    return await self.bot.send_message(message.channel, err)
                except Exception as e:
                    return await self.bot.send_message(message.channel, e)
                await self.bot.process_commands(message)

    def handle_alias_arguments(self, command, message):
        """Takes an alias name, alias value, and message and handles percent-encoded args.
        Returns: string"""
        rawargs = " ".join(self.bot.prefix.join(message.content.split(self.bot.prefix)[1:]).split(' ')[1:])
        view = StringView(rawargs)
        args = []
        while not view.eof:
            view.skip_ws()
            args.append(quoted_word(view))
        tempargs = args[:]
        new_command = command
        if '%*%' in command:
            new_command = new_command.replace('%*%', shlex.quote(rawargs) if ' ' in rawargs else rawargs)
            tempargs = []
        if '&*&' in command:
            new_command = new_command.replace('&*&', rawargs.replace("\"", "\\\"").replace("'", "\\'"))
            tempargs = []
        for index, value in enumerate(args):
            key = '%{}%'.format(index + 1)
            to_remove = False
            if key in command:
                new_command = new_command.replace(key, shlex.quote(value) if ' ' in value else value)
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

        return self.bot.prefix + new_command + " " + ' '.join((shlex.quote(v) if ' ' in v else v) for v in tempargs)

    async def parse_no_char(self, cstr, ctx):
        """
        Parses cvars and whatnot without an active character.
        :param cstr: The string to parse.
        :param ctx: The Context to parse the string in.
        :return: The parsed string.
        :rtype: str
        """
        _cache = {
            "gvars": {}
        }
        user_vars = await scripting.get_uvars(ctx)

        def process(to_process):
            ops = r"([-+*/().<>=])"
            _vars = user_vars

            evaluator = self.nochar_eval
            evaluator.reset()

            def get_gvar(name):
                if name not in _cache['gvars']:
                    result = ctx.bot.mdb.gvars.delegate.find_one({"key": name})
                    if result is None:
                        return None
                    _cache['gvars'][name] = result['value']
                return _cache['gvars'][name]

            def exists(name):
                return name in evaluator.names

            evaluator.functions['get_gvar'] = get_gvar
            evaluator.functions['exists'] = exists

            def set_value(name, value):
                evaluator.names[name] = value
                return ''

            evaluator.functions['set'] = set_value
            evaluator.names.update(_vars)

            def evalrepl(match):
                if match.group(1):  # {{}}
                    evalresult = evaluator.eval(match.group(1))
                elif match.group(2):  # <>
                    if re.match(r'<a?([@#]|:.+:)[&!]{0,2}\d+>', match.group(0)):  # ignore mentions
                        return match.group(0)
                    out = match.group(2)
                    evalresult = str(_vars.get(out, out))
                elif match.group(3):  # {}
                    varstr = match.group(3)
                    out = ""
                    for substr in re.split(ops, varstr):
                        temp = substr.strip()
                        out += str(_vars.get(temp, temp)) + " "
                    evalresult = str(roll(out).total)
                else:
                    evalresult = None
                return str(evalresult) if evalresult is not None else ''

            try:
                output = re.sub(SCRIPTING_RE, evalrepl, to_process)  # evaluate
            except Exception as ex:
                raise EvaluationError(ex)
            return output

        return await asyncio.get_event_loop().run_in_executor(None, process, cstr)

    @commands.group(pass_context=True, invoke_without_command=True)
    async def alias(self, ctx, alias_name=None, *, cmds=None):
        """Adds an alias for a long command.
        After an alias has been added, you can instead run the aliased command with !<alias_name>.
        If a user and a server have aliases with the same name, the user alias will take priority."""
        if alias_name is None:
            return await ctx.invoke(self.bot.get_command("alias list"))
        if alias_name in self.bot.commands:
            return await self.bot.say('There is already a built-in command with that name!')

        if ' ' in alias_name or not alias_name:
            return await self.bot.say('Invalid alias name.')

        user_aliases = await scripting.get_aliases(ctx)
        if cmds is None:
            alias = user_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = f'!alias {alias_name} {alias}'
            return await self.bot.say(f'**{alias_name}**:\n(Copy-pastable)\n```md\n{alias}\n```')

        await self.bot.mdb.aliases.update_one({"owner": ctx.message.author.id, "name": alias_name},
                                              {"$set": {"commands": cmds.lstrip('!')}}, True)
        await self.bot.say('Alias `!{}` added for command:\n`!{}`'.format(alias_name, cmds.lstrip('!')))

    @alias.command(pass_context=True, name='list')
    async def alias_list(self, ctx):
        """Lists all user aliases."""
        user_aliases = await scripting.get_aliases(ctx)
        aliases = list(user_aliases.keys())
        sorted_aliases = sorted(aliases)
        return await self.bot.say('Your aliases:\n{}'.format(', '.join(sorted_aliases)))

    @alias.command(pass_context=True, name='delete', aliases=['remove'])
    async def alias_delete(self, ctx, alias_name):
        """Deletes a user alias."""
        result = await self.bot.mdb.aliases.delete_one({"owner": ctx.message.author.id, "name": alias_name})
        if not result.deleted_count:
            return await self.bot.say('Alias not found.')
        await self.bot.say('Alias {} removed.'.format(alias_name))

    @alias.command(pass_context=True, name='deleteall', aliases=['removeall'])
    async def alias_deleteall(self, ctx):
        """Deletes ALL user aliases."""
        await self.bot.say("This will delete **ALL** of your user aliases. "
                           "Are you *absolutely sure* you want to continue?\n"
                           "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel)
        if not reply.content == "Yes, I am sure":
            return await self.bot.say("Unconfirmed. Aborting.")

        await self.bot.mdb.aliases.delete_many({"owner": ctx.message.author.id})
        return await self.bot.say("OK. I have deleted all your aliases.")

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['serveralias'], no_pm=True)
    async def servalias(self, ctx, alias_name=None, *, cmds=None):
        """Adds an alias that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have aliases with the same name, the user alias will take priority."""
        if alias_name is None:
            return await ctx.invoke(self.bot.get_command("servalias list"))

        server_aliases = await scripting.get_servaliases(ctx)
        if alias_name in self.bot.commands:
            return await self.bot.say('There is already a built-in command with that name!')

        if cmds is None:
            alias = server_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = f'!servalias {alias_name} {alias}'
            return await self.bot.say(f'**{alias_name}**:\n(Copy-pastable)```md\n{alias}\n```')

        if not self.can_edit_servaliases(ctx):
            return await self.bot.say("You do not have permission to edit server aliases. Either __Administrator__ "
                                      "Discord permissions or a role called \"Server Aliaser\" is required.")

        await self.bot.mdb.servaliases.update_one({"server": ctx.message.server.id, "name": alias_name},
                                                  {"$set": {"commands": cmds.lstrip('!')}}, True)
        await self.bot.say('Server alias `!{}` added for command:\n`!{}`'.format(alias_name, cmds.lstrip('!')))

    @servalias.command(pass_context=True, name='list', no_pm=True)
    async def servalias_list(self, ctx):
        """Lists all server aliases."""
        server_aliases = await scripting.get_servaliases(ctx)
        aliases = list(server_aliases.keys())
        sorted_aliases = sorted(aliases)
        return await self.bot.say('This server\'s aliases:\n{}'.format(', '.join(sorted_aliases)))

    @servalias.command(pass_context=True, name='delete', aliases=['remove'], no_pm=True)
    async def servalias_delete(self, ctx, alias_name):
        """Deletes a server alias.
        Any user with permission to create a server alias can delete one from the server."""
        if not self.can_edit_servaliases(ctx):
            return await self.bot.say("You do not have permission to edit server aliases. Either __Administrator__ "
                                      "Discord permissions or a role called \"Server Aliaser\" is required.")
        result = await self.bot.mdb.servaliases.delete_one({"server": ctx.message.server.id, "name": alias_name})
        if not result.deleted_count:
            return await self.bot.say('Server alias not found.')
        await self.bot.say('Server alias {} removed.'.format(alias_name))

    @staticmethod
    def can_edit_servaliases(ctx):
        """
        Returns whether a user can edit server aliases in the current context.
        """
        return ctx.message.author.server_permissions.administrator or \
               'server aliaser' in (r.name.lower() for r in ctx.message.author.roles) or \
               ctx.message.author.id == ctx.bot.owner.id

    @commands.group(pass_context=True, invoke_without_command=True)
    async def snippet(self, ctx, snipname=None, *, snippet=None):
        """Creates a snippet to use in attack macros.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*."""
        if snipname is None:
            return await ctx.invoke(self.bot.get_command("snippet list"))
        user_snippets = await scripting.get_snippets(ctx)

        if snippet is None:
            return await self.bot.say(f'**{snipname}**:\n'
                                      f'(Copy-pastable)```md\n'
                                      f'!snippet {snipname} {user_snippets.get(snipname, "Not defined.")}'
                                      f'\n```')

        if len(snipname) < 2: return await self.bot.say("Snippets must be at least 2 characters long!")
        await self.bot.mdb.snippets.update_one({"owner": ctx.message.author.id, "name": snipname},
                                               {"$set": {"snippet": snippet}}, True)
        await self.bot.say('Shortcut {} added for arguments:\n`{}`'.format(snipname, snippet))

    @snippet.command(pass_context=True, name='list')
    async def snippet_list(self, ctx):
        """Lists your user snippets."""
        user_snippets = await scripting.get_snippets(ctx)
        await self.bot.say('Your snippets:\n{}'.format(', '.join(sorted([name for name in user_snippets.keys()]))))

    @snippet.command(pass_context=True, name='delete', aliases=['remove'])
    async def snippet_delete(self, ctx, snippet_name):
        """Deletes a snippet."""
        result = await self.bot.mdb.snippets.delete_one({"owner": ctx.message.author.id, "name": snippet_name})
        if not result.deleted_count:
            return await self.bot.say('Snippet not found.')
        await self.bot.say('Shortcut {} removed.'.format(snippet_name))

    @snippet.command(pass_context=True, name='deleteall', aliases=['removeall'])
    async def snippet_deleteall(self, ctx):
        """Deletes ALL user snippets."""
        await self.bot.say("This will delete **ALL** of your user snippets. "
                           "Are you *absolutely sure* you want to continue?\n"
                           "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel)
        if not reply.content == "Yes, I am sure":
            return await self.bot.say("Unconfirmed. Aborting.")

        await self.bot.mdb.snippets.delete_many({"owner": ctx.message.author.id})
        return await self.bot.say("OK. I have deleted all your snippets.")

    @commands.group(pass_context=True, invoke_without_command=True, no_pm=True)
    async def servsnippet(self, ctx, snipname=None, *, snippet=None):
        """Creates a snippet to use in attack macros for the entire server.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have snippets with the same name, the user snippet will take priority.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*."""
        if snipname is None:
            return await ctx.invoke(self.bot.get_command("servsnippet list"))
        server_id = ctx.message.server.id
        server_snippets = await scripting.get_servsnippets(ctx)

        if snippet is None:
            return await self.bot.say(f'**{snipname}**:\n'
                                      f'(Copy-pastable)```md\n'
                                      f'!snippet {snipname} {server_snippets.get(snipname,"Not defined.")}\n'
                                      f'```')

        if self.can_edit_servaliases(ctx):
            if len(snipname) < 2: return await self.bot.say("Snippets must be at least 2 characters long!")
            await self.bot.mdb.servsnippets.update_one({"server": server_id, "name": snipname},
                                                       {"$set": {"snippet": snippet}}, True)
            await self.bot.say('Server snippet {} added for arguments:\n`{}`'.format(snipname, snippet))
        else:
            return await self.bot.say("You do not have permission to edit server snippets. Either __Administrator__ "
                                      "Discord permissions or a role called \"Server Aliaser\" is required.")

    @servsnippet.command(pass_context=True, name='list', no_pm=True)
    async def servsnippet_list(self, ctx):
        """Lists this server's snippets."""
        server_snippets = await scripting.get_servsnippets(ctx)
        await self.bot.say(
            'This server\'s snippets:\n{}'.format(', '.join(sorted([name for name in server_snippets.keys()]))))

    @servsnippet.command(pass_context=True, name='delete', aliases=['remove'], no_pm=True)
    async def servsnippet_delete(self, ctx, snippet_name):
        """Deletes a server snippet.
        Any user that can create a server snippet can delete one."""
        if not self.can_edit_servaliases(ctx):
            return await self.bot.say("You do not have permission to edit server snippets. Either __Administrator__ "
                                      "Discord permissions or a role called \"Server Aliaser\" is required.")
        result = await self.bot.mdb.servsnippets.delete_one({"server": ctx.message.server.id, "name": snippet_name})
        if not result.deleted_count:
            return await self.bot.say('Snippet not found.')
        await self.bot.say('Server snippet {} removed.'.format(snippet_name))

    @commands.command(pass_context=True)
    async def test(self, ctx, *, teststr):
        """Parses `str` as if it were in an alias, for testing."""
        char = await Character.from_ctx(ctx)
        parsed = await char.parse_cvars(teststr, ctx)
        parsed = clean_content(parsed, ctx)
        await self.bot.say(f"{ctx.message.author.display_name}: {parsed}")

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['uvar'])
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
            return await self.bot.say(f'**{name}**:\n`{uvar}`')

        if name in STAT_VAR_NAMES or any(c in name for c in '-/()[]\\.^$*+?|{}'):
            return await self.bot.say("Could not create uvar: already builtin, or contains invalid character!")

        await scripting.set_uvar(ctx, name, value)
        await self.bot.say('User variable `{}` set to: `{}`'.format(name, value))

    @uservar.command(pass_context=True, name='remove', aliases=['delete'])
    async def uvar_remove(self, ctx, name):
        """Deletes a uvar from the user."""
        result = await self.bot.mdb.uvars.delete_one({"owner": ctx.message.author.id, "name": name})
        if not result.deleted_count:
            return await self.bot.say("Uvar does not exist.")
        await self.bot.say('User variable {} removed.'.format(name))

    @uservar.command(pass_context=True, name='list')
    async def uvar_list(self, ctx):
        """Lists all uvars for the user."""
        user_vars = await scripting.get_uvars(ctx)
        await self.bot.say('Your user variables:\n{}'.format(', '.join(sorted([name for name in user_vars.keys()]))))

    @uservar.command(pass_context=True, name='deleteall', aliases=['removeall'])
    async def uvar_deleteall(self, ctx):
        """Deletes ALL user variables."""
        await self.bot.say("This will delete **ALL** of your user variables (uvars). "
                           "Are you *absolutely sure* you want to continue?\n"
                           "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel)
        if (not reply) or (not reply.content == "Yes, I am sure"):
            return await self.bot.say("Unconfirmed. Aborting.")

        await self.bot.mdb.uvars.delete_many({"owner": ctx.message.author.id})
        return await self.bot.say("OK. I have deleted all your uvars.")

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['gvar'])
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
        return await self.bot.say(f"**{name}**:\n*Owner: {gvar['owner_name']}* ```\n{gvar['value']}\n```")

    @globalvar.command(pass_context=True, name='create')
    async def gvar_create(self, ctx, *, value):
        """Creates a global variable.
        A name will be randomly assigned upon creation."""
        name = str(uuid.uuid4())
        data = {'key': name, 'owner': ctx.message.author.id, 'owner_name': str(ctx.message.author), 'value': value,
                'editors': []}
        await self.bot.mdb.gvars.insert_one(data)
        await self.bot.say(f"Created global variable `{name}`.")

    @globalvar.command(pass_context=True, name='edit')
    async def gvar_edit(self, ctx, name, *, value):
        """Edits a global variable."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await self.bot.say("Global variable not found.")
        elif gvar['owner'] != ctx.message.author.id and not ctx.message.author.id in gvar.get('editors', []):
            return await self.bot.say("You are not allowed to edit this variable.")
        else:
            await self.bot.mdb.gvars.update_one({"key": name}, {"$set": {"value": value}})
        await self.bot.say(f'Global variable `{name}` edited.')

    @globalvar.command(pass_context=True, name='editor')
    async def gvar_editor(self, ctx, name, user: discord.Member = None):
        """Toggles the editor status of a user."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await self.bot.say("Global variable not found.")

        if user is not None:
            if gvar['owner'] != ctx.message.author.id:
                return await self.bot.say("You are not the owner of this variable.")
            else:
                e = gvar.get('editors', [])
                if user.id in e:
                    e.remove(user.id)
                    msg = f"Removed {user} from the editor list."
                else:
                    e.append(user.id)
                    msg = f"Added {user} to the editor list."
                await self.bot.mdb.gvars.update_one({"key": name}, {"$set": {"editors": e}})
            await self.bot.say(f'Global variable `{name}` edited: {msg}')
        else:
            await self.bot.say(f"Editors: {', '.join(gvar.get('editors', []))}")

    @globalvar.command(pass_context=True, name='remove', aliases=['delete'])
    async def gvar_remove(self, ctx, name):
        """Deletes a global variable."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await self.bot.say("Global variable not found.")
        elif gvar['owner'] != ctx.message.author.id:
            return await self.bot.say("You are not the owner of this variable.")
        else:
            if await confirm(ctx, f"Are you sure you want to delete `{name}`?"):
                await self.bot.mdb.gvars.delete_one({"key": name})
            else:
                return await self.bot.say("Ok, cancelling.")

        await self.bot.say('Global variable {} removed.'.format(name))

    @globalvar.command(pass_context=True, name='list')
    async def gvar_list(self, ctx):
        """Lists all global variables for the user."""
        user_vars = []
        async for gvar in self.bot.mdb.gvars.find({"owner": ctx.message.author.id}):
            user_vars.append((gvar['key'], gvar['value']))
        gvar_list = [f"`{k}`: {textwrap.shorten(v, 20)}" for k, v in sorted(user_vars, key=lambda i: i[0])]
        say_list = ['']
        for g in gvar_list:
            if len(g) + len(say_list[-1]) < 1900:
                say_list[-1] += f'\n{g}'
            else:
                say_list.append(g)
        await self.bot.say('Your global variables:{}'.format(say_list[0]))
        for m in say_list[1:]:
            await self.bot.say(m)


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
    """A singleton class to pretend to be ctx."""

    def __init__(self, bot, message):
        self.bot = bot
        self.message = message


class NoCharacterEvaluator(ScriptingEvaluator):
    def __init__(self, operators=None, functions=None, names=None):
        _funcs = scripting.DEFAULT_FUNCTIONS.copy()
        _funcs.update(get_cc=self.needs_char, set_cc=self.needs_char, get_cc_max=self.needs_char,
                      get_cc_min=self.needs_char, mod_cc=self.needs_char,
                      cc_exists=self.needs_char, create_cc_nx=self.needs_char,
                      get_slots=self.needs_char, get_slots_max=self.needs_char, set_slots=self.needs_char,
                      use_slot=self.needs_char,
                      get_hp=self.needs_char, set_hp=self.needs_char, mod_hp=self.needs_char,
                      get_temphp=self.needs_char, set_temphp=self.needs_char,
                      set_cvar=self.needs_char, delete_cvar=self.needs_char, set_cvar_nx=self.needs_char,
                      get_raw=self.needs_char, combat=self.needs_char)
        _ops = scripting.DEFAULT_OPERATORS.copy()
        _names = {"True": True, "False": False, "currentHp": 0}

        if operators:
            _ops.update(operators)
        if functions:
            _funcs.update(functions)
        if names:
            _names.update(names)

        super(NoCharacterEvaluator, self).__init__(_ops, _funcs, _names)
        self._initial_names = copy.copy(self.names)

    def needs_char(self, *args, **kwargs):
        raise FunctionRequiresCharacter()  # no. bad.

    def reset(self):
        self.names = copy.copy(self._initial_names)
        self._loops = 0
