import discord.utils
from discord.ext import commands

from utils import config


# The permission system of the bot is based on a "just works" basis
# You have permissions and the bot has permissions. If you meet the permissions
# required to execute the command (and the bot does as well) then it goes through
# and you can execute the command.
# If these checks fail, then there are two fallbacks.
# A role with the name of Bot Mod and a role with the name of Bot Admin.
# Having these roles provides you access to certain commands without actually having
# the permissions required for them.
# Of course, the owner will always be able to execute commands.

# ===== predicates =====
def author_is_owner(ctx):
    return ctx.author.id == config.OWNER_ID


def _check_permissions(ctx, perms):
    if author_is_owner(ctx):
        return True

    ch = ctx.channel
    author = ctx.author
    try:
        resolved = ch.permissions_for(author)
    except AttributeError:
        resolved = None
    return all(getattr(resolved, name, None) == value for name, value in perms.items())


def _role_or_permissions(ctx, role_filter, **perms):
    if _check_permissions(ctx, perms):
        return True

    ch = ctx.message.channel
    author = ctx.message.author
    if isinstance(ch, discord.abc.PrivateChannel):
        return False  # can't have roles in PMs

    try:
        role = discord.utils.find(role_filter, author.roles)
    except:
        return False
    return role is not None


# ===== checks =====
def is_owner():
    def predicate(ctx):
        if author_is_owner(ctx):
            return True
        raise commands.CheckFailure("Only the bot owner may run this command.")

    return commands.check(predicate)


def role_or_permissions(role_name, **perms):
    def predicate(ctx):
        if _role_or_permissions(ctx, lambda r: r.name.lower() == role_name.lower(), **perms):
            return True
        raise commands.CheckFailure(
            f"You require a role named {role_name} or these permissions to run this command: {', '.join(perms)}")

    return commands.check(predicate)


def admin_or_permissions(**perms):
    def predicate(ctx):
        admin_role = "Bot Admin"
        if _role_or_permissions(ctx, lambda r: r.name.lower() == admin_role.lower(), **perms):
            return True
        raise commands.CheckFailure(
            f"You require a role named Bot Admin or these permissions to run this command: {', '.join(perms)}")

    return commands.check(predicate)


BREWER_ROLES = ("server brewer", "dragonspeaker")


def can_edit_serverbrew():
    def predicate(ctx):
        if ctx.author.guild_permissions.manage_guild or \
                any(r.name.lower() in BREWER_ROLES for r in ctx.author.roles) or \
                author_is_owner(ctx):
            return True
        raise commands.CheckFailure(
            "You do not have permission to manage server homebrew. Either __Manage Server__ "
            "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
            "is required."
        )

    return commands.check(predicate)


def feature_flag(flag_name, use_ddb_user=False, default=False):
    async def predicate(ctx):
        if use_ddb_user:
            ddb_user = await ctx.bot.ddb.get_ddb_user(ctx, ctx.author.id)
            if ddb_user is None:
                user = {"key": str(ctx.author.id), "anonymous": True}
            else:
                user = ddb_user.to_ld_dict()
        else:
            user = {"key": str(ctx.author.id), "name": str(ctx.author)}

        flag_on = await ctx.bot.ldclient.variation(flag_name, user, default)
        if flag_on:
            return True

        raise commands.CheckFailure(
            "This command is currently disabled. Check back later!"
        )

    return commands.check(predicate)
