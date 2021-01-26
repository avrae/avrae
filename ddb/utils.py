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
