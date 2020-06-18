import asyncio
import traceback
import uuid

import draconic

from aliasing.personal import Servsnippet, Snippet
from cogs5e.models.errors import AvraeException, InvalidArgument, NotAllowed
from utils.argparser import argquote, argsplit

# constants
GVAR_SIZE_LIMIT = 100_000
UVAR_SIZE_LIMIT = 10_000
CVAR_SIZE_LIMIT = 10_000
ALIAS_SIZE_LIMIT = 10_000
SNIPPET_SIZE_LIMIT = 2_000


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
    location = ''
    if isinstance(e, AvraeException):
        return await ctx.channel.send(err)
    elif isinstance(e, draconic.InvalidExpression):
        try:
            location = f" on line {e.node.lineno}, col {e.node.col_offset}"
        except AttributeError:
            pass
    elif isinstance(e, draconic.DraconicSyntaxError):
        location = f" on line {e.lineno}, col {e.offset}"
    tb = ''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))
    try:
        await ctx.author.send(
            f"```py\n"
            f"Error{location} when parsing expression {err.expression}:\n"
            f"{tb}\n"
            f"```")
    except:
        pass
    return await ctx.channel.send(err)
