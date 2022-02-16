from pydantic import BaseModel

from utils.functions import get_guild_member, user_from_id


async def update_user_map(ctx, ddb_id, discord_id):
    """
    Update the one-to-one mapping of DDB user IDs to Discord user IDs.
    """
    # todo: this should be a multi-document transaction when we move to documentdb >= 4.0
    # as is, there is a possible race condition between the delete and update, but unless there is extreme latency
    # this shouldn't happen
    existing_mapping = await ctx.bot.mdb.ddb_account_map.find_one({"discord_id": discord_id})
    if existing_mapping is None:
        await ctx.bot.mdb.ddb_account_map.update_one(
            {"ddb_id": ddb_id},
            {"$set": {"discord_id": discord_id}},
            upsert=True
        )
    elif existing_mapping['ddb_id'] != ddb_id:
        await ctx.bot.mdb.ddb_account_map.delete_one({"discord_id": discord_id})
        await ctx.bot.mdb.ddb_account_map.update_one(
            {"ddb_id": ddb_id},
            {"$set": {"discord_id": discord_id}},
            upsert=True
        )


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


# ==== pydantic helpers ====
def snake_to_lowercamel(snake_case):
    """Converts an identifier in snake_case to lowerCamelCase."""
    first, *others = snake_case.split('_')
    return first + ''.join(word.capitalize() for word in others)


class ApiBaseModel(BaseModel):
    """A base pydantic model with camelCase aliases for each property."""

    class Config:
        alias_generator = snake_to_lowercamel

    # compatibility w/ @callback gamelog decorator
    @classmethod
    def from_dict(cls, d):
        return cls.parse_obj(d)
