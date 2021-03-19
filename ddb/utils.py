from utils.functions import get_guild_member, user_from_id


async def ddb_id_to_discord_id(mdb, ddb_user_id):
    """
    Translates a DDB user ID to a Discord user ID.

    :rtype: int or None
    """
    # this mapping is updated in ddb.client.get_ddb_user()
    result = await mdb.ddb_account_map.find_one({"ddb_id": ddb_user_id})
    if result is not None:
        return result['discord_id']
    return None


async def ddb_id_to_discord_user(ctx, ddb_user_id, guild=None):
    """
    Translates a DDB user ID to a Discord user.

    :rtype: discord.User or None
    """
    discord_id = await ddb_id_to_discord_id(ctx.bot.mdb, ddb_user_id)
    if discord_id is None:
        return None

    if guild is not None:
        # optimization: we can use get_guild_member rather than user_from_id because we're operating in a guild
        return await get_guild_member(guild, discord_id)
    else:
        return await user_from_id(ctx, discord_id)
