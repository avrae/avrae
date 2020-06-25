import asyncio
import traceback
import uuid

import draconic

import cogs5e.models.character as character_model
from aliasing.constants import CVAR_SIZE_LIMIT, GVAR_SIZE_LIMIT, UVAR_SIZE_LIMIT
from aliasing.personal import Alias, Servalias, Servsnippet, Snippet
from cogs5e.models.errors import AvraeException, InvalidArgument, NoCharacter, NotAllowed
from aliasing.errors import EvaluationError
from utils.argparser import argquote, argsplit


async def handle_aliases(ctx):
    # ctx.prefix: the invoking prefix
    # ctx.invoked_with: the first word
    alias = ctx.invoked_with

    # personal alias/servalias
    command_code = (await Alias.get_code_for(alias, ctx)) or (await Servalias.get_code_for(alias, ctx))

    if not command_code:
        return

    command_code = await handle_alias_arguments(command_code, ctx)
    char = None
    try:
        char = await character_model.Character.from_ctx(ctx)
    except NoCharacter:
        pass

    try:
        if char:
            ctx.message.content = await char.parse_cvars(command_code, ctx)
        else:
            ctx.message.content = await parse_no_char(command_code, ctx)
    except EvaluationError as err:
        return await handle_alias_exception(ctx, err)
    except Exception as e:
        return await ctx.send(e)

    # send it back around to be reprocessed
    await ctx.bot.process_commands(ctx.message)


async def handle_alias_arguments(command, ctx):
    """Takes an alias name, alias value, and message and handles percent-encoded args.
    Returns: string"""
    prefix = ctx.prefix
    rawargs = ctx.view.read_rest()

    args = argsplit(rawargs)
    tempargs = args[:]
    new_command = command
    if '%*%' in command:
        new_command = new_command.replace('%*%', argquote(rawargs))
        tempargs = []
    if '&*&' in command:
        new_command = new_command.replace('&*&', rawargs.replace("\"", "\\\""))
        tempargs = []
    if '&ARGS&' in command:
        new_command = new_command.replace('&ARGS&', str(args))
        tempargs = []
    for index, value in enumerate(args):
        key = '%{}%'.format(index + 1)
        to_remove = False
        if key in command:
            new_command = new_command.replace(key, argquote(value))
            to_remove = True
        key = '&{}&'.format(index + 1)
        if key in command:
            new_command = new_command.replace(key, value.replace("\"", "\\\""))
            to_remove = True
        if to_remove:
            try:
                tempargs.remove(value)
            except ValueError:
                pass

    quoted_args = ' '.join(map(argquote, tempargs))
    return f"{prefix}{new_command} {quoted_args}".strip()


# cvars
def set_cvar(character, name, value):
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument("Cvar names must be identifiers "
                              "(only contain a-z, A-Z, 0-9, _, and not start with a number).")
    elif name in character.get_scope_locals(True):
        raise InvalidArgument(f"The variable `{name}` is already built in.")
    elif len(value) > CVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Cvars must be shorter than {CVAR_SIZE_LIMIT} characters.")

    character.set_cvar(name, value)


# uvars
async def get_uvars(ctx):
    uvars = {}
    async for uvar in ctx.bot.mdb.uvars.find({"owner": str(ctx.author.id)}):
        uvars[uvar['name']] = uvar['value']
    return uvars


async def set_uvar(ctx, name, value):
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument("Uvar names must be valid identifiers "
                              "(only contain a-z, A-Z, 0-9, _, and not start with a number).")
    elif len(value) > UVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Uvars must be shorter than {UVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.uvars.update_one(
        {"owner": str(ctx.author.id), "name": name},
        {"$set": {"value": value}},
        True)


async def update_uvars(ctx, uvar_dict, changed=None):
    if changed is None:
        for name, value in uvar_dict.items():
            await set_uvar(ctx, name, value)
    else:
        for name in changed:
            if name in uvar_dict:
                await set_uvar(ctx, name, uvar_dict[name])
            else:
                await ctx.bot.mdb.uvars.delete_one({"owner": str(ctx.author.id), "name": name})


# gvars
async def create_gvar(ctx, value):
    value = str(value)
    if len(value) > GVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Gvars must be shorter than {GVAR_SIZE_LIMIT} characters.")
    name = str(uuid.uuid4())
    data = {'key': name, 'owner': str(ctx.author.id), 'owner_name': str(ctx.author), 'value': value,
            'editors': []}
    await ctx.bot.mdb.gvars.insert_one(data)
    return name


async def update_gvar(ctx, gid, value):
    value = str(value)
    gvar = await ctx.bot.mdb.gvars.find_one({"key": gid})
    if gvar is None:
        raise InvalidArgument("Global variable not found.")
    elif gvar['owner'] != str(ctx.author.id) and not str(ctx.author.id) in gvar.get('editors', []):
        raise NotAllowed("You are not allowed to edit this variable.")
    elif len(value) > GVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Gvars must be shorter than {GVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.gvars.update_one({"key": gid}, {"$set": {"value": value}})


# snippets
async def parse_snippets(args, ctx) -> str:
    """
    Parses user and server snippets.
    :param args: The string to parse. Will be split automatically
    :param ctx: The Context.
    :return: The string, with snippets replaced.
    """
    if isinstance(args, str):
        args = argsplit(args)
    if not isinstance(args, list):
        args = list(args)
    snippets = await Servsnippet.get_ctx_map(ctx)
    snippets.update(await Snippet.get_ctx_map(ctx))
    for index, arg in enumerate(args):  # parse snippets
        snippet_value = snippets.get(arg)
        if snippet_value:
            args[index] = snippet_value
        elif ' ' in arg:
            args[index] = argquote(arg)
    return " ".join(args)


async def parse_no_char(cstr, ctx):
    """
    Parses cvars and whatnot without an active character.
    :param cstr: The string to parse.
    :param ctx: The Context to parse the string in.
    :return: The parsed string.
    :rtype: str
    """
    from aliasing.evaluators import ScriptingEvaluator
    evaluator = await ScriptingEvaluator.new(ctx)
    out = await asyncio.get_event_loop().run_in_executor(None, evaluator.transformed_str, cstr)
    await evaluator.run_commits()
    return out


async def handle_alias_exception(ctx, err):
    e = err.original
    location = f"when parsing expression {err.expression}"
    locinfo = None
    if isinstance(e, AvraeException):
        return await ctx.channel.send(err)
    elif isinstance(e, draconic.InvalidExpression):
        try:
            location = f"on line {e.node.lineno}, col {e.node.col_offset}"
            locinfo = (e.node.lineno, e.node.col_offset)
        except AttributeError:
            pass
    elif isinstance(e, draconic.DraconicSyntaxError):
        location = f"on line {e.lineno}, col {e.offset}"
        locinfo = (e.lineno, e.offset)

    # make a pointer to the error so it looks nice
    point_to_error = ''
    if locinfo:
        line, col = locinfo
        the_line = err.expression.split('\n')[line - 1]
        point_to_error = f"{the_line}\n{' ' * (col)}^\n"

    if isinstance(e, draconic.AnnotatedException):
        e = e.original

    tb = ''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))
    try:
        await ctx.author.send(
            f"```py\n"
            f"Error {location}:\n"
            f"{point_to_error}"
            f"{tb}\n"
            f"```"
            f"This is an issue in a user-created command; do *not* report this on the official bug tracker.")
    except:
        pass
    return await ctx.channel.send(err)
