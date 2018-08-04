import discord.utils
from discord.ext import commands

import credentials


#
# This is a modified version of checks.py, originally made by Rapptz
#
#                 https://github.com/Rapptz
#          https://github.com/Rapptz/RoboDanny/tree/async
#


def is_owner_check(ctx):
    return ctx.message.author.id == credentials.owner_id


def is_owner():
    return commands.check(is_owner_check)


# The permission system of the bot is based on a "just works" basis
# You have permissions and the bot has permissions. If you meet the permissions
# required to execute the command (and the bot does as well) then it goes through
# and you can execute the command.
# If these checks fail, then there are two fallbacks.
# A role with the name of Bot Mod and a role with the name of Bot Admin.
# Having these roles provides you access to certain commands without actually having
# the permissions required for them.
# Of course, the owner will always be able to execute commands.

def check_permissions(ctx, perms):
    if is_owner_check(ctx):
        return True

    ch = ctx.message.channel
    author = ctx.message.author
    try:
        resolved = ch.permissions_for(author)
    except AttributeError:
        resolved = None
    return all(getattr(resolved, name, None) == value for name, value in perms.items())


def role_or_permissions(ctx, check, **perms):
    if check_permissions(ctx, perms):
        return True

    ch = ctx.message.channel
    author = ctx.message.author
    if ch.is_private:
        return False  # can't have roles in PMs

    try:
        role = discord.utils.find(check, author.roles)
    except:
        return False
    return role is not None


def mod_or_permissions(**perms):
    def predicate(ctx):
        mod_role = "Bot Mod".lower()
        admin_role = "Bot Admin".lower()
        return role_or_permissions(ctx, lambda r: r.name.lower() in (mod_role, admin_role), **perms)

    return commands.check(predicate)


def admin_or_permissions(**perms):
    def predicate(ctx):
        admin_role = "Bot Admin".lower()
        return role_or_permissions(ctx, lambda r: r.name.lower() == admin_role.lower(), **perms)

    return commands.check(predicate)


def serverowner_or_permissions(**perms):
    def predicate(ctx):
        if ctx.message.server is None:
            return False
        server = ctx.message.server
        owner = server.owner

        if ctx.message.author.id == owner.id:
            return True

        return check_permissions(ctx, perms)

    return commands.check(predicate)
