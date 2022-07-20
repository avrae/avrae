from disnake.ext import commands

from utils.aldclient import discord_user_to_dict
from utils.functions import natural_join

is_owner = commands.is_owner


def admin_or_permissions(**perms):
    """The user has a role name "Bot Admin" or all of the passed permissions"""
    # noinspection PyUnresolvedReferences
    real_predicate = commands.check_any(
        commands.has_role("Bot Admin"),
        commands.has_permissions(**perms),
        commands.is_owner(),
    ).predicate

    async def predicate(ctx):
        try:
            return await real_predicate(ctx)
        except commands.CheckFailure:
            raise commands.CheckFailure(
                f"You require a role named Bot Admin or these permissions to run this command: {', '.join(perms)}"
            )

    return commands.check(predicate)


BREWER_ROLES = ("Server Brewer", "Dragonspeaker")


def can_edit_serverbrew():
    # noinspection PyUnresolvedReferences
    real_predicate = commands.check_any(
        commands.has_any_role(*BREWER_ROLES),
        commands.has_permissions(manage_guild=True),
        commands.is_owner(),
    ).predicate

    async def predicate(ctx):
        try:
            return await real_predicate(ctx)
        except commands.CheckFailure:
            raise commands.CheckFailure(
                "You do not have permission to manage server homebrew. Either __Manage Server__ "
                'Discord permissions or a role named "Server Brewer" or "Dragonspeaker" '
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
            user = discord_user_to_dict(ctx.author)

        flag_on = await ctx.bot.ldclient.variation(flag_name, user, default)
        if flag_on:
            return True

        raise commands.CheckFailure("This command is currently disabled. Check back later!")

    return commands.check(predicate)


def user_permissions(*permissions: str):
    """The user must have all of the specified permissions granted by `!admin set_user_permissions`"""

    async def predicate(ctx):
        user_p = await ctx.bot.mdb.user_permissions.find_one({"id": str(ctx.author.id)})
        if all(user_p.get(p) for p in permissions):
            return True
        raise commands.CheckFailure(f"This command requires the {natural_join(permissions, 'and')} permissions.")

    return commands.check(predicate)
